"""
Persistent agent loop with goal tracking
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from .core.events import EventBus, Event
from .agent_core import run_agent


@dataclass
class AgentSession:
    goal: str
    history: List[Dict[str, Any]] = field(default_factory=list)
    started: datetime = field(default_factory=datetime.utcnow)
    active: bool = True


class AgentLoop:
    def __init__(self, eb: EventBus | None = None):
        from .core.events import EventBus
        self.eb = eb or EventBus()
        self.sessions: Dict[str, AgentSession] = {}
        self._running = False

    async def start(self, goal: str, sid: str = "default") -> AgentSession:
        s = AgentSession(goal=goal)
        self.sessions[sid] = s
        self._running = True
        self.eb.publish(Event(event_type="loop.started", payload={"sid": sid, "goal": goal}), blocking=False)
        asyncio.create_task(self._run(sid))
        return s

    async def _run(self, sid: str):
        s = self.sessions.get(sid)
        if not s:
            return
        try:
            await run_agent(s.goal, iterations=5)
            s.active = False
            self.eb.publish(Event(event_type="loop.finished", payload={"sid": sid}), blocking=False)
        except Exception as e:
            s.history.append({"error": str(e), "ts": datetime.utcnow().isoformat()})
            self.eb.publish(Event(event_type="loop.error", payload={"sid": sid, "err": str(e)}), blocking=False)


async def start_loop(goal: str, sid: str = "default"):
    l = AgentLoop()
    return await l.start(goal, sid)
