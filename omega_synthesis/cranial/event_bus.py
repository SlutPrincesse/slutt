import threading
from typing import Any, Dict, List, Optional


class EventBus:
    def __init__(self):
        self._topics: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def publish(self, topic: str, payload: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._topics.setdefault(topic, []).append({"topic": topic, "payload": payload or {}})

    def consume(self, topic: Optional[str] = None, timeout: float = 0.1) -> Optional[Dict[str, Any]]:
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if topic:
                    if self._topics.get(topic):
                        return self._topics[topic].pop(0)
                else:
                    for t, events in self._topics.items():
                        if events:
                            return events.pop(0)
            time.sleep(0.01)
        return None

    def drain(self) -> List[Dict[str, Any]]:
        with self._lock:
            events = []
            for evts in self._topics.values():
                events.extend(evts)
            self._topics.clear()
            return events
