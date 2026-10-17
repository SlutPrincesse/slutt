"""
Core agent runtime: unifies orchestrator, memory, tools, evolution, guardrails
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from .core.events import EventBus, Event
from .goal_orchestrator import orchestrate
from .self_heal import heal
from .tools import DynamicToolRegistry, ToolSynthesizer
from .memory import EpisodicStore, CodeMemory
from .guardrails import PreCommitValidator
from .shadowgit import ShadowGit
from .evolution import CodeEvolutionEngine, EvolutionConfig
from .compilation import JITCompiler


class AgentCore:
    def __init__(self, eb: EventBus | None = None):
        from .core.events import EventBus
        self.eb = eb or EventBus()
        self._active = False
        try:
            self.tools = DynamicToolRegistry()
            self.synth = ToolSynthesizer(self.tools)
        except Exception:
            self.tools = self.synth = None
        try:
            self.episodic = EpisodicStore()
            self.code_mem = CodeMemory()
        except Exception:
            self.episodic = self.code_mem = None
        try:
            self.guard = PreCommitValidator()
        except Exception:
            self.guard = None
        try:
            self.shadow = ShadowGit()
        except Exception:
            self.shadow = None
        try:
            self.jit = JITCompiler()
        except Exception:
            self.jit = None
        try:
            self.cevo = CodeEvolutionEngine(EvolutionConfig())
        except Exception:
            self.cevo = None

    async def run(self, goal: str, iterations: int = 3) -> Dict[str, Any]:
        self._active = True
        self.eb.publish(Event(event_type="agent.started", payload={"goal": goal}), blocking=False)
        for i in range(iterations):
            try:
                res = await orchestrate(goal)
                self.eb.publish(Event(event_type="agent.iteration.ok", payload={"i": i, "res": res}), blocking=False)
                if self.cevo:
                    try:
                        await self.cevo.evolve(None)  # stub
                    except Exception:
                        pass
                if self.shadow:
                    try:
                        self.shadow.commit(f"agent iter {i}: {goal[:40]}")
                    except Exception:
                        pass
            except Exception as e:
                await heal({"error": str(e), "i": i})
                self.eb.publish(Event(event_type="agent.iteration.fail", payload={"i": i, "err": str(e)}), blocking=False)
        self._active = False
        self.eb.publish(Event(event_type="agent.stopped", payload={"goal": goal}), blocking=False)
        return {"goal": goal, "status": "done"}


async def run_agent(goal: str, iterations: int = 3):
    a = AgentCore()
    return await a.run(goal, iterations)
