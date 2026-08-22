import threading
from typing import Any, Callable, Dict, List, Optional

from cranial.event_bus import EventBus


class ConsciousLayer:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.task_dag = None
        self.user_actions: List[Dict[str, Any]] = []
        self._stop = threading.Event()
        self._loop = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._loop.start()

    def stop(self) -> None:
        self._stop.set()
        self._loop.join()

    def submit(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        if self.task_dag is None:
            raise RuntimeError("Task DAG not attached")
        node = self.task_dag.add_task(name, name, metadata)
        self.bus.publish("conscious.task.created", {"task_id": node.id, "name": name})
        return node.id

    def attach_dag(self, dag) -> None:
        self.task_dag = dag

    def _run(self) -> None:
        while not self._stop.is_set():
            event = self.bus.consume("conscious", timeout=0.5)
            if event:
                self._handle(event)

    def _handle(self, event: Dict[str, Any]) -> None:
        topic = event.get("topic")
        payload = event.get("payload", {})
        if topic == "shadow.compilation.finished":
            print(f"[Conscious] Background compilation finished: {payload}")
        elif topic == "shadow.research.result":
            print(f"[Conscious] Research result received: {payload}")

    def request_tool_ingest(self, query: str) -> None:
        self.bus.publish("conscious.tool.ingest", {"query": query})

    def request_speculative(self, mode: str, count: int = 3) -> None:
        self.bus.publish("conscious.speculative.start", {"mode": mode, "count": count})
