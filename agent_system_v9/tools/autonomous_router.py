"""Autonomous tool selection based on success rates."""
from __future__ import annotations

from typing import Any


class AutonomousToolRouter:
    def __init__(self, registry):
        self.registry = registry

    def suggest(self, task: str, top_k: int = 3) -> list[str]:
        task_l = task.lower()
        candidates = []
        for name, entry in self.registry._tools.items():
            score = 0.0
            # tag relevance
            for tag in entry.tags:
                if tag in task_l:
                    score += 1.0
            # name relevance
            if any(tok in name for tok in task_l.split()):
                score += 2.0
            # success rate from metrics
            m = self.registry.metrics.by_tool.get(name, {})
            calls = m.get("executions", 0)
            errors = m.get("errors", 0)
            rate = 1.0 - (errors / max(1, calls))
            score += rate
            candidates.append((score, name))
        candidates.sort(reverse=True)
        return [n for _, n in candidates[:top_k]]
