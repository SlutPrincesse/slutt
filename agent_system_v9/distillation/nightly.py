"""Nightly distillation job skeleton."""
from __future__ import annotations

import asyncio
from typing import Any

from .trace_distiller import TraceDistiller
from .memory_distiller import MemoryDistiller
from .policy_distiller import PolicyDistiller


class NightlyDistillationJob:
    def __init__(self, tracer=None, episodic_store=None, knowledge_graph=None, provider_registry=None, tool_registry=None):
        self.tracer = tracer
        self.episodic_store = episodic_store
        self.knowledge_graph = knowledge_graph
        self.provider_registry = provider_registry
        self.tool_registry = tool_registry

    async def run(self) -> dict[str, Any]:
        report = {}
        # 1. distill traces
        events = self.tracer.events() if self.tracer is not None else []
        td = TraceDistiller()
        report["traces"] = td.distill(events)
        # 2. distill memory
        md = MemoryDistiller(self.knowledge_graph, self.episodic_store)
        report["memory_distilled"] = md.distill()
        # 3. distill policy
        metrics = self.tracer.aggregate() if self.tracer is not None else {}
        pd = PolicyDistiller(self.provider_registry, self.tool_registry)
        report["policy"] = pd.distill({"tools": metrics})
        return report
