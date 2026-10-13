"""
Runtime Sandbox Isolator - On-demand ephemeral container/LXC sandbox manager for unverified code execution
"""
import os
import subprocess
import threading
import time
import uuid
import tempfile
import shutil
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SandboxRuntime(Enum):
    DOCKER = "docker"
    PODMAN = "podman"
    LXC = "lxc"
    FIREJAIL = "firejail"
    BUBBLEWRAP = "bwrap"
    NAMESPACE = "namespace"


class SandboxState(Enum):
    CREATING = "creating"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class SandboxSpec:
    runtime: SandboxRuntime = SandboxRuntime.NAMESPACE
    image: str = "python:3.11-slim"
    command: List[str] = field(default_factory=list)
    working_dir: str = "/workspace"
    environment: Dict[str, str] = field(default_factory=dict)
    volumes: Dict[str, str] = field(default_factory=dict)  # host_path: container_path
    memory_limit: str = "512m"
    cpu_limit: str = "1.0"
    pids_limit: int = 100
    network_mode: str = "none"
    read_only_rootfs: bool = True
    capabilities_drop: List[str] = field(default_factory=lambda: ["ALL"])
    capabilities_add: List[str] = field(default_factory=list)
    tmpfs: Dict[str, str] = field(default_factory=dict)
    ulimits: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    timeout: float = 30.0
    auto_remove: bool = True


@dataclass
class SandboxResult:
    sandbox_id: str
    spec: SandboxSpec
    state: SandboxState
    container_id: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None
    start_time: float = 0.0
    end_time: float = 0.0
    error: Optional[str] = None


