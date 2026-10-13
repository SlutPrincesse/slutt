"""
Core Event Bus - High-speed real-time event routing between components
"""
from typing import Dict, List, Callable, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import threading
import asyncio
import uuid
import time
from collections import defaultdict
import weakref


class EventPriority(Enum):
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class Event:
    event_type: str
    payload: Any = None
    source: str = ""
    target: str = ""
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        return self.priority.value > other.priority.value


class EventBus:
    _instance: Optional['EventBus'] = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._pattern_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._wildcard_subscribers: List[Callable] = []
        self._event_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()
        self._event_history: List[Event] = []
        self._max_history = 10000
        self._stats = {
            "published": 0,
            "delivered": 0,
            "failed": 0,
            "dropped": 0
        }
        self._initialized = True
    
    def subscribe(self, event_type: str, handler: Callable, pattern: bool = False):
        with self._lock:
            if pattern or "*" in event_type or "?" in event_type:
                self._pattern_subscribers[event_type].append(handler)
            else:
                self._subscribers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable):
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [h for h in self._subscribers[event_type] if h != handler]
            if event_type in self._pattern_subscribers:
                self._pattern_subscribers[event_type] = [h for h in self._pattern_subscribers[event_type] if h != handler]
    
    def subscribe_all(self, handler: Callable):
        with self._lock:
            self._wildcard_subscribers.append(handler)
    
    def publish(self, event: Event, blocking: bool = False) -> str:
        self._stats["published"] += 1
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]
        
        if blocking:
            self._deliver_sync(event)
        else:
            try:
                self._event_queue.put_nowait((event.priority, event))
            except asyncio.QueueFull:
                self._stats["dropped"] += 1
        
        return event.event_id
    
    def publish_sync(self, event_type: str, payload: Any = None, source: str = "", 
                     priority: EventPriority = EventPriority.NORMAL, **metadata) -> str:
        event = Event(event_type=event_type, payload=payload, source=source, 
                      priority=priority, metadata=metadata)
        return self.publish(event, blocking=True)
    
    def _deliver_sync(self, event: Event):
        handlers = self._get_handlers(event.event_type)
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(event))
                else:
                    handler(event)
                self._stats["delivered"] += 1
            except Exception as e:
                self._stats["failed"] += 1
        
        for handler in self._wildcard_subscribers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(event))
                else:
                    handler(event)
                self._stats["delivered"] += 1
            except Exception:
                self._stats["failed"] += 1
    
    def _get_handlers(self, event_type: str) -> List[Callable]:
        handlers = list(self._subscribers.get(event_type, []))
        for pattern, pattern_handlers in self._pattern_subscribers.items():
            if self._match_pattern(event_type, pattern):
                handlers.extend(pattern_handlers)
        return handlers
    
    def _match_pattern(self, event_type: str, pattern: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(event_type, pattern)
    
    async def start(self):
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._event_worker())
    
    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
    
    async def _event_worker(self):
        while self._running:
            try:
                priority, event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                self._deliver_sync(event)
            except asyncio.TimeoutError:
                continue
            except Exception:
                self._stats["failed"] += 1
    
    def get_stats(self) -> Dict[str, int]:
        return dict(self._stats)
    
    def get_history(self, limit: int = 100, event_type: str = None) -> List[Event]:
        history = self._event_history
        if event_type:
            history = [e for e in history if e.event_type == event_type]
        return history[-limit:]


event_bus = EventBus()