import threading
from typing import Any, Dict, List

from cranial.event_bus import EventBus


class CranialHUD:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.conscious_log: List[str] = []
        self.shadow_log: List[str] = []
        self._stop = threading.Event()
        self._loop = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._loop.start()

    def stop(self) -> None:
        self._stop.set()
        self._loop.join()

    def render(self) -> str:
        left = "\n".join(self.conscious_log[-10:]) or "[Conscious] idle"
        right = "\n".join(self.shadow_log[-10:]) or "[Shadow] idle"
        divider = "│" * (max(len(left.splitlines()), len(right.splitlines())))
        return f"""
╔══════════════════════════════════════════════════════════════════╗
║                     THE CRANIAL HUD                              ║
╠════════════════════════════╦══════════════════════════════════════╣
║ Conscious Layer            ║ Subconscious Layer                   ║
║ {left[:60]:<60} ║ {right[:60]:<60} ║
╚════════════════════════════╩══════════════════════════════════════╝
"""

    def _run(self) -> None:
        while not self._stop.is_set():
            event = self.bus.consume(timeout=0.5)
            if event:
                self._handle(event)

    def _handle(self, event: Dict[str, Any]) -> None:
        topic = event.get("topic", "")
        payload = event.get("payload", {})
        if topic.startswith("conscious."):
            self.conscious_log.append(f"[{topic.split('.')[-1]}] {payload}")
        elif topic.startswith("shadow."):
            self.shadow_log.append(f"[{topic.split('.')[-1]}] {payload}")
        elif topic == "shadow.stall":
            self.shadow_log.append(f"[STALL] {payload}")
