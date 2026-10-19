"""Self-distilling tool genesis: synthesize tools from repeated patterns, A/B test, prune."""
from __future__ import annotations

from collections import Counter
from typing import Any

from agent_system_v9.distillation.trace_distiller import TraceDistiller
from agent_system_v9.tools.tool_synthesizer import ToolSynthesizer


class ToolGenesis:
    def __init__(self, registry, synthesizer: ToolSynthesizer | None = None):
        self.registry = registry
        self.synthesizer = synthesizer or ToolSynthesizer()
        self._candidates: dict[str, float] = {}

    def propose(self, events: list[Any]) -> list[str]:
        td = TraceDistiller()
        distilled = td.distill(events)
        seqs = distilled.get("tool_sequences", [])
        proposed = []
        for seq in seqs:
            name = "auto_" + "_".join(seq)[:40]
            self._candidates[name] = self._candidates.get(name, 0) + 1
            proposed.append(name)
        return proposed

    def score(self, name: str, success_rate: float) -> None:
        self._candidates[name] = success_rate

    def prune(self, threshold: float = 0.5) -> list[str]:
        removed = [n for n, s in list(self._candidates.items()) if s < threshold]
        for n in removed:
            del self._candidates[n]
        return removed

    def candidates(self) -> dict[str, float]:
        return dict(self._candidates)
