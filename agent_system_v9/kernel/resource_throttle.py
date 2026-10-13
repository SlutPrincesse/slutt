"""
Resource Throttle (cgroups) - Dynamic CPU, memory, and disk I/O band-limiter preventing thread starvation
"""
import os
import subprocess
import threading
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CgroupVersion(Enum):
    V1 = "v1"
    V2 = "v2"


class ResourceType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    IO = "io"
    PIDS = "pids"


@dataclass
class ResourceLimits:
    cpu_quota: Optional[int] = None  # microseconds per period
    cpu_period: int = 100000
    cpu_shares: Optional[int] = None
    cpu_cpus: Optional[str] = None  # cpuset
    cpu_mems: Optional[str] = None  # memory nodes
    
    memory_limit: Optional[int] = None  # bytes
    memory_swap_limit: Optional[int] = None
    memory_soft_limit: Optional[int] = None
    memory_oom_control: bool = True
    
    io_weight: Optional[int] = None  # 10-1000
    io_read_bps: Optional[int] = None  # bytes/sec
    io_write_bps: Optional[int] = None
    io_read_iops: Optional[int] = None
    io_write_iops: Optional[int] = None
    
    pids_max: Optional[int] = None


@dataclass
class CgroupController:
    cgroup_path: str
    version: CgroupVersion
    limits: ResourceLimits
    pids: List[int] = field(default_factory=list)
    created: bool = False


