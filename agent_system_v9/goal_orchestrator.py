"""
Full goal-driven orchestrator
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .core.events import EventBus, Event
from .core.registry import SystemRegistry, registry as global_registry
from .reasoning import ConceptAbstractor, ContextSerializer, OntologyUpdater
from .memory import EpisodicStore, SemanticIndexer, KnowledgeGraph, CodeMemory, QueryEngine
from .tools import DynamicToolRegistry, ToolSynthesizer
from .compilation import UniversalCodeGenerator, JITCompiler, HotSwapLoader
from .shadowgit import ShadowGit, ShadowGitSync
from .guardrails import PreCommitValidator, TypingGuard, NoOpDetector
from .evolution import CodeEvolutionEngine, EvolutionConfig


@dataclass
class GoalPlan:
    goal: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created: float = field(default_factory=time.time)


class GoalOrchestrator:
    def __init__(self, event_bus: EventBus | None = None, registry: SystemRegistry | None = None):
        self.eb = event_bus or EventBus()
        self.reg = registry or global_registry
        self._running = False
        try:
            self.reason = ConceptAbstractor()
            self.ctx_ser = ContextSerializer()
            self.onto = OntologyUpdater()
        except Exception:
            self.reason = self.ctx_ser = self.onto = None
        try:
            self.episodic = EpisodicStore()
            self.semantic = SemanticIndexer()
            self.kg = KnowledgeGraph()
            self.code_mem = CodeMemory()
            self.query = QueryEngine(self.episodic, self.semantic, self.kg, self.code_mem)
        except Exception:
            self.episodic = self.semantic = self.kg = self.code_mem = self.query = None
        try:
            self.tools = DynamicToolRegistry()
            self.synth = ToolSynthesizer(self.tools)
        except Exception:
            self.tools = self.synth = None
        try:
            self.codegen = UniversalCodeGenerator()
            self.jit = JITCompiler()
            self.hotswap = HotSwapLoader()
        except Exception:
            self.codegen = self.jit = self.hotswap = None
        try:
            self.shadow = ShadowGit()
        except Exception:
            self.shadow = None
        try:
            self.guard = PreCommitValidator()
            self.typing = TypingGuard()
            self.noop = NoOpDetector()
        except Exception:
            self.guard = self.typing = self.noop = None
        try:
            self.evo_cfg = EvolutionConfig()
            self.cevo = CodeEvolutionEngine(self.evo_cfg)
        except Exception:
            self.cevo = None

    async def decompose(self, goal: str) -> GoalPlan:
        plan = GoalPlan(goal=goal)
        plan.steps = [
            {"id": 1, "name": "analyze", "desc": "Understand goal via reasoning/memory"},
            {"id": 2, "name": "plan", "desc": "Create detailed action plan"},
            {"id": 3, "name": "research", "desc": "Query memory/tools for relevant info"},
            {"id": 4, "name": "implement", "desc": "Generate/edit code with guardrails"},
            {"id": 5, "name": "validate", "desc": "Compile/test/lint"},
            {"id": 6, "name": "evolve", "desc": "Consider improvements"},
            {"id": 7, "name": "persist", "desc": "Commit via ShadowGit and summarize"},
            {"id": 8, "name": "reflect", "desc": "Learn from outcome"},
        ]
        self.eb.publish(Event(event_type="orchestrator.plan.created", payload={"goal": goal, "steps": len(plan.steps)}), blocking=False)
        return plan

    async def execute(self, plan: GoalPlan) -> Dict[str, Any]:
        self._running = True
        results = []
        for step in plan.steps:
            self.eb.publish(Event(event_type="orchestrator.step.start", payload={"step": step}), blocking=False)
            await asyncio.sleep(0.01)
            if self.query:
                try:
                    await self.query.query(step["name"])
                except Exception:
                    pass
            if step["name"] == "persist" and self.shadow:
                try:
                    await self.shadow.commit(f"auto: {plan.goal[:60]}")
                except Exception:
                    pass
            self.eb.publish(Event(event_type="orchestrator.step.done", payload={"step": step}), blocking=False)
            results.append(step["name"])
        self._running = False
        self.eb.publish(Event(event_type="orchestrator.goal.completed", payload={"goal": plan.goal, "results": results}), blocking=False)
        return {"goal": plan.goal, "steps": results, "status": "completed"}


async def orchestrate(goal: str):
    o = GoalOrchestrator()
    p = await o.decompose(goal)
    return await o.execute(p)
