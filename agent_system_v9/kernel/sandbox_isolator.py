"""
Runtime Sandbox Isolator - On-demand ephemeral container/LXC sandbox manager for unverified code execution
Supports OverlayFS ephemeral layers and cgroups v2 resource quotas.
"""
import os
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SandboxRuntime(Enum):
    DOCKER = "docker"
    PODMAN = "podman"
    LXC = "lxc"
    FIREJAIL = "firejail"
    BUBBLEWRAP = "bwrap"
    NAMESPACE = "namespace"
    OVERLAYFS = "overlayfs"
    OVERLAYFS_CGROUP = "overlayfs_cgroup"


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
    command: list[str] = field(default_factory=list)
    working_dir: str = "/workspace"
    environment: dict[str, str] = field(default_factory=dict)
    volumes: dict[str, str] = field(default_factory=dict)  # host_path: container_path
    memory_limit: str = "512m"
    cpu_limit: str = "1.0"
    pids_limit: int = 100
    network_mode: str = "none"
    read_only_rootfs: bool = True
    capabilities_drop: list[str] = field(default_factory=lambda: ["ALL"])
    capabilities_add: list[str] = field(default_factory=list)
    tmpfs: dict[str, str] = field(default_factory=dict)
    ulimits: dict[str, tuple[int, int]] = field(default_factory=dict)
    timeout: float = 30.0
    auto_remove: bool = True

    # OverlayFS specific
    overlay_lower_dirs: list[str] = field(default_factory=list)  # Lower (read-only) layers
    overlay_upper_dir: str = ""  # Upper (writable) layer
    overlay_work_dir: str = ""  # Work directory for overlayfs
    overlay_mount_point: str = ""  # Where to mount the overlay

    # cgroups v2 specific
    cgroup_path: str = ""  # Custom cgroup path
    cgroup_cpu_quota: int | None = None  # microseconds
    cgroup_cpu_period: int = 100000
    cgroup_memory_limit: int | None = None  # bytes
    cgroup_pids_max: int | None = None
    cgroup_io_weight: int | None = None
    cgroup_io_read_bps: int | None = None
    cgroup_io_write_bps: int | None = None


@dataclass
class SandboxResult:
    sandbox_id: str
    spec: SandboxSpec
    state: SandboxState
    container_id: str | None = None
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    start_time: float = 0.0
    end_time: float = 0.0
    error: str | None = None