class SandboxIsolator:
    def __init__(self, default_runtime: SandboxRuntime = SandboxRuntime.NAMESPACE):
        self.default_runtime = default_runtime
        self._sandboxes: Dict[str, SandboxResult] = {}
        self._lock = threading.RLock()
        self._runtime_available: Dict[SandboxRuntime, bool] = {}
        self._check_runtimes()
    
    def _check_runtimes(self):
        for runtime in SandboxRuntime:
            self._runtime_available[runtime] = self._check_runtime(runtime)
    
    def _check_runtime(self, runtime: SandboxRuntime) -> bool:
        try:
            if runtime == SandboxRuntime.DOCKER:
                subprocess.run(["docker", "version"], capture_output=True, check=True, timeout=5)
            elif runtime == SandboxRuntime.PODMAN:
                subprocess.run(["podman", "version"], capture_output=True, check=True, timeout=5)
            elif runtime == SandboxRuntime.LXC:
                subprocess.run(["lxc", "version"], capture_output=True, check=True, timeout=5)
            elif runtime == SandboxRuntime.FIREJAIL:
                subprocess.run(["firejail", "--version"], capture_output=True, check=True, timeout=5)
            elif runtime == SandboxRuntime.BUBBLEWRAP:
                subprocess.run(["bwrap", "--version"], capture_output=True, check=True, timeout=5)
            elif runtime == SandboxRuntime.NAMESPACE:
                return True  # Always available on Linux
            return True
        except Exception:
            return False
    
    def get_available_runtime(self, preferred: Optional[SandboxRuntime] = None) -> SandboxRuntime:
        if preferred and self._runtime_available.get(preferred, False):
            return preferred
        for runtime in [SandboxRuntime.BUBBLEWRAP, SandboxRuntime.FIREJAIL, 
                        SandboxRuntime.DOCKER, SandboxRuntime.PODMAN, 
                        SandboxRuntime.LXC, SandboxRuntime.NAMESPACE]:
            if self._runtime_available.get(runtime, False):
                return runtime
        return SandboxRuntime.NAMESPACE
    
    def create_sandbox(self, spec: SandboxSpec) -> str:
        sandbox_id = str(uuid.uuid4())[:8]
        
        runtime = self.get_available_runtime(spec.runtime)
        spec.runtime = runtime
        
        result = SandboxResult(
            sandbox_id=sandbox_id,
            spec=spec,
            state=SandboxState.CREATING,
            start_time=time.time()
        )
        
        with self._lock:
            self._sandboxes[sandbox_id] = result
        
        thread = threading.Thread(target=self._run_sandbox, args=(sandbox_id,), daemon=True)
        thread.start()
        
        return sandbox_id
    
    def _run_sandbox(self, sandbox_id: str):
        with self._lock:
            result = self._sandboxes.get(sandbox_id)
            if not result:
                return
            spec = result.spec
        
        try:
            if spec.runtime == SandboxRuntime.DOCKER:
                self._run_docker(sandbox_id, result)
            elif spec.runtime == SandboxRuntime.PODMAN:
                self._run_podman(sandbox_id, result)
            elif spec.runtime == SandboxRuntime.BUBBLEWRAP:
                self._run_bubblewrap(sandbox_id, result)
            elif spec.runtime == SandboxRuntime.FIREJAIL:
                self._run_firejail(sandbox_id, result)
            elif spec.runtime == SandboxRuntime.NAMESPACE:
                self._run_namespace(sandbox_id, result)
            else:
                raise RuntimeError(f"Unsupported runtime: {spec.runtime}")
        except Exception as e:
            with self._lock:
                result.state = SandboxState.ERROR
                result.error = str(e)
                result.end_time = time.time()
    
    def _run_docker(self, sandbox_id: str, result: SandboxResult):
        spec = result.spec
        
        cmd = ["docker", "run", "--rm" if spec.auto_remove else "", "-i"]
        
        cmd.extend(["--memory", spec.memory_limit])
        cmd.extend(["--cpus", spec.cpu_limit])
        cmd.extend(["--pids-limit", str(spec.pids_limit)])
        cmd.extend(["--network", spec.network_mode])
        
        if spec.read_only_rootfs:
            cmd.append("--read-only")
        
        for cap in spec.capabilities_drop:
            cmd.extend(["--cap-drop", cap])
        for cap in spec.capabilities_add:
            cmd.extend(["--cap-add", cap])
        
        for host_path, container_path in spec.volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])
        
        for container_path, options in spec.tmpfs.items():
            cmd.extend(["--tmpfs", f"{container_path}:{options}"])
        
        for name, (soft, hard) in spec.ulimits.items():
            cmd.extend(["--ulimit", f"{name}={soft}:{hard}"])
        
        for key, value in spec.environment.items():
            cmd.extend(["-e", f"{key}={value}"])
        
        cmd.extend(["-w", spec.working_dir])
        cmd.append(spec.image)
        cmd.extend(spec.command)
        
        cmd = [c for c in cmd if c]
        
        with self._lock:
            result.state = SandboxState.RUNNING
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=spec.timeout
            )
            result.stdout = proc.stdout
            result.stderr = proc.stderr
            result.returncode = proc.returncode
        except subprocess.TimeoutExpired as e:
            result.stdout = e.stdout or ""
            result.stderr = e.stderr or ""
            result.returncode = -1
            result.error = "Timeout"
        except Exception as e:
            result.error = str(e)
            result.returncode = -1
        finally:
            with self._lock:
                result.state = SandboxState.STOPPED
                result.end_time = time.time()
    
    def _run_podman(self, sandbox_id: str, result: SandboxResult):
        # Podman CLI is compatible with Docker
        spec = result.spec
        spec.runtime = SandboxRuntime.DOCKER
        self._run_docker(sandbox_id, result)
        spec.runtime = SandboxRuntime.PODMAN
    
    def _run_bubblewrap(self, sandbox_id: str, result: SandboxResult):
        spec = result.spec
        
        cmd = ["bwrap", "--die-with-parent"]
        
        cmd.extend(["--ro-bind", "/usr", "/usr"])
        cmd.extend(["--ro-bind", "/lib", "/lib"])
        cmd.extend(["--ro-bind", "/lib64", "/lib64"])
        cmd.extend(["--ro-bind", "/bin", "/bin"])
        cmd.extend(["--ro-bind", "/sbin", "/sbin"])
        cmd.extend(["--ro-bind", "/etc", "/etc"])
        
        if not spec.read_only_rootfs:
            cmd.extend(["--bind", "/", "/"])
        
        for host_path, container_path in spec.volumes.items():
            cmd.extend(["--bind", host_path, container_path])
        
        for container_path, options in spec.tmpfs.items():
            cmd.extend(["--tmpfs", container_path])
        
        cmd.extend(["--proc", "/proc"])
        cmd.extend(["--dev", "/dev"])
        cmd.extend(["--chdir", spec.working_dir])
        
        for key, value in spec.environment.items():
            cmd.extend(["--setenv", key, value])
        
        cmd.extend(["--unshare-all"])
        cmd.extend(["--new-session"])
        
        cmd.extend(spec.command)
        
        with self._lock:
            result.state = SandboxState.RUNNING
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=spec.timeout
            )
            result.stdout = proc.stdout
            result.stderr = proc.stderr
            result.returncode = proc.returncode
        except subprocess.TimeoutExpired as e:
            result.stdout = e.stdout or ""
            result.stderr = e.stderr or ""
            result.returncode = -1
            result.error = "Timeout"
        except Exception as e:
            result.error = str(e)
            result.returncode = -1
        finally:
            with self._lock:
                result.state = SandboxState.STOPPED
                result.end_time = time.time()
    
    def _run_firejail(self, sandbox_id: str, result: SandboxResult):
        spec = result.spec
        
        cmd = ["firejail", "--quiet", "--noprofile"]
        
        if spec.read_only_rootfs:
            cmd.append("--noroot")
        
        cmd.extend(["--private", "--private-dev"])
        cmd.extend(["--net=none"])
        cmd.extend(["--cpu=" + spec.cpu_limit])
        cmd.extend(["--rlimit=cpu=" + str(int(float(spec.cpu_limit) * spec.timeout))])
        
        for host_path, container_path in spec.volumes.items():
            cmd.extend(["--whitelist=" + host_path])
        
        for key, value in spec.environment.items():
            cmd.extend(["--env=" + f"{key}={value}"])
        
        cmd.extend(["--chdir", spec.working_dir])
        cmd.extend(spec.command)
        
        with self._lock:
            result.state = SandboxState.RUNNING
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=spec.timeout
            )
            result.stdout = proc.stdout
            result.stderr = proc.stderr
            result.returncode = proc.returncode
        except subprocess.TimeoutExpired as e:
            result.stdout = e.stdout or ""
            result.stderr = e.stderr or ""
            result.returncode = -1
            result.error = "Timeout"
        except Exception as e:
            result.error = str(e)
            result.returncode = -1
        finally:
            with self._lock:
                result.state = SandboxState.STOPPED
                result.end_time = time.time()
    
    def _run_namespace(self, sandbox_id: str, result: SandboxResult):
        # Linux namespace-based isolation using unshare
        spec = result.spec
        
        cmd = ["unshare", "--fork", "--pid", "--mount", "--net", "--uts", "--ipc", "--user", "--map-root-user"]
        
        # Setup mount namespace
        cmd.extend(["--mount-proc"])
        
        for host_path, container_path in spec.volumes.items():
            cmd.extend(["--bind", host_path, container_path])
        
        env = os.environ.copy()
        env.update(spec.environment)
        
        with self._lock:
            result.state = SandboxState.RUNNING
        
        try:
            proc = subprocess.run(
                cmd + spec.command,
                capture_output=True,
                text=True,
                timeout=spec.timeout,
                cwd=spec.working_dir,
                env=env
            )
            result.stdout = proc.stdout
            result.stderr = proc.stderr
            result.returncode = proc.returncode
        except subprocess.TimeoutExpired as e:
            result.stdout = e.stdout or ""
            result.stderr = e.stderr or ""
            result.returncode = -1
            result.error = "Timeout"
        except Exception as e:
            result.error = str(e)
            result.returncode = -1
        finally:
            with self._lock:
                result.state = SandboxState.STOPPED
                result.end_time = time.time()
    
    def execute(self, command: List[str], **kwargs) -> SandboxResult:
        spec = SandboxSpec(command=command, **kwargs)
        sandbox_id = self.create_sandbox(spec)
        return self.wait(sandbox_id)
    
    def wait(self, sandbox_id: str, timeout: Optional[float] = None) -> Optional[SandboxResult]:
        with self._lock:
            result = self._sandboxes.get(sandbox_id)
            if not result:
                return None
        
        start = time.time()
        while result.state in (SandboxState.CREATING, SandboxState.RUNNING):
            if timeout and (time.time() - start) > timeout:
                break
            time.sleep(0.1)
            with self._lock:
                result = self._sandboxes.get(sandbox_id)
        
        return result
    
    def get_result(self, sandbox_id: str) -> Optional[SandboxResult]:
        with self._lock:
            return self._sandboxes.get(sandbox_id)
    
    def list_sandboxes(self, state: Optional[SandboxState] = None) -> List[SandboxResult]:
        with self._lock:
            results = list(self._sandboxes.values())
            if state:
                results = [r for r in results if r.state == state]
            return results
    
    def cleanup(self, sandbox_id: str) -> bool:
        with self._lock:
            result = self._sandboxes.pop(sandbox_id, None)
            return result is not None
    
    def cleanup_all(self):
        with self._lock:
            self._sandboxes.clear()


_sandbox_isolator: Optional[SandboxIsolator] = None

def get_sandbox_isolator() -> SandboxIsolator:
    global _sandbox_isolator
    if _sandbox_isolator is None:
        from ..core.config import config
        default_rt = config.get_param("kernel", "sandbox_runtime", "namespace")
        runtime = SandboxRuntime(default_rt) if default_rt in [r.value for r in SandboxRuntime] else SandboxRuntime.NAMESPACE
        _sandbox_isolator = SandboxIsolator(default_runtime=runtime)
    return _sandbox_isolator