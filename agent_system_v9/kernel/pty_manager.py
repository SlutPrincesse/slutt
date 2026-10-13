"""
Virtual pTY Manager - Full-duplex interactive terminal multiplexer for CLI automation
"""
import fcntl
import os
import pty
import select
import signal
import struct
import termios
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class PTYState(Enum):
    CREATED = "created"
    ACTIVE = "active"
    RESIZED = "resized"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class PTYSession:
    session_id: str
    pid: int
    fd: int
    command: list[str]
    cwd: str
    env: dict[str, str]
    cols: int = 80
    rows: int = 24
    state: PTYState = PTYState.CREATED
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    output_buffer: deque = field(default_factory=lambda: deque(maxlen=50000))


class PTYManager:
    def __init__(self, buffer_size: int = 8192):
        self.buffer_size = buffer_size
        self._sessions: dict[str, PTYSession] = {}
        self._session_threads: dict[str, threading.Thread] = {}
        self._lock = threading.RLock()
        self._running = False
        self._monitor_thread: threading.Thread | None = None
        self._callbacks: dict[str, list[Callable]] = {
            "output": [],
            "exit": [],
            "resize": [],
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
        self.close_all()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)

    def create_session(self, command: list[str], cwd: str | None = None,
                       env: dict[str, str] | None = None,
                       cols: int = 80, rows: int = 24) -> str:
        session_id = str(uuid.uuid4())[:8]

        pid, fd = pty.fork()

        if pid == 0:
            # Child process
            os.environ.update(env or {})
            if cwd:
                os.chdir(cwd)
            os.execvpe(command[0], command, os.environ)
        else:
            # Parent process
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            self._set_window_size(fd, rows, cols)

            session = PTYSession(
                session_id=session_id,
                pid=pid,
                fd=fd,
                command=command,
                cwd=cwd or os.getcwd(),
                env=env or {},
                cols=cols,
                rows=rows,
                state=PTYState.ACTIVE
            )

            with self._lock:
                self._sessions[session_id] = session

            thread = threading.Thread(target=self._read_loop, args=(session_id,), daemon=True)
            self._session_threads[session_id] = thread
            thread.start()

            self._notify_state_change(session_id, PTYState.ACTIVE)
            return session_id

    def _set_window_size(self, fd: int, rows: int, cols: int):
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def _read_loop(self, session_id: str):
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return

        while self._running:
            with self._lock:
                session = self._sessions.get(session_id)
                if not session or session.state != PTYState.ACTIVE:
                    break
                fd = session.fd

            try:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if not ready:
                    continue

                data = os.read(fd, self.buffer_size)
                if not data:
                    break

                text = data.decode('utf-8', errors='replace')
                session.last_activity = time.time()
                session.output_buffer.append(text)

                self._notify_output(session_id, text)

            except OSError:
                break
            except Exception:
                break

        self._cleanup_session(session_id)

    def write(self, session_id: str, data: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session.state != PTYState.ACTIVE:
                return False
            fd = session.fd

        try:
            os.write(fd, data.encode('utf-8'))
            return True
        except Exception:
            return False

    def resize(self, session_id: str, cols: int, rows: int) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            session.cols = cols
            session.rows = rows

            if session.state == PTYState.ACTIVE:
                self._set_window_size(session.fd, rows, cols)
                session.state = PTYState.RESIZED
                self._notify_resize(session_id, cols, rows)
                session.state = PTYState.ACTIVE
            return True

    def send_signal(self, session_id: str, sig: int) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            pid = session.pid

        try:
            os.kill(pid, sig)
            return True
        except Exception:
            return False

    def close(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return False

            session.state = PTYState.CLOSED
            fd = session.fd
            pid = session.pid

        try:
            os.close(fd)
        except Exception:
            pass

        try:
            os.kill(pid, signal.SIGHUP)
            os.waitpid(pid, os.WNOHANG)
        except Exception:
            pass

        self._session_threads.pop(session_id, None)
        self._notify_state_change(session_id, PTYState.CLOSED)
        self._notify_exit(session_id, 0)
        return True

    def close_all(self):
        with self._lock:
            session_ids = list(self._sessions.keys())
        for sid in session_ids:
            self.close(sid)

    def get_session(self, session_id: str) -> PTYSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def get_output(self, session_id: str, lines: int | None = None) -> str:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return ""
            if lines:
                return "".join(list(session.output_buffer)[-lines:])
            return "".join(session.output_buffer)

    def list_sessions(self) -> list[PTYSession]:
        with self._lock:
            return list(self._sessions.values())

    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _notify_output(self, session_id: str, data: str):
        for cb in self._callbacks["output"]:
            try:
                cb(session_id, data)
            except Exception:
                pass

    def _notify_exit(self, session_id: str, code: int):
        for cb in self._callbacks["exit"]:
            try:
                cb(session_id, code)
            except Exception:
                pass

    def _notify_resize(self, session_id: str, cols: int, rows: int):
        for cb in self._callbacks["resize"]:
            try:
                cb(session_id, cols, rows)
            except Exception:
                pass

    def _notify_state_change(self, session_id: str, state: PTYState):
        for cb in self._callbacks["state_change"]:
            try:
                cb(session_id, state)
            except Exception:
                pass

    def _cleanup_session(self, session_id: str):
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.state = PTYState.CLOSED
        self._notify_state_change(session_id, PTYState.CLOSED)
        self._notify_exit(session_id, -1)

    def _monitor_loop(self):
        while self._running:
            time.sleep(1.0)
            with self._lock:
                for session in self._sessions.values():
                    if session.state == PTYState.ACTIVE:
                        try:
                            os.kill(session.pid, 0)
                        except OSError:
                            session.state = PTYState.ERROR
                            self._notify_state_change(session.session_id, PTYState.ERROR)


_pty_manager: PTYManager | None = None


def get_pty_manager() -> PTYManager:
    global _pty_manager
    if _pty_manager is None:
        from ..core.config import config
        buf_size = config.get_param("kernel", "pty_buffer_size", 8192)
        _pty_manager = PTYManager(buffer_size=buf_size)
        _pty_manager.start()
    return _pty_manager
