"""
Dynamic Non-Blocking Reactive Callbacks - Event-driven watcher executing immediate callbacks on I/O changes
"""
import asyncio
import pathlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(Enum):
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    FILE_MOVED = "file_moved"
    PROCESS_STARTED = "process_started"
    PROCESS_EXITED = "process_exited"
    NETWORK_CONNECT = "network_connect"
    NETWORK_DISCONNECT = "network_disconnect"
    CUSTOM = "custom"


@dataclass
class CallbackRegistration:
    callback_id: str
    event_types: set[EventType]
    callback: Callable
    filter_pattern: str = ""
    once: bool = False
    priority: int = 0
    active: bool = True


class ReactiveCallbackEngine:
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self._registrations: dict[str, CallbackRegistration] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._lock = threading.RLock()
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._file_watchers: dict[str, threading.Thread] = {}
        self._watched_paths: set[str] = set()

    def start(self):
        if self._running:
            return
        self._running = True
        self._loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._loop_thread.start()

    def stop(self):
        self._running = False
        for watcher in self._file_watchers.values():
            watcher.join(timeout=1.0)
        if self._loop and self._worker_task:
            self._worker_task.cancel()
        if self._loop_thread:
            self._loop_thread.join(timeout=5.0)

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._worker_task = self._loop.create_task(self._process_events())
        self._loop.run_forever()

    async def _process_events(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                await self._dispatch_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception:
                pass

    async def _dispatch_event(self, event: dict[str, Any]):
        event_type = EventType(event.get("type", "custom"))
        matching_callbacks = []

        with self._lock:
            for reg in self._registrations.values():
                if reg.active and event_type in reg.event_types:
                    if not reg.filter_pattern or reg.filter_pattern in event.get("path", ""):
                        matching_callbacks.append(reg)

        # Sort by priority
        matching_callbacks.sort(key=lambda c: -c.priority)

        for reg in matching_callbacks:
            try:
                if asyncio.iscoroutinefunction(reg.callback):
                    await reg.callback(event)
                else:
                    reg.callback(event)

                if reg.once:
                    reg.active = False
            except Exception:
                pass

    def register_callback(self, event_types: list[EventType], callback: Callable,
                         filter_pattern: str = "", once: bool = False, priority: int = 0) -> str:
        callback_id = f"cb_{hash(f'{callback}{time.time()}') % 1000000}"

        reg = CallbackRegistration(
            callback_id=callback_id,
            event_types=set(event_types),
            callback=callback,
            filter_pattern=filter_pattern,
            once=once,
            priority=priority
        )

        with self._lock:
            self._registrations[callback_id] = reg

        return callback_id

    def unregister_callback(self, callback_id: str) -> bool:
        with self._lock:
            if callback_id in self._registrations:
                del self._registrations[callback_id]
                return True
        return False

    def emit(self, event_type: EventType, data: dict[str, Any]):
        event = {"type": event_type, "timestamp": time.time(), **data}

        if self._loop and self._running:
            try:
                asyncio.run_coroutine_threadsafe(self._event_queue.put(event), self._loop)
            except Exception:
                pass

    def watch_path(self, path: str, event_types: list[EventType] = None,
                  callback: Callable = None) -> str:
        if path in self._watched_paths:
            return path

        self._watched_paths.add(path)
        event_types = event_types or [EventType.FILE_MODIFIED, EventType.FILE_CREATED, EventType.FILE_DELETED]

        def watcher():
            last_mtimes = {}
            while self._running and path in self._watched_paths:
                try:
                    if pathlib.Path(path).exists():
                        mtime = pathlib.Path(path).stat().st_mtime
                        if path not in last_mtimes:
                            last_mtimes[path] = mtime
                        elif mtime > last_mtimes[path]:
                            self.emit(EventType.FILE_MODIFIED, {"path": path, "mtime": mtime})
                            last_mtimes[path] = mtime
                    elif path in last_mtimes:
                        self.emit(EventType.FILE_DELETED, {"path": path})
                        del last_mtimes[path]
                except Exception:
                    pass
                time.sleep(0.5)

        thread = threading.Thread(target=watcher, daemon=True)
        self._file_watchers[path] = thread
        thread.start()

        if callback:
            self.register_callback(event_types, callback, filter_pattern=path)

        return path

    def unwatch_path(self, path: str):
        self._watched_paths.discard(path)


_reactive_engine: ReactiveCallbackEngine | None = None


def get_reactive_engine() -> ReactiveCallbackEngine:
    global _reactive_engine
    if _reactive_engine is None:
        _reactive_engine = ReactiveCallbackEngine()
        _reactive_engine.start()
    return _reactive_engine