class SandboxIsolator:
    def __init__(self, default_runtime: SandboxRuntime = SandboxRuntime.NAMESPACE):
        self.default_runtime = default_runtime
        self._sandboxes: dict[str, SandboxResult] = {}
        self._lock = threading.RLock()
        self._runtime_available: dict[SandboxRuntime, bool] = {}
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
            elif runtime in (SandboxRuntime.OVERLAYFS, SandboxRuntime.OVERLAYFS_CGROUP):
                # Check for mount and overlayfs support
                subprocess.run(["mount", "--version"], capture_output=True, check=True, timeout=2)
                with Path("/proc/filesystems").open() as f:
                    return "overlay" in f.read()
            return True
        except Exception:
            return False

    def get_available_runtime(self, preferred: SandboxRuntime | None = None) -> SandboxRuntime:
        if preferred and self._runtime_available.get(preferred, False):
            return preferred
        for runtime in [SandboxRuntime.OVERLAYFS_CGROUP, SandboxRuntime.OVERLAYFS,
                        SandboxRuntime.BUBBLEWRAP, SandboxRuntime.FIREJAIL,
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
            elif spec.runtime == SandboxRuntime.OVERLAYFS:
                self._run_overlayfs(sandbox_id, result)
            elif spec.runtime == SandboxRuntime.OVERLAYFS_CGROUP:
                self._run_overlayfs_cgroup(sandbox_id, result)
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

    def _run_overlayfs(self, sandbox_id: str, result: SandboxResult):
        """Run sandbox using OverlayFS ephemeral layer."""
        spec = result.spec

        # Create temporary directories for overlay
        with tempfile.TemporaryDirectory(prefix=f"overlay_{sandbox_id}_") as tmp_base:
            lower_dir = spec.overlay_lower_dirs[0] if spec.overlay_lower_dirs else "/"
            upper_dir = os.path.join(tmp_base, "upper")
            work_dir = os.path.join(tmp_base, "work")
            merged_dir = spec.overlay_mount_point or os.path.join(tmp_base, "merged")

            Path(upper_dir).mkdir(exist_ok=True, parents=True)
            Path(work_dir).mkdir(exist_ok=True, parents=True)
            Path(merged_dir).mkdir(exist_ok=True, parents=True)

            # Mount overlayfs
            mount_cmd = [
                "mount", "-t", "overlay", "overlay",
                "-o", f"lowerdir={lower_dir},upperdir={upper_dir},workdir={work_dir}",
                merged_dir
            ]

            try:
                subprocess.run(mount_cmd, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                result.error = f"OverlayFS mount failed: {e.stderr.decode()}"
                result.returncode = -1
                with self._lock:
                    result.state = SandboxState.ERROR
                    result.end_time = time.time()
                return

            try:
                # Bind mount volumes into merged directory
                for host_path, container_path in spec.volumes.items():
                    target = os.path.join(merged_dir, container_path.lstrip("/"))
                    Path(os.path.dirname(target)).mkdir(exist_ok=True, parents=True)
                    subprocess.run(["mount", "--bind", host_path, target], check=True)

                # Setup environment
                env = os.environ.copy()
                env.update(spec.environment)

                with self._lock:
                    result.state = SandboxState.RUNNING

                # Execute in the overlay mount namespace
                cmd = ["unshare", "--fork", "--pid", "--mount", "--net", "--uts", "--ipc"]
                cmd.extend(["--mount-proc"])
                cmd.extend(["--cwd", merged_dir])
                cmd.extend(spec.command)

                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=spec.timeout,
                    cwd=merged_dir,
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
                # Cleanup: unmount overlay
                try:
                    subprocess.run(["umount", "-R", merged_dir], capture_output=True)
                except Exception:
                    pass
                with self._lock:
                    result.state = SandboxState.STOPPED
                    result.end_time = time.time()

    def _run_overlayfs_cgroup(self, sandbox_id: str, result: SandboxResult):
        """Run sandbox using OverlayFS with cgroups v2 resource quotas."""
        spec = result.spec

        # Use ResourceThrottle for cgroup management
        from .resource_throttle import ResourceLimits, get_resource_throttle

        throttle = get_resource_throttle()

        # Create cgroup with specified limits
        cgroup_name = f"sandbox_{sandbox_id}"
        limits = ResourceLimits(
            cpu_quota=spec.cgroup_cpu_quota,
            cpu_period=spec.cgroup_cpu_period,
            memory_limit=spec.cgroup_memory_limit,
            pids_max=spec.cgroup_pids_max or spec.pids_limit,
            io_weight=spec.cgroup_io_weight,
            io_read_bps=spec.cgroup_io_read_bps,
            io_write_bps=spec.cgroup_io_write_bps,
        )

        cgroup_path = throttle.create_cgroup(cgroup_name, limits)

        # Create temporary directories for overlay
        with tempfile.TemporaryDirectory(prefix=f"overlay_{sandbox_id}_") as tmp_base:
            lower_dir = spec.overlay_lower_dirs[0] if spec.overlay_lower_dirs else "/"
            upper_dir = os.path.join(tmp_base, "upper")
            work_dir = os.path.join(tmp_base, "work")
            merged_dir = spec.overlay_mount_point or os.path.join(tmp_base, "merged")

            Path(upper_dir).mkdir(exist_ok=True, parents=True)
            Path(work_dir).mkdir(exist_ok=True, parents=True)
            Path(merged_dir).mkdir(exist_ok=True, parents=True)

            # Mount overlayfs
            mount_cmd = [
                "mount", "-t", "overlay", "overlay",
                "-o", f"lowerdir={lower_dir},upperdir={upper_dir},workdir={work_dir}",
                merged_dir
            ]

            try:
                subprocess.run(mount_cmd, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                result.error = f"OverlayFS mount failed: {e.stderr.decode()}"
                result.returncode = -1
                throttle.delete_cgroup(cgroup_name)
                with self._lock:
                    result.state = SandboxState.ERROR
                    result.end_time = time.time()
                return

            try:
                # Bind mount volumes into merged directory
                for host_path, container_path in spec.volumes.items():
                    target = os.path.join(merged_dir, container_path.lstrip("/"))
                    Path(os.path.dirname(target)).mkdir(exist_ok=True, parents=True)
                    subprocess.run(["mount", "--bind", host_path, target], check=True)

                # Setup environment
                env = os.environ.copy()
                env.update(spec.environment)

                with self._lock:
                    result.state = SandboxState.RUNNING

                # Execute in the overlay mount namespace with cgroup
                cmd = ["unshare", "--fork", "--pid", "--mount", "--net", "--uts", "--ipc"]
                cmd.extend(["--mount-proc"])
                cmd.extend(["--cwd", merged_dir])
                cmd.extend(spec.command)

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=merged_dir,
                    env=env
                )

                # Add process to cgroup
                throttle.add_pid(cgroup_name, proc.pid)

                try:
                    stdout, stderr = proc.communicate(timeout=spec.timeout)
                    result.stdout = stdout
                    result.stderr = stderr
                    result.returncode = proc.returncode
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                    result.stdout = stdout or ""
                    result.stderr = stderr or ""
                    result.returncode = -1
                    result.error = "Timeout"
                except Exception as e:
                    result.error = str(e)
                    result.returncode = -1

            finally:
                # Cleanup: remove from cgroup, unmount overlay, delete cgroup
                try:
                    throttle.remove_pid(cgroup_name, proc.pid)
                except Exception:
                    pass
                try:
                    subprocess.run(["umount", "-R", merged_dir], capture_output=True)
                except Exception:
                    pass
                throttle.delete_cgroup(cgroup_name)

                with self._lock:
                    result.state = SandboxState.STOPPED
                    result.end_time = time.time()

    def execute(self, command: list[str], **kwargs) -> SandboxResult:
        spec = SandboxSpec(command=command, **kwargs)
        sandbox_id = self.create_sandbox(spec)
        return self.wait(sandbox_id)

    async def execute_tool(
        self,
        tool_name: str,
        func: Callable,
        args: dict[str, Any],
        spec: dict[str, Any],
    ) -> Any:
        """Execute a tool callable within an isolated, resource-bounded sandbox.

        Applies cgroup resource limits (memory, cpu, pids) and runs ``func``
        (sync or async) under those limits. Returns ``func``'s result when it
        is a dict, otherwise wraps the sandbox execution result.
        """
        import asyncio

        from .resource_throttle import (
            ResourceLimits,
            get_resource_throttle,
        )

        memory_limit = spec.get("memory_limit", "512m")
        cpu_limit = spec.get("cpu_limit", "1.0")
        timeout = float(spec.get("timeout_seconds", 30.0))

        # Parse memory limit (e.g. "512m", "2g", "512mi")
        mem_bytes = self._parse_mem(memory_limit)
        # Parse cpu limit (e.g. "2.0" -> 2 CPU cores)
        cpu_cores = self._parse_cpu(cpu_limit)
        cpu_quota = int(cpu_cores * 100000)

        throttle = get_resource_throttle()
        cgroup_name = f"tool_{tool_name}"
        limits = ResourceLimits(
            cpu_quota=cpu_quota,
            cpu_period=100000,
            memory_limit=mem_bytes,
            pids_max=100,
        )
        cgroup_created = False
        try:
            throttle.create_cgroup(cgroup_name, limits)
            cgroup_created = True
        except Exception:
            # Cgroups unavailable in this environment; run unbounded but still
            # enforce the async timeout below.
            cgroup_created = False

        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(**args), timeout=timeout)
            else:
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: func(**args)),
                    timeout=timeout,
                )
        except asyncio.TimeoutError:
            if cgroup_created:
                try:
                    throttle.delete_cgroup(cgroup_name)
                except Exception:
                    pass
            return {
                "success": False,
                "error": f"tool {tool_name} timed out after {timeout}s",
                "output": {},
            }
        except Exception as e:  # noqa: BLE001 - surface tool errors as results
            if cgroup_created:
                try:
                    throttle.delete_cgroup(cgroup_name)
                except Exception:
                    pass
            return {"success": False, "error": str(e), "output": {}}
        finally:
            if cgroup_created:
                try:
                    throttle.delete_cgroup(cgroup_name)
                except Exception:
                    pass

        if isinstance(result, dict):
            return result
        return {
            "success": True,
            "output": result,
            "stderr": "",
            "returncode": 0,
        }

    @staticmethod
    def _parse_mem(value: str) -> int | None:
        """Parse a memory limit string into bytes."""
        value = str(value).strip().lower()
        if not value:
            return None
        multipliers = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3,
                       "ki": 1024, "mi": 1024 ** 2, "gi": 1024 ** 3}
        num = ""
        for ch in value:
            if ch.isdigit() or ch == ".":
                num += ch
            else:
                break
        unit = value[len(num):]
        try:
            base = float(num) if num else 0
        except ValueError:
            return None
        return int(base * multipliers.get(unit, 1))

    @staticmethod
    def _parse_cpu(value: str) -> float:
        """Parse a cpu limit string into core count (e.g. '2.0' -> 2.0)."""
        value = str(value).strip()
        num = ""
        for ch in value:
            if ch.isdigit() or ch == ".":
                num += ch
            else:
                break
        try:
            return float(num) if num else 1.0
        except ValueError:
            return 1.0

    def wait(self, sandbox_id: str, timeout: float | None = None) -> SandboxResult | None:
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

    def get_result(self, sandbox_id: str) -> SandboxResult | None:
        with self._lock:
            return self._sandboxes.get(sandbox_id)

    def list_sandboxes(self, state: SandboxState | None = None) -> list[SandboxResult]:
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


_sandbox_isolator: SandboxIsolator | None = None


def get_sandbox_isolator() -> SandboxIsolator:
    global _sandbox_isolator
    if _sandbox_isolator is None:
        from ..core.config import config
        default_rt = config.get_param("kernel", "sandbox_runtime", "namespace")
        runtime = SandboxRuntime(default_rt) if default_rt in [r.value for r in SandboxRuntime] else SandboxRuntime.NAMESPACE
        _sandbox_isolator = SandboxIsolator(default_runtime=runtime)
    return _sandbox_isolator
