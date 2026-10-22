"""
EventBus bridge to Unified UI
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List

from ..core.events import EventBus, Event


@dataclass
class UIState:
    """Unified UI state"""
    components: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    events: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))
    tools: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)
    evolution: Dict[str, Any] = field(default_factory=dict)
    last_update: float = field(default_factory=time.time)


class UnifiedBridge:
    """Bridge between EventBus and UI"""
    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus or EventBus()
        self.state = UIState()
        self.subscribers: List[Callable] = []
        self._running = False
        self._task: asyncio.Task | None = None

    def subscribe_ui(self, callback: Callable):
        self.subscribers.append(callback)

    def _notify(self):
        for cb in self.subscribers:
            try:
                if asyncio.iscoroutinefunction(cb):
                    asyncio.create_task(cb(self.state))
                else:
                    cb(self.state)
            except Exception:
                pass

    def start(self):
        self._running = True
        try:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._loop())
        except Exception:
            pass

    async def _loop(self):
        while self._running:
            self.state.last_update = time.time()
            self._notify()
            await asyncio.sleep(0.05)

    def stop(self):
        self._running = False

    def _handle_event(self, event):
        try:
            et = getattr(event, 'event_type', None)
            if et and 'tool' in str(et):
                self.state.tools.setdefault(str(et), []).append({'payload': str(getattr(event,'payload',None)), 'timestamp': getattr(event,'timestamp',None), 'source': getattr(event,'source',None)})
            self.state.events.append({
                'type': event.event_type,
                'payload': str(event.payload) if event.payload is not None else None,
                'timestamp': event.timestamp,
                'source': event.source,
            })
        except Exception:
            pass

    def wire(self):
        self.event_bus.subscribe_all(self._handle_event)

    def update_components(self, data: Dict[str, Any]):
        self.state.components.update(data)
        self._notify()
