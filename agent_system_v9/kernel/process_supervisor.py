"""
Process Subshell Supervisor - Spawn, monitor, signal, terminate background OS processes
"""
import subprocess
import threading
import time
import signal
import os
import uuid
from typing import Dict, List, Optional, Callable, Any, IO
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import select


class ProcessState(Enum):
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    TERMINATED = "terminated"
    FAILED = "failed"
    ZOMBIE = "zombie"


@dataclass
class ProcessSpec:
    command: List[str]
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    stdin_data: Optional[str] = None
    timeout: float = 30.0
    capture_output: bool = True
    shell: bool = False
    preexec_fn: Optional[Callable] = None
    start_new_session: bool = True
    resource_limits: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessResult:
    process_id: str
    spec: ProcessSpec
    state: ProcessState
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    pid: Optional[int] = None
    error: Optional[str] = None


class ProcessSupervisor:
    def __init__(self, max_processes: int = 100):
        self.max_processes = max_processes
        self._processes: Dict[str, ProcessResult] = {}
        self._running_processes: Dict[str, subprocess.Popen] = {}
        self._output_buffers: Dict[str, Dict[str, deque]] = {}
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._callbacks: Dict[str, List[Callable]] = {
            "stdout": [],
            "stderr": [],
            "exit": [],
            "state_change": []
        }
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop(self):
        self._running = False
        self.terminate_all()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
    
    def spawn(self, spec: ProcessSpec) -> str:
        with self._lock:
            if len(self._running_processes) >= self.max_processes:
                raise RuntimeError("Maximum process limit reached")
            
            process_id = str(uuid.uuid4())[:8]
            result = ProcessResult(
                process_id=process_id,
                spec=spec,
                state=ProcessState.PENDING,
                start_time=time.time()
            )
            self._processes[process_id] = result
            self._output_buffers[process_id] = {"stdout": deque(maxlen=10000), "stderr": deque(maxlen=10000)}
        
        thread = threading.Thread(target=self._run_process, args=(process_id, spec), daemon=True)
        thread.start()
        return process_id
    
    def _run_process(self, process_id: str, spec: ProcessSpec):
        with self._lock:
            self._processes[process_id].state = ProcessState.STARTING
            self._notify_state_change(process_id, ProcessState.STARTING)
        
        env = os.environ.copy()
        env.update(spec.env)
        
        try:
            proc = subprocess.Popen(
                spec.command,
                env=env,
                cwd=spec.cwd,
                stdin=subprocess.PIPE if spec.stdin_data else None,
                stdout=subprocess.PIPE if spec.capture_output else None,
                stderr=subprocess.PIPE if spec.capture_output else None,
                shell=spec.shell,
                preexec_fn=spec.preexec_fn,
                start_new_session=spec.start_new_session,
                bufsize=0
            )
        except Exception as e:
            with self._lock:
                self._processes[process_id].state = ProcessState.FAILED
                self._processes[process_id].error = str(e)
                self._processes[process_id].end_time = time.time()
                self._notify_state_change(process_id, ProcessState.FAILED)
            return
        
        with self._lock:
            self._running_processes[process_id] = proc
            self._processes[process_id].pid = proc.pid
            self._processes[process_id].state = ProcessState.RUNNING
            self._notify_state_change(process_id, ProcessState.RUNNING)
        
        if spec.stdin_data and proc.stdin:
            try:
                proc.stdin.write(spec.stdin_data.encode())
                proc.stdin.close()
            except Exception:
                pass
        
        stdout_data = []
        stderr_data = []
        
        try:
            if spec.capture_output and proc.stdout and proc.stderr:
                stdout_data, stderr_data = self._read_output(process_id, proc, spec.timeout)
            else:
                proc.wait(timeout=spec.timeout)
        except subprocess.TimeoutExpired:
            self.terminate(process_id, force=True)
            with self._lock:
                self._processes[process_id].error = "Process timeout"
        except Exception as e:
            with self._lock:
                self._processes[process_id].error = str(e)
        finally:
            self._cleanup_process(process_id, proc, stdout_data, stderr_data)
    
    def _read_output(self, process_id: str, proc: subprocess.Popen, timeout: float) -> tuple:
        stdout_chunks = []
        stderr_chunks = []
        start_time = time.time()
        
        stdout_fd = proc.stdout.fileno() if proc.stdout else None
        stderr_fd = proc.stderr.fileno() if proc.stderr else None
        
        while proc.poll() is None:
            if time.time() - start_time > timeout:
                break
            
            ready, _, _ = select.select(
                [f for f in [stdout_fd, stderr_fd] if f is not None], [], [], 0.1
            )
            
            for fd in ready:
                if fd == stdout_fd:
                    chunk = os.read(fd, 8192)
                    if chunk:
                        text = chunk.decode('utf-8', errors='replace')
                        stdout_chunks.append(text)
                        self._output_buffers[process_id]["stdout"].append(text)
                        self._notify_stdout(process_id, text)
                elif fd == stderr_fd:
                    chunk = os.read(fd, 8192)
                    if chunk:
                        text = chunk.decode('utf-8', errors='replace')
                        stderr_chunks.append(text)
                        self._output_buffers[process_id]["stderr"].append(text)
                        self._notify_stderr(process_id, text)
        
        return stdout_chunks, stderr_chunks
    
    def _cleanup_process(self, process_id: str, proc: subprocess.Popen, 
                         stdout_data: List[str], stderr_data: List[str]):
        returncode = proc.poll()
        if returncode is None:
            try:
                returncode = proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                returncode = -9
        
        with self._lock:
            self._running_processes.pop(process_id, None)
            result = self._processes[process_id]
            result.returncode = returncode
            result.stdout = "".join(stdout_data)
            result.stderr = "".join(stderr_data)
            result.end_time = time.time()
            
            if returncode == 0:
                result.state = ProcessState.TERMINATED
            elif returncode < 0:
                result.state = ProcessState.TERMINATED
            else:
                result.state = ProcessState.FAILED
            
            self._notify_state_change(process_id, result.state)
            self._notify_exit(process_id, returncode)
    
    def terminate(self, process_id: str, force: bool = False) -> bool:
        with self._lock:
            proc = self._running_processes.get(process_id)
            if not proc:
                return False
            
            self._processes[process_id].state = ProcessState.STOPPING
            self._notify_state_change(process_id, ProcessState.STOPPING)
        
        try:
            if force:
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    try:
                        proc.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return True
        except Exception:
            return False
    
    def terminate_all(self, force: bool = False):
        with self._lock:
            process_ids = list(self._running_processes.keys())
        for pid in process_ids:
            self.terminate(pid, force)
    
    def signal(self, process_id: str, sig: int) -> bool:
        with self._lock:
            proc = self._running_processes.get(process_id)
            if not proc or proc.poll() is not None:
                return False
        
        try:
            os.killpg(os.getpgid(proc.pid), sig)
            return True
        except Exception:
            return False
    
    def get_result(self, process_id: str) -> Optional[ProcessResult]:
        with self._lock:
            return self._processes.get(process_id)
    
    def get_output(self, process_id: str, stream: str = "stdout") -> str:
        with self._lock:
            buffer = self._output_buffers.get(process_id, {}).get(stream, deque())
            return "".join(buffer)
    
    def list_processes(self, state: Optional[ProcessState] = None) -> List[ProcessResult]:
        with self._lock:
            results = list(self._processes.values())
            if state:
                results = [r for r in results if r.state == state]
            return results
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _notify_stdout(self, process_id: str, data: str):
        for cb in self._callbacks["stdout"]:
            try:
                cb(process_id, data)
            except Exception:
                pass
    
    def _notify_stderr(self, process_id: str, data: str):
        for cb in self._callbacks["stderr"]:
            try:
                cb(process_id, data)
            except Exception:
                pass
    
    def _notify_exit(self, process_id: str, returncode: int):
        for cb in self._callbacks["exit"]:
            try:
                cb(process_id, returncode)
            except Exception:
                pass
    
    def _notify_state_change(self, process_id: str, state: ProcessState):
        for cb in self._callbacks["state_change"]:
            try:
                cb(process_id, state)
            except Exception:
                pass
    
    def _monitor_loop(self):
        while self._running:
            time.sleep(1.0)
            with self._lock:
                for pid, proc in list(self._running_processes.items()):
                    if proc.poll() is not None and self._processes[pid].state == ProcessState.RUNNING:
                        self._cleanup_process(pid, proc, [], [])


_process_supervisor: Optional[ProcessSupervisor] = None

def get_process_supervisor() -> ProcessSupervisor:
    global _process_supervisor
    if _process_supervisor is None:
        from ..core.config import config
        max_procs = config.get_param("kernel", "max_processes", 100)
        _process_supervisor = ProcessSupervisor(max_processes=max_procs)
        _process_supervisor.start()
    return _process_supervisor