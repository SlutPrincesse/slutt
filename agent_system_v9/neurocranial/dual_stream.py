"""
Dual-Stream Data Splitter - Directs logs/telemetry to background (right) and task trees to active focus (left)
"""
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class StreamType(Enum):
    TASK = "task"           # Left hemisphere - active task execution
    TELEMETRY = "telemetry"  # Right hemisphere - logging, metrics
    MEMORY = "memory"       # Right hemisphere - memory operations
    AUDIT = "audit"         # Right hemisphere - audit trails
    CONTROL = "control"     # Left hemisphere - control flow
    BRIDGE = "bridge"       # Cross-hemisphere


@dataclass
class StreamConfig:
    stream_type: StreamType
    target_hemisphere: str  # "left" or "right"
    buffer_size: int = 1000
    flush_interval: float = 1.0
    compression: bool = False
    priority: int = 50


class DualStreamSplitter:
    def __init__(self, split_ratio: float = 0.5):
        self.split_ratio = split_ratio  # Ratio for left/right allocation
        self._streams: dict[StreamType, StreamConfig] = {}
        self._left_buffer: deque = deque(maxlen=10000)
        self._right_buffer: deque = deque(maxlen=10000)
        self._bridge_buffer: deque = deque(maxlen=5000)
        self._lock = threading.RLock()
        self._running = False
        self._flush_thread: threading.Thread | None = None
        self._left_handlers: dict[StreamType, list[Callable]] = {}
        self._right_handlers: dict[StreamType, list[Callable]] = {}
        self._bridge_handlers: list[Callable] = []
        self._stats = {
            "left_events": 0,
            "right_events": 0,
            "bridge_events": 0,
            "dropped": 0
        }

        self._register_default_streams()

    def _register_default_streams(self):
        # Left hemisphere streams (active focus)
        self.register_stream(StreamConfig(
            stream_type=StreamType.TASK,
            target_hemisphere="left",
            buffer_size=5000,
            flush_interval=0.5,
            priority=90
        ))
        self.register_stream(StreamConfig(
            stream_type=StreamType.CONTROL,
            target_hemisphere="left",
            buffer_size=1000,
            flush_interval=0.1,
            priority=100
        ))

        # Right hemisphere streams (background)
        self.register_stream(StreamConfig(
            stream_type=StreamType.TELEMETRY,
            target_hemisphere="right",
            buffer_size=10000,
            flush_interval=2.0,
            compression=True,
            priority=30
        ))
        self.register_stream(StreamConfig(
            stream_type=StreamType.MEMORY,
            target_hemisphere="right",
            buffer_size=5000,
            flush_interval=1.0,
            priority=40
        ))
        self.register_stream(StreamConfig(
            stream_type=StreamType.AUDIT,
            target_hemisphere="right",
            buffer_size=10000,
            flush_interval=1.0,
            compression=True,
            priority=20
        ))

        # Bridge stream
        self.register_stream(StreamConfig(
            stream_type=StreamType.BRIDGE,
            target_hemisphere="bridge",
            buffer_size=2000,
            flush_interval=0.5,
            priority=80
        ))

    def start(self):
        if self._running:
            return
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def stop(self):
        self._running = False
        self._flush_buffers()
        if self._flush_thread:
            self._flush_thread.join(timeout=5.0)

    def register_stream(self, config: StreamConfig):
        with self._lock:
            self._streams[config.stream_type] = config

    def write(self, stream_type: StreamType, data: Any, metadata: dict[str, Any] = None):
        config = self._streams.get(stream_type)
        if not config:
            return

        entry = {
            "stream_type": stream_type.value,
            "data": data,
            "metadata": metadata or {},
            "timestamp": time.time()
        }

        with self._lock:
            if config.target_hemisphere == "left":
                if len(self._left_buffer) >= self._streams[StreamType.TASK].buffer_size:
                    self._stats["dropped"] += 1
                else:
                    self._left_buffer.append(entry)
                    self._stats["left_events"] += 1
            elif config.target_hemisphere == "right":
                if len(self._right_buffer) >= self._streams[StreamType.TELEMETRY].buffer_size:
                    self._stats["dropped"] += 1
                else:
                    self._right_buffer.append(entry)
                    self._stats["right_events"] += 1
            elif len(self._bridge_buffer) >= self._streams[StreamType.BRIDGE].buffer_size:
                self._stats["dropped"] += 1
            else:
                self._bridge_buffer.append(entry)
                self._stats["bridge_events"] += 1

    def read_left(self, count: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return [self._left_buffer.popleft() for _ in range(min(count, len(self._left_buffer)))]

    def read_right(self, count: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return [self._right_buffer.popleft() for _ in range(min(count, len(self._right_buffer)))]

    def read_bridge(self, count: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return [self._bridge_buffer.popleft() for _ in range(min(count, len(self._bridge_buffer)))]

    def peek_left(self, count: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._left_buffer)[:count]

    def peek_right(self, count: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._right_buffer)[:count]

    def register_left_handler(self, stream_type: StreamType, handler: Callable):
        if stream_type not in self._left_handlers:
            self._left_handlers[stream_type] = []
        self._left_handlers[stream_type].append(handler)

    def register_right_handler(self, stream_type: StreamType, handler: Callable):
        if stream_type not in self._right_handlers:
            self._right_handlers[stream_type] = []
        self._right_handlers[stream_type].append(handler)

    def register_bridge_handler(self, handler: Callable):
        self._bridge_handlers.append(handler)

    def _flush_loop(self):
        while self._running:
            time.sleep(0.5)
            self._flush_buffers()

    def _flush_buffers(self):
        with self._lock:
            # Process left hemisphere
            left_events = list(self._left_buffer)
            self._left_buffer.clear()

        for entry in left_events:
            for handler in self._left_handlers.get(StreamType(entry["stream_type"]), []):
                try:
                    handler(entry)
                except Exception:
                    pass

        with self._lock:
            # Process right hemisphere
            right_events = list(self._right_buffer)
            self._right_buffer.clear()

        for entry in right_events:
            for handler in self._right_handlers.get(StreamType(entry["stream_type"]), []):
                try:
                    handler(entry)
                except Exception:
                    pass

        with self._lock:
            # Process bridge
            bridge_events = list(self._bridge_buffer)
            self._bridge_buffer.clear()

        for entry in bridge_events:
            for handler in self._bridge_handlers:
                try:
                    handler(entry)
                except Exception:
                    pass

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                "left_buffer_size": len(self._left_buffer),
                "right_buffer_size": len(self._right_buffer),
                "bridge_buffer_size": len(self._bridge_buffer)
            }

    def get_buffer_sizes(self) -> dict[str, int]:
        with self._lock:
            return {
                "left": len(self._left_buffer),
                "right": len(self._right_buffer),
                "bridge": len(self._bridge_buffer)
            }


_dual_stream_splitter: DualStreamSplitter | None = None


def get_dual_stream_splitter() -> DualStreamSplitter:
    global _dual_stream_splitter
    if _dual_stream_splitter is None:
        from ..core.config import config
        ratio = config.get_param("neurocranial", "stream_split_ratio", 0.5)
        _dual_stream_splitter = DualStreamSplitter(split_ratio=ratio)
        _dual_stream_splitter.start()
    return _dual_stream_splitter
