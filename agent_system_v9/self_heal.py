"""
Self-healing: detect failures, search memory, synthesize fix
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from .core.events import EventBus, Event
from .memory import EpisodicStore, CodeMemory, QueryEngine, SemanticIndexer, KnowledgeGraph
from .tools import ToolSynthesizer, DynamicToolRegistry


class SelfHealer:
    def __init__(self, eb: EventBus | None = None):
        from .core.events import EventBus
        self.eb = eb or EventBus()
        try:
            self.episodic = EpisodicStore()
            self.code_mem = CodeMemory()
            self.query = QueryEngine(self.episodic, SemanticIndexer(), KnowledgeGraph(), self.code_mem)
        except Exception:
            self.query = None
        try:
            self.synth = ToolSynthesizer(DynamicToolRegistry())
        except Exception:
            self.synth = None

    async def on_failure(self, info: Dict[str, Any]) -> Dict[str, Any]:
        self.eb.publish(Event(event_type="selfheal.detected", payload=info), blocking=False)
        if self.query:
            try:
                await self.query.query(str(info))
            except Exception:
                pass
        if self.synth:
            try:
                await self.synth.synthesize_from_exception(str(info))
            except Exception:
                pass
        self.eb.publish(Event(event_type="selfheal.attempted", payload=info), blocking=False)
        return {"status": "attempted", "info": info}


async def heal(info: Dict[str, Any]):
    sh = SelfHealer()
    return await sh.on_failure(info)
