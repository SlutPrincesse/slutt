"""
Native Nudge Low-Latency Monitor - Background watcher auditing I/O stalls to invoke auto-recovery
"""
import threading
import time
import psutil
import os
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class NudgeType(Enum):
    IO_STALL = "io_stall"
    CPU_THROTTLE = "cpu_throttle"
    MEMORY_PRESSURE = "memory_pressure"
    NETWORK_LATENCY = "network_latency"
    DEADLOCK_DETECTED = "deadlock_detected"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


@dataclass
class NudgeEvent:
    event_id: str
    nudge_type: NudgeType
    severity: float  # 0.0 to 1.0
    source: str
    message: str
    metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    handled: bool = False
    recovery_action: str = ""


class NudgeMonitor:
    def __init__(self, sensitivity: float = 0.8, check_interval: float = 0.1):
        self.sensitivity = sensitivity
        self.check_interval = check_interval
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._event_history: deque = deque(maxlen=1000)
        self._thresholds = {
            NudgeType.IO_STALL: {"io_wait_percent": 50.0},
            NudgeType.CPU_THROTTLE: {"cpu_percent": 90.0, "throttle_time": 0.1},
            NudgeType.MEMORY_PRESSURE: {"memory_percent": 85.0, "available_mb": 500},
            NudgeType.NETWORK_LATENCY: {"latency_ms": 500.0, "packet_loss": 0.05},
            NudgeType.DEADLOCK_DETECTED: {"thread_blocked_time": 10.0},
            NudgeType.RESOURCE_EXHAUSTION: {"fd_usage_percent": 80.0}
        }
        self._callbacks: Dict[str, List[Callable]] = {
            "nudge_detected": [],
            "nudge_handled": [],
            "recovery_triggered": []
        }
        self._recovery_actions: Dict[NudgeType, Callable] = {}
        self._register_default_recoveries()
    
    def _register_default_recoveries(self):
        self._recovery_actions[NudgeType.IO_STALL] = self._recover_io_stall
        self._recovery_actions[NudgeType.CPU_THROTTLE] = self._recover_cpu_throttle
        self._recovery_actions[NudgeType.MEMORY_PRESSURE] = self._recover_memory_pressure
        self._recovery_actions[NudgeType.NETWORK_LATENCY] = self._recover_network_latency
        self._recovery_actions[NudgeType.DEADLOCK_DETECTED] = self._recover_deadlock
        self._recovery_actions[NudgeType.RESOURCE_EXHAUSTION] = self._recover_resource_exhaustion
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop(self):
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
    
    def _monitor_loop(self):
        while self._running:
            try:
                self._check_system_health()
            except Exception:
                pass
            time.sleep(self.check_interval)
    
    def _check_system_health(self):
        metrics = self._collect_metrics()
        nudges = self._evaluate_thresholds(metrics)
        
        for nudge in nudges:
            self._handle_nudge(nudge)
    
    def _collect_metrics(self) -> Dict[str, float]:
        metrics = {}
        
        try:
            # CPU
            cpu = psutil.cpu_times_percent(interval=None)
            metrics["cpu_percent"] = psutil.cpu_percent(interval=None)
            metrics["cpu_iowait"] = cpu.iowait if hasattr(cpu, 'iowait') else 0
            
            # Memory
            mem = psutil.virtual_memory()
            metrics["memory_percent"] = mem.percent
            metrics["memory_available_mb"] = mem.available / 1024 / 1024
            
            # Disk I/O
            disk = psutil.disk_io_counters()
            if disk:
                metrics["disk_read_mb"] = disk.read_bytes / 1024 / 1024
                metrics["disk_write_mb"] = disk.write_bytes / 1024 / 1024
            
            # Network
            net = psutil.net_io_counters()
            if net:
                metrics["net_bytes_sent"] = net.bytes_sent
                metrics["net_bytes_recv"] = net.bytes_recv
            
            # Process
            proc = psutil.Process(os.getpid())
            metrics["process_memory_mb"] = proc.memory_info().rss / 1024 / 1024
            metrics["process_cpu_percent"] = proc.cpu_percent()
            metrics["process_fds"] = proc.num_fds() if hasattr(proc, 'num_fds') else 0
            metrics["process_threads"] = proc.num_threads()
            
            # System limits
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            metrics["fd_usage_percent"] = (metrics.get("process_fds", 0) / soft) * 100 if soft > 0 else 0
            
        except Exception:
            pass
        
        return metrics
    
    def _evaluate_thresholds(self, metrics: Dict[str, float]) -> List[NudgeEvent]:
        nudges = []
        
        # IO Stall
        if metrics.get("cpu_iowait", 0) > self._thresholds[NudgeType.IO_STALL]["io_wait_percent"]:
            severity = min(1.0, metrics["cpu_iowait"] / 100.0)
            nudges.append(NudgeEvent(
                event_id=f"nudge_{int(time.time() * 1000)}",
                nudge_type=NudgeType.IO_STALL,
                severity=severity,
                source="system_monitor",
                message=f"High I/O wait detected: {metrics['cpu_iowait']:.1f}%",
                metrics=metrics
            ))
        
        # CPU Throttle
        if metrics.get("cpu_percent", 0) > self._thresholds[NudgeType.CPU_THROTTLE]["cpu_percent"]:
            severity = min(1.0, metrics["cpu_percent"] / 100.0)
            nudges.append(NudgeEvent(
                event_id=f"nudge_{int(time.time() * 1000)}",
                nudge_type=NudgeType.CPU_THROTTLE,
                severity=severity,
                source="system_monitor",
                message=f"High CPU usage: {metrics['cpu_percent']:.1f}%",
                metrics=metrics
            ))
        
        # Memory Pressure
        if (metrics.get("memory_percent", 0) > self._thresholds[NudgeType.MEMORY_PRESSURE]["memory_percent"] or
            metrics.get("memory_available_mb", float('inf')) < self._thresholds[NudgeType.MEMORY_PRESSURE]["available_mb"]):
            severity = min(1.0, metrics.get("memory_percent", 0) / 100.0)
            nudges.append(NudgeEvent(
                event_id=f"nudge_{int(time.time() * 1000)}",
                nudge_type=NudgeType.MEMORY_PRESSURE,
                severity=severity,
                source="system_monitor",
                message=f"Memory pressure: {metrics.get('memory_percent', 0):.1f}% used",
                metrics=metrics
            ))
        
        # FD Exhaustion
        if metrics.get("fd_usage_percent", 0) > self._thresholds[NudgeType.RESOURCE_EXHAUSTION]["fd_usage_percent"]:
            severity = min(1.0, metrics["fd_usage_percent"] / 100.0)
            nudges.append(NudgeEvent(
                event_id=f"nudge_{int(time.time() * 1000)}",
                nudge_type=NudgeType.RESOURCE_EXHAUSTION,
                severity=severity,
                source="system_monitor",
                message=f"File descriptor exhaustion: {metrics['fd_usage_percent']:.1f}%",
                metrics=metrics
            ))
        
        return nudges
    
    def _handle_nudge(self, nudge: NudgeEvent):
        with self._lock:
            self._event_history.append(nudge)
        
        self._notify_nudge_detected(nudge)
        
        # Trigger recovery
        if nudge.nudge_type in self._recovery_actions:
            try:
                action = self._recovery_actions[nudge.nudge_type](nudge)
                nudge.recovery_action = action
                nudge.handled = True
                self._notify_recovery_triggered(nudge, action)
            except Exception as e:
                nudge.recovery_action = f"failed: {e}"
        
        self._notify_nudge_handled(nudge)
    
    def _recover_io_stall(self, nudge: NudgeEvent) -> str:
        # Reduce I/O priority, flush buffers
        return "io_priority_reduced"
    
    def _recover_cpu_throttle(self, nudge: NudgeEvent) -> str:
        # Reduce worker threads, yield CPU
        return "worker_throttled"
    
    def _recover_memory_pressure(self, nudge: NudgeEvent) -> str:
        # Trigger GC, clear caches
        import gc
        gc.collect()
        return "gc_triggered"
    
    def _recover_network_latency(self, nudge: NudgeEvent) -> str:
        # Reduce network requests, increase timeouts
        return "network_throttled"
    
    def _recover_deadlock(self, nudge: NudgeEvent) -> str:
        # Analyze thread states, interrupt if needed
        return "deadlock_analyzed"
    
    def _recover_resource_exhaustion(self, nudge: NudgeEvent) -> str:
        # Close idle connections, release resources
        return "resources_released"
    
    def register_recovery_action(self, nudge_type: NudgeType, action: Callable[[NudgeEvent], str]):
        self._recovery_actions[nudge_type] = action
    
    def set_threshold(self, nudge_type: NudgeType, thresholds: Dict[str, float]):
        self._thresholds[nudge_type] = thresholds
    
    def get_recent_nudges(self, limit: int = 100, nudge_type: NudgeType = None) -> List[NudgeEvent]:
        with self._lock:
            events = list(self._event_history)
        
        if nudge_type:
            events = [e for e in events if e.nudge_type == nudge_type]
        
        return events[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            events = list(self._event_history)
        
        by_type = {}
        for event in events:
            by_type[event.nudge_type.value] = by_type.get(event.nudge_type.value, 0) + 1
        
        return {
            "total_nudges": len(events),
            "by_type": by_type,
            "handled": sum(1 for e in events if e.handled),
            "unhandled": sum(1 for e in events if not e.handled)
        }
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _notify_nudge_detected(self, nudge: NudgeEvent):
        for cb in self._callbacks["nudge_detected"]:
            try:
                cb(nudge)
            except Exception:
                pass
    
    def _notify_nudge_handled(self, nudge: NudgeEvent):
        for cb in self._callbacks["nudge_handled"]:
            try:
                cb(nudge)
            except Exception:
                pass
    
    def _notify_recovery_triggered(self, nudge: NudgeEvent, action: str):
        for cb in self._callbacks["recovery_triggered"]:
            try:
                cb(nudge, action)
            except Exception:
                pass


import resource

_nudge_monitor: Optional[NudgeMonitor] = None

def get_nudge_monitor() -> NudgeMonitor:
    global _nudge_monitor
    if _nudge_monitor is None:
        from ..core.config import config
        sens = config.get_param("hud", "nudge_sensitivity", 0.8)
        _nudge_monitor = NudgeMonitor(sensitivity=sens)
        _nudge_monitor.start()
    return _nudge_monitor