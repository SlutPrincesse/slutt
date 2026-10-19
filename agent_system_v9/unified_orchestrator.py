"""Unified orchestrator wiring all subsystems into a single entry point."""
from __future__ import annotations

import asyncio
from typing import Any

from .core.config import SystemConfig
from .core.registry import SystemRegistry
from .core.events import EventBus
from .tools.tool_registry import DynamicToolRegistry
from .context.context_window import ContextWindow
from .prompt.dynamic_assembler import get_prompt_assembler
from .providers.registry import ProviderRegistry
from .memory.query_engine import QueryEngine
from .telemetry.tracer import Tracer
from .coding.coding_agent import CodingAgent
from .pentest.pentest_tools import register_pentest_tools
from .agents.multi_agent import MultiAgentOrchestrator


class UnifiedOrchestrator:
    def __init__(self):
        self.config = SystemConfig()
        self.registry = SystemRegistry()
        self.event_bus = EventBus()
        self.tool_registry = DynamicToolRegistry.get_instance()
        self.tool_registry.set_event_bus(self.event_bus)
        self.context_window = ContextWindow(session_id="unified", budget_tokens=4000, verbatim_tail=8)
        self.prompt_assembler = get_prompt_assembler()
        self.prompt_assembler.set_context_window(self.context_window)
        self.provider_registry = ProviderRegistry.get_instance()
        self.query_engine = QueryEngine()
        self.tracer = Tracer()
        self.coding_agent = CodingAgent(context_window=self.context_window, prompt_assembler=self.prompt_assembler, provider_registry=self.provider_registry)
        self.multi_agent = MultiAgentOrchestrator(provider=None)
        try:
            register_pentest_tools(self.tool_registry, network_enabled=False)
        except Exception:
            pass

    async def handle(self, task: str) -> dict[str, Any]:
        self.context_window.append("user", task)
        # simple routing: if contains 'code' -> coding agent
        if "code" in task.lower() or "fix" in task.lower():
            res = await self.coding_agent.solve(task)
            self.context_window.append("assistant", str(res.test_output)[:2000])
            return {"type": "coding", "result": res.__dict__}
        # if contains 'recon'/'pentest' -> multi-agent
        if any(k in task.lower() for k in ("recon", "pentest", "scan")):
            res = await self.multi_agent.run(task)
            return {"type": "pentest", "result": res.__dict__}
        # default: LLM chat if provider available
        provider = self.provider_registry.select_provider() if self.provider_registry.get_healthy() else None
        if provider is not None:
            try:
                resp = await provider.chat([{"role": "user", "content": task}])
                content = getattr(resp, "content", None) or str(resp)
                self.context_window.append("assistant", content)
                return {"type": "chat", "result": content}
            except Exception as e:
                return {"type": "error", "error": str(e)}
        return {"type": "echo", "result": task}
