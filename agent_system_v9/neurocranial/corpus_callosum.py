"""
Corpus Callosum Event Bus - High-speed real-time event bus routing data between foreground and background layers
"""
import asyncio
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Hemisphere(Enum):
    LEFT = "left"      # Active focus, task execution
    RIGHT = "right"    # Background, logging, telemetry
    BRIDGE = "bridge"  # Cross-hemisphere communication


class EventPriority(Enum):
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class Event:
    event_id: str
    event_type: str
    source_hemisphere: Hemisphere
    target_hemisphere: Hemisphere
    payload: Any
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other):
        return self.priority.value > other.priority.value


@dataclass
class EventStream:
    stream_id: str
    source: Hemisphere
    target: Hemisphere
    event_types: set[str]
    active: bool = True
    created_at: float = field(default_factory=time.time)
    event_count: int = 0


class CorpusCallosum:
    def __init__(self, capacity: int = 10000):
        self.capacity = capacity
        self._queues: dict[Hemisphere, asyncio.PriorityQueue] = {
            Hemisphere.LEFT: asyncio.PriorityQueue(maxsize=capacity),
            Hemisphere.RIGHT: asyncio.PriorityQueue(maxsize=capacity),
            Hemisphere.BRIDGE: asyncio.PriorityQueue(maxsize=capacity)
        }
        self._streams: dict[str, EventStream] = {}
        self._subscribers: dict[Hemisphere, dict[str, list[Callable]]] = {
            h: defaultdict(list) for h in Hemisphere
        }
        self._pattern_subscribers: dict[Hemisphere, dict[str, list[Callable]]] = {
            h: defaultdict(list) for h in Hemisphere
        }
        self._lock = threading.RLock()
        self._running = False
        self._worker_tasks: dict[Hemisphere, asyncio.Task] = {}
        self._stats = {
            "events_routed": 0,
            "events_dropped": 0,
            "left_to_right": 0,
            "right_to_left": 0,
            "bridge_events": 0
        }
        self._event_history: deque = deque(maxlen=1000)

    def start(self):
        if self._running:
            return
        self._running = True

        # Start event loop in background thread
        self._loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._loop_thread.start()

    def stop(self):
        self._running = False
        if hasattr(self, '_loop_thread'):
            self._loop_thread.join(timeout=5.0)

    def _run_event_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Start workers for each hemisphere
        for hemisphere in Hemisphere:
            self._worker_tasks[hemisphere] = loop.create_task(self._hemisphere_worker(hemisphere))

        try:
            loop.run_forever()
        finally:
            for task in self._worker_tasks.values():
                task.cancel()
            loop.close()

    async def _hemisphere_worker(self, hemisphere: Hemisphere):
        queue = self._queues[hemisphere]
        while self._running:
            try:
                priority, event = await asyncio.wait_for(queue.get(), timeout=0.1)
                await self._deliver_event(hemisphere, event)
            except asyncio.TimeoutError:
                continue
            except Exception:
                pass

    async def _deliver_event(self, hemisphere: Hemisphere, event: Event):
        handlers = self._get_handlers(hemisphere, event.event_type)

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                pass

        self._stats["events_routed"] += 1
        self._event_history.append(event)

    def _get_handlers(self, hemisphere: Hemisphere, event_type: str) -> list[Callable]:
        handlers = list(self._subscribers[hemisphere].get(event_type, []))

        for pattern, pattern_handlers in self._pattern_subscribers[hemisphere].items():
            if self._match_pattern(event_type, pattern):
                handlers.extend(pattern_handlers)

        return handlers

    def _match_pattern(self, event_type: str, pattern: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(event_type, pattern)

    def create_stream(self, source: Hemisphere, target: Hemisphere,
                      event_types: list[str]) -> str:
        stream_id = str(uuid.uuid4())[:8]
        stream = EventStream(
            stream_id=stream_id,
            source=source,
            target=target,
            event_types=set(event_types)
        )

        with self._lock:
            self._streams[stream_id] = stream

        return stream_id

    def close_stream(self, stream_id: str) -> bool:
        with self._lock:
            stream = self._streams.pop(stream_id, None)
            if stream:
                stream.active = False
                return True
        return False

    def emit(self, event_type: str, payload: Any,
             source: Hemisphere = Hemisphere.LEFT,
             target: Hemisphere = Hemisphere.RIGHT,
             priority: EventPriority = EventPriority.NORMAL,
             correlation_id: str = None) -> str:

        event = Event(
            event_id=str(uuid.uuid4())[:8],
            event_type=event_type,
            source_hemisphere=source,
            target_hemisphere=target,
            payload=payload,
            priority=priority,
            correlation_id=correlation_id
        )

        # Route based on hemispheres
        if source == Hemisphere.LEFT and target == Hemisphere.RIGHT:
            self._stats["left_to_right"] += 1
            target_queue = self._queues[Hemisphere.RIGHT]
        elif source == Hemisphere.RIGHT and target == Hemisphere.LEFT:
            self._stats["right_to_left"] += 1
            target_queue = self._queues[Hemisphere.LEFT]
        else:
            self._stats["bridge_events"] += 1
            target_queue = self._queues[Hemisphere.BRIDGE]

        try:
            target_queue.put_nowait((event.priority, event))
        except asyncio.QueueFull:
            self._stats["events_dropped"] += 1

        return event.event_id

    def emit_sync(self, event_type: str, payload: Any,
                  source: Hemisphere = Hemisphere.LEFT,
                  target: Hemisphere = Hemisphere.RIGHT,
                  **kwargs) -> str:
        return self.emit(event_type, payload, source, target, **kwargs)

    def subscribe(self, hemisphere: Hemisphere, event_type: str, handler: Callable):
        with self._lock:
            self._subscribers[hemisphere][event_type].append(handler)

    def subscribe_pattern(self, hemisphere: Hemisphere, pattern: str, handler: Callable):
        with self._lock:
            self._pattern_subscribers[hemisphere][pattern].append(handler)

    def unsubscribe(self, hemisphere: Hemisphere, event_type: str, handler: Callable):
        with self._lock:
            if handler in self._subscribers[hemisphere][event_type]:
                self._subscribers[hemisphere][event_type].remove(handler)

    def get_stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def get_recent_events(self, limit: int = 100) -> list[Event]:
        return list(self._event_history)[-limit:]

    def get_stream(self, stream_id: str) -> EventStream | None:
        with self._lock:
            return self._streams.get(stream_id)

    def list_streams(self) -> list[EventStream]:
        with self._lock:
            return list(self._streams.values())


_corpus_callosum: CorpusCallosum | None = None


def get_corpus_callosum() -> CorpusCallosum:
    global _corpus_callosum
    if _corpus_callosum is None:
        from ..core.config import config
        cap = config.get_param("neurocranial", "event_bus_capacity", 10000)
        _corpus_callosum = CorpusCallosum(capacity=cap)
        _corpus_callosum.start()
    return _corpus_callosum