class ResourceThrottle:
    def __init__(self, cgroup_root: str = "/sys/fs/cgroup"):
        self.cgroup_root = Path(cgroup_root)
        self._controllers: Dict[str, CgroupController] = {}
        self._version = self._detect_cgroup_version()
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._stats: Dict[str, Dict[str, Any]] = {}
    
    def _detect_cgroup_version(self) -> CgroupVersion:
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    if "cgroup2" in line or "cgroup v2" in line:
                        return CgroupVersion.V2
            return CgroupVersion.V1
        except Exception:
            return CgroupVersion.V1
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop(self):
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
    
    def create_cgroup(self, name: str, limits: ResourceLimits, parent: str = "agent_v9") -> str:
        cgroup_name = f"{parent}/{name}"
        cgroup_path = self.cgroup_root / cgroup_name
        
        with self._lock:
            if cgroup_path.exists():
                return str(cgroup_path)
        
        try:
            cgroup_path.mkdir(parents=True, exist_ok=True)
            
            controller = CgroupController(
                cgroup_path=str(cgroup_path),
                version=self._version,
                limits=limits
            )
            
            self._apply_limits(controller)
            controller.created = True
            
            with self._lock:
                self._controllers[name] = controller
            
            return str(cgroup_path)
        except Exception as e:
            raise RuntimeError(f"Failed to create cgroup: {e}")
    
    def _apply_limits(self, controller: CgroupController):
        limits = controller.limits
        path = Path(controller.cgroup_path)
        
        if self._version == CgroupVersion.V2:
            self._apply_v2_limits(path, limits)
        else:
            self._apply_v1_limits(path, limits)
    
    def _apply_v2_limits(self, path: Path, limits: ResourceLimits):
        if limits.cpu_quota is not None or limits.cpu_period != 100000:
            cpu_max = f"{limits.cpu_quota or 'max'} {limits.cpu_period}"
            (path / "cpu.max").write_text(cpu_max)
        
        if limits.cpu_shares is not None:
            (path / "cpu.weight").write_text(str(max(1, min(10000, limits.cpu_shares // 1024 + 1))))
        
        if limits.cpu_cpus:
            (path / "cpuset.cpus").write_text(limits.cpu_cpus)
        
        if limits.cpu_mems:
            (path / "cpuset.mems").write_text(limits.cpu_mems)
        
        if limits.memory_limit is not None:
            (path / "memory.max").write_text(str(limits.memory_limit))
        
        if limits.memory_swap_limit is not None:
            (path / "memory.swap.max").write_text(str(limits.memory_swap_limit))
        
        if limits.memory_soft_limit is not None:
            (path / "memory.low").write_text(str(limits.memory_soft_limit))
        
        if limits.memory_oom_control:
            (path / "memory.oom_control").write_text("1")
        
        if limits.io_weight is not None:
            (path / "io.weight").write_text(str(limits.io_weight))
        
        if limits.io_read_bps is not None:
            (path / "io.max").write_text(f"rbps={limits.io_read_bps}")
        
        if limits.io_write_bps is not None:
            (path / "io.max").write_text(f"wbps={limits.io_write_bps}")
        
        if limits.io_read_iops is not None:
            (path / "io.max").write_text(f"riops={limits.io_read_iops}")
        
        if limits.io_write_iops is not None:
            (path / "io.max").write_text(f"wiops={limits.io_write_iops}")
        
        if limits.pids_max is not None:
            (path / "pids.max").write_text(str(limits.pids_max))
    
    def _apply_v1_limits(self, path: Path, limits: ResourceLimits):
        # CPU
        cpu_path = self.cgroup_root / "cpu" / path.relative_to(self.cgroup_root)
        cpu_path.mkdir(parents=True, exist_ok=True)
        
        if limits.cpu_quota is not None:
            (cpu_path / "cpu.cfs_quota_us").write_text(str(limits.cpu_quota))
        (cpu_path / "cpu.cfs_period_us").write_text(str(limits.cpu_period))
        
        if limits.cpu_shares is not None:
            (cpu_path / "cpu.shares").write_text(str(limits.cpu_shares))
        
        # Cpuset
        cpuset_path = self.cgroup_root / "cpuset" / path.relative_to(self.cgroup_root)
        cpuset_path.mkdir(parents=True, exist_ok=True)
        
        if limits.cpu_cpus:
            (cpuset_path / "cpuset.cpus").write_text(limits.cpu_cpus)
        if limits.cpu_mems:
            (cpuset_path / "cpuset.mems").write_text(limits.cpu_mems)
        
        # Memory
        mem_path = self.cgroup_root / "memory" / path.relative_to(self.cgroup_root)
        mem_path.mkdir(parents=True, exist_ok=True)
        
        if limits.memory_limit is not None:
            (mem_path / "memory.limit_in_bytes").write_text(str(limits.memory_limit))
        if limits.memory_swap_limit is not None:
            (mem_path / "memory.memsw.limit_in_bytes").write_text(str(limits.memory_swap_limit))
        if limits.memory_soft_limit is not None:
            (mem_path / "memory.soft_limit_in_bytes").write_text(str(limits.memory_soft_limit))
        if limits.memory_oom_control:
            (mem_path / "memory.oom_control").write_text("1")
        
        # IO
        blkio_path = self.cgroup_root / "blkio" / path.relative_to(self.cgroup_root)
        blkio_path.mkdir(parents=True, exist_ok=True)
        
        if limits.io_weight is not None:
            (blkio_path / "blkio.weight").write_text(str(limits.io_weight))
        if limits.io_read_bps is not None:
            (blkio_path / "blkio.throttle.read_bps_device").write_text(f"8:0 {limits.io_read_bps}")
        if limits.io_write_bps is not None:
            (blkio_path / "blkio.throttle.write_bps_device").write_text(f"8:0 {limits.io_write_bps}")
        if limits.io_read_iops is not None:
            (blkio_path / "blkio.throttle.read_iops_device").write_text(f"8:0 {limits.io_read_iops}")
        if limits.io_write_iops is not None:
            (blkio_path / "blkio.throttle.write_iops_device").write_text(f"8:0 {limits.io_write_iops}")
        
        # PIDs
        pids_path = self.cgroup_root / "pids" / path.relative_to(self.cgroup_root)
        pids_path.mkdir(parents=True, exist_ok=True)
        
        if limits.pids_max is not None:
            (pids_path / "pids.max").write_text(str(limits.pids_max))
    
    def add_pid(self, cgroup_name: str, pid: int) -> bool:
        with self._lock:
            controller = self._controllers.get(cgroup_name)
            if not controller:
                return False
        
        try:
            tasks_file = Path(controller.cgroup_path) / ("cgroup.procs" if self._version == CgroupVersion.V2 else "tasks")
            with open(tasks_file, "w") as f:
                f.write(str(pid))
            
            with self._lock:
                controller.pids.append(pid)
            return True
        except Exception:
            return False
    
    def remove_pid(self, cgroup_name: str, pid: int) -> bool:
        with self._lock:
            controller = self._controllers.get(cgroup_name)
            if not controller:
                return False
        
        try:
            # Move to root cgroup
            root_tasks = self.cgroup_root / ("cgroup.procs" if self._version == CgroupVersion.V2 else "tasks")
            with open(root_tasks, "w") as f:
                f.write(str(pid))
            
            with self._lock:
                if pid in controller.pids:
                    controller.pids.remove(pid)
            return True
        except Exception:
            return False
    
    def update_limits(self, cgroup_name: str, limits: ResourceLimits) -> bool:
        with self._lock:
            controller = self._controllers.get(cgroup_name)
            if not controller:
                return False
            controller.limits = limits
        
        try:
            self._apply_limits(controller)
            return True
        except Exception:
            return False
    
    def get_stats(self, cgroup_name: str) -> Dict[str, Any]:
        with self._lock:
            controller = self._controllers.get(cgroup_name)
            if not controller:
                return {}
        
        path = Path(controller.cgroup_path)
        stats = {}
        
        try:
            if self._version == CgroupVersion.V2:
                stats = self._read_v2_stats(path)
            else:
                stats = self._read_v1_stats(path)
        except Exception:
            pass
        
        with self._lock:
            self._stats[cgroup_name] = stats
        
        return stats
    
    def _read_v2_stats(self, path: Path) -> Dict[str, Any]:
        stats = {}
        
        # CPU stats
        cpu_stat = path / "cpu.stat"
        if cpu_stat.exists():
            for line in cpu_stat.read_text().strip().split('\n'):
                if line:
                    k, v = line.split()
                    stats[f"cpu_{k}"] = int(v)
        
        # Memory stats
        mem_stat = path / "memory.stat"
        if mem_stat.exists():
            for line in mem_stat.read_text().strip().split('\n'):
                if line:
                    k, v = line.split()
                    stats[f"mem_{k}"] = int(v)
        
        # Memory current
        mem_cur = path / "memory.current"
        if mem_cur.exists():
            stats["mem_current"] = int(mem_cur.read_text().strip())
        
        # IO stats
        io_stat = path / "io.stat"
        if io_stat.exists():
            for line in io_stat.read_text().strip().split('\n'):
                if line:
                    parts = line.split()
                    if len(parts) >= 3:
                        dev, k, v = parts[0], parts[1], parts[2]
                        stats[f"io_{dev}_{k}"] = int(v)
        
        # PIDs
        pids_cur = path / "pids.current"
        if pids_cur.exists():
            stats["pids_current"] = int(pids_cur.read_text().strip())
        
        return stats
    
    def _read_v1_stats(self, path: Path) -> Dict[str, Any]:
        stats = {}
        rel_path = path.relative_to(self.cgroup_root)
        
        # CPU stats
        cpu_stat = self.cgroup_root / "cpu" / rel_path / "cpu.stat"
        if cpu_stat.exists():
            for line in cpu_stat.read_text().strip().split('\n'):
                if line:
                    k, v = line.split()
                    stats[f"cpu_{k}"] = int(v)
        
        # CPU usage
        cpu_usage = self.cgroup_root / "cpu" / rel_path / "cpuacct.usage"
        if cpu_usage.exists():
            stats["cpu_usage_ns"] = int(cpu_usage.read_text().strip())
        
        # Memory stats
        mem_stat = self.cgroup_root / "memory" / rel_path / "memory.stat"
        if mem_stat.exists():
            for line in mem_stat.read_text().strip().split('\n'):
                if line:
                    k, v = line.split()
                    stats[f"mem_{k}"] = int(v)
        
        mem_cur = self.cgroup_root / "memory" / rel_path / "memory.usage_in_bytes"
        if mem_cur.exists():
            stats["mem_current"] = int(mem_cur.read_text().strip())
        
        # IO stats
        blkio_stat = self.cgroup_root / "blkio" / rel_path / "blkio.io_service_bytes"
        if blkio_stat.exists():
            for line in blkio_stat.read_text().strip().split('\n'):
                if line:
                    parts = line.split()
                    if len(parts) >= 3:
                        dev, k, v = parts[0], parts[1], parts[2]
                        stats[f"io_{dev}_{k}"] = int(v)
        
        # PIDs
        pids_cur = self.cgroup_root / "pids" / rel_path / "pids.current"
        if pids_cur.exists():
            stats["pids_current"] = int(pids_cur.read_text().strip())
        
        return stats
    
    def delete_cgroup(self, cgroup_name: str) -> bool:
        with self._lock:
            controller = self._controllers.pop(cgroup_name, None)
            if not controller:
                return False
        
        try:
            # Move all pids to root first
            for pid in controller.pids:
                self.remove_pid(cgroup_name, pid)
            
            # Remove cgroup directory
            import shutil
            shutil.rmtree(controller.cgroup_path, ignore_errors=True)
            return True
        except Exception:
            return False
    
    def list_cgroups(self) -> List[str]:
        with self._lock:
            return list(self._controllers.keys())
    
    def get_controller(self, cgroup_name: str) -> Optional[CgroupController]:
        with self._lock:
            return self._controllers.get(cgroup_name)
    
    def apply_to_current_process(self, cgroup_name: str) -> bool:
        return self.add_pid(cgroup_name, os.getpid())
    
    def _monitor_loop(self):
        while self._running:
            time.sleep(5.0)
            with self._lock:
                cgroup_names = list(self._controllers.keys())
            
            for name in cgroup_names:
                self.get_stats(name)


_resource_throttle: Optional[ResourceThrottle] = None

def get_resource_throttle() -> ResourceThrottle:
    global _resource_throttle
    if _resource_throttle is None:
        _resource_throttle = ResourceThrottle()
        _resource_throttle.start()
    return _resource_throttle


def create_resource_limits(cpu_percent: float = 100.0, memory_mb: int = 512, 
                          io_bps: int = 0, pids: int = 100) -> ResourceLimits:
    return ResourceLimits(
        cpu_quota=int(cpu_percent * 1000),
        cpu_period=100000,
        memory_limit=memory_mb * 1024 * 1024,
        memory_swap_limit=memory_mb * 1024 * 1024 * 2,
        io_read_bps=io_bps if io_bps > 0 else None,
        io_write_bps=io_bps if io_bps > 0 else None,
        pids_max=pids
    )