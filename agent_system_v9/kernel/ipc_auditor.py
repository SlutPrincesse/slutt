"""
IPC Pipe Auditor - Inspect standard input/output pipes to detect hangs, deadlocks, and silent freezes
"""
import fcntl
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class PipeState(Enum):
    OPEN = "open"
    READING = "reading"
    WRITING = "writing"
    BLOCKED_READ = "blocked_read"
    BLOCKED_WRITE = "blocked_write"
    CLOSED = "closed"
    BROKEN = "broken"
    SILENT = "silent"


@dataclass
class PipeInfo:
    fd: int
    name: str
    mode: str  # "r", "w", "rw"
    state: PipeState = PipeState.OPEN
    bytes_read: int = 0
    bytes_written: int = 0
    last_activity: float = field(default_factory=time.time)
    read_blocked_since: float | None = None
    write_blocked_since: float | None = None
    silent_since: float | None = None
    peer_pid: int | None = None


class IPCAuditor:
    def __init__(self, hang_threshold: float = 5.0, silent_threshold: float = 30.0):
        self.hang_threshold = hang_threshold
        self.silent_threshold = silent_threshold
        self._pipes: dict[int, PipeInfo] = {}
        self._pipe_names: dict[str, int] = {}
        self._lock = threading.RLock()
        self._monitor_thread: threading.Thread | None = None
        self._running = False
        self._callbacks: dict[str, list[Callable]] = {
            "hang_detected": [],
            "silent_detected": [],
            "deadlock_detected": [],
            "pipe_closed": [],
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
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)

    def register_pipe(self, fd: int, name: str, mode: str = "rw", peer_pid: int | None = None) -> int:
        with self._lock:
            if fd in self._pipes:
                return fd

            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            pipe_info = PipeInfo(
                fd=fd,
                name=name,
                mode=mode,
                peer_pid=peer_pid
            )
            self._pipes[fd] = pipe_info
            self._pipe_names[name] = fd
            return fd

    def unregister_pipe(self, fd: int) -> bool:
        with self._lock:
            pipe_info = self._pipes.pop(fd, None)
            if pipe_info:
                self._pipe_names.pop(pipe_info.name, None)
                pipe_info.state = PipeState.CLOSED
                self._notify_pipe_closed(fd, pipe_info)
                return True
            return False

    def record_read(self, fd: int, bytes_count: int):
        with self._lock:
            pipe_info = self._pipes.get(fd)
            if pipe_info:
                pipe_info.bytes_read += bytes_count
                pipe_info.last_activity = time.time()
                pipe_info.read_blocked_since = None
                pipe_info.silent_since = None
                if pipe_info.state in (PipeState.BLOCKED_READ, PipeState.SILENT):
                    pipe_info.state = PipeState.OPEN
                    self._notify_state_change(fd, pipe_info.state)

    def record_write(self, fd: int, bytes_count: int):
        with self._lock:
            pipe_info = self._pipes.get(fd)
            if pipe_info:
                pipe_info.bytes_written += bytes_count
                pipe_info.last_activity = time.time()
                pipe_info.write_blocked_since = None
                pipe_info.silent_since = None
                if pipe_info.state in (PipeState.BLOCKED_WRITE, PipeState.SILENT):
                    pipe_info.state = PipeState.OPEN
                    self._notify_state_change(fd, pipe_info.state)

    def record_blocked_read(self, fd: int):
        with self._lock:
            pipe_info = self._pipes.get(fd)
            if pipe_info:
                if pipe_info.read_blocked_since is None:
                    pipe_info.read_blocked_since = time.time()
                pipe_info.state = PipeState.BLOCKED_READ
                self._notify_state_change(fd, PipeState.BLOCKED_READ)

    def record_blocked_write(self, fd: int):
        with self._lock:
            pipe_info = self._pipes.get(fd)
            if pipe_info:
                if pipe_info.write_blocked_since is None:
                    pipe_info.write_blocked_since = time.time()
                pipe_info.state = PipeState.BLOCKED_WRITE
                self._notify_state_change(fd, PipeState.BLOCKED_WRITE)

    def get_pipe_info(self, fd: int) -> PipeInfo | None:
        with self._lock:
            return self._pipes.get(fd)

    def get_pipe_by_name(self, name: str) -> PipeInfo | None:
        with self._lock:
            fd = self._pipe_names.get(name)
            if fd is not None:
                return self._pipes.get(fd)
            return None

    def list_pipes(self, state: PipeState | None = None) -> list[PipeInfo]:
        with self._lock:
            pipes = list(self._pipes.values())
            if state:
                pipes = [p for p in pipes if p.state == state]
            return pipes

    def check_hangs(self) -> list[tuple[int, PipeInfo, str]]:
        hangs = []
        now = time.time()
        with self._lock:
            for fd, pipe_info in self._pipes.items():
                if pipe_info.read_blocked_since and (now - pipe_info.read_blocked_since) > self.hang_threshold:
                    hangs.append((fd, pipe_info, "read_hang"))
                if pipe_info.write_blocked_since and (now - pipe_info.write_blocked_since) > self.hang_threshold:
                    hangs.append((fd, pipe_info, "write_hang"))
        return hangs

    def check_silent(self) -> list[tuple[int, PipeInfo]]:
        silent = []
        now = time.time()
        with self._lock:
            for fd, pipe_info in self._pipes.items():
                if (now - pipe_info.last_activity) > self.silent_threshold:
                    if pipe_info.silent_since is None:
                        pipe_info.silent_since = now
                    pipe_info.state = PipeState.SILENT
                    silent.append((fd, pipe_info))
        return silent

    def detect_deadlocks(self) -> list[tuple[int, int]]:
        deadlocks = []
        with self._lock:
            blocked_readers = [fd for fd, p in self._pipes.items() if p.state == PipeState.BLOCKED_READ]
            blocked_writers = [fd for fd, p in self._pipes.items() if p.state == PipeState.BLOCKED_WRITE]

            for rfd in blocked_readers:
                rpipe = self._pipes[rfd]
                for wfd in blocked_writers:
                    wpipe = self._pipes[wfd]
                    if rpipe.peer_pid == wpipe.peer_pid:
                        deadlocks.append((rfd, wfd))
        return deadlocks

    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _notify_hang(self, fd: int, pipe_info: PipeInfo, hang_type: str):
        for cb in self._callbacks["hang_detected"]:
            try:
                cb(fd, pipe_info, hang_type)
            except Exception:
                pass

    def _notify_silent(self, fd: int, pipe_info: PipeInfo):
        for cb in self._callbacks["silent_detected"]:
            try:
                cb(fd, pipe_info)
            except Exception:
                pass

    def _notify_deadlock(self, fd1: int, fd2: int):
        for cb in self._callbacks["deadlock_detected"]:
            try:
                cb(fd1, fd2)
            except Exception:
                pass

    def _notify_pipe_closed(self, fd: int, pipe_info: PipeInfo):
        for cb in self._callbacks["pipe_closed"]:
            try:
                cb(fd, pipe_info)
            except Exception:
                pass

    def _notify_state_change(self, fd: int, state: PipeState):
        for cb in self._callbacks["state_change"]:
            try:
                cb(fd, state)
            except Exception:
                pass

    def _monitor_loop(self):
        while self._running:
            time.sleep(0.5)

            hangs = self.check_hangs()
            for fd, pipe_info, hang_type in hangs:
                self._notify_hang(fd, pipe_info, hang_type)

            silent = self.check_silent()
            for fd, pipe_info in silent:
                self._notify_silent(fd, pipe_info)

            deadlocks = self.detect_deadlocks()
            for fd1, fd2 in deadlocks:
                self._notify_deadlock(fd1, fd2)


_ipc_auditor: IPCAuditor | None = None


def get_ipc_auditor() -> IPCAuditor:
    global _ipc_auditor
    if _ipc_auditor is None:
        _ipc_auditor = IPCAuditor()
        _ipc_auditor.start()
    return _ipc_auditor
