"""
Auto-orchestrator: minimal default loop wiring reasoning/memory/tools/compilation/shadowgit
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List

from .core.events import EventBus, Event
from .core.registry import SystemRegistry


@dataclass
class Goal:
    text: str
    steps: List[str]
    context: Dict[str, Any]


class AutoOrchestrator:
    def __init__(self, event_bus: EventBus | None = None, registry: SystemRegistry | None = None):
        from .core.events import EventBus
        from .core.registry import registry as reg
        self.eb = event_bus or EventBus()
        self.reg = registry or reg
        self._running = False

    async def run_goal(self, goal_text: str):
        self._running = True
        # Decompose (minimal)
        steps = ["plan", "research", "act", "reflect"]
        g = Goal(text=goal_text, steps=steps, context={})
        for s in steps:
            await asyncio.sleep(0)
            self.eb.publish(Event(event_type=f"orchestrator.step", payload={"step": s, "goal": goal_text}), blocking=False)
        self._running = False
        return {"goal": goal_text, "status": "done"}


async def run_auto(goal: str):
    ao = AutoOrchestrator()
    return await ao.run_goal(goal)
