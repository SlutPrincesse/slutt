import threading
import time
from typing import Any, Dict, Optional

from cranial.event_bus import EventBus


class ShadowNudge:
    def __init__(self, bus: EventBus, stall_timeout: float = 2.0):
        self.bus = bus
        self.stall_timeout = stall_timeout
        self._stop = threading.Event()
        self._loop = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._loop.start()

    def stop(self) -> None:
        self._stop.set()
        self._loop.join()

    def _run(self) -> None:
        timers: Dict[str, float] = {}
        while not self._stop.is_set():
            event = self.bus.consume("shadow", timeout=0.5)
            now = time.time()
            if event:
                topic = event.get("topic")
                task_id = event.get("payload", {}).get("task_id", "")
                if topic == "shadow.task.started":
                    timers[task_id] = now
                elif topic == "shadow.task.finished":
                    timers.pop(task_id, None)
                elif topic == "shadow.task.failed":
                    timers.pop(task_id, None)
            for tid, started in list(timers.items()):
                if now - started > self.stall_timeout:
                    self.bus.publish("shadow.stall", {"task_id": tid, "elapsed": now - started})
                    timers.pop(tid, None)


class ShadowBrokerWorker:
    def __init__(self, bus: EventBus, broker: Any):
        self.bus = bus
        self.broker = broker
        self._stop = threading.Event()
        self._loop = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._loop.start()

    def stop(self) -> None:
        self._stop.set()
        self._loop.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            event = self.bus.consume("conscious.tool.ingest", timeout=0.5)
            if event:
                query = event.get("payload", {}).get("query", "")
                print(f"[ShadowBroker] Ingestion request: {query}")
                card = self.broker.ingest_repo(f"https://github.com/example/{query}")
                if card:
                    self.bus.publish("shadow.tool.registered", card.to_dict())


class SubconsciousLayer:
    def __init__(self, bus: EventBus, broker: Any):
        self.bus = bus
        self.nudge = ShadowNudge(bus)
        self.broker_worker = ShadowBrokerWorker(bus, broker)

    def start(self) -> None:
        self.nudge.start()
        self.broker_worker.start()

    def stop(self) -> None:
        self.nudge.stop()
        self.broker_worker.stop()
