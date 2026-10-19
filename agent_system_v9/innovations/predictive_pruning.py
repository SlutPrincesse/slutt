"""Predictive context pruning: predict needed tokens, prune proactively."""
from __future__ import annotations

from typing import Any


class PredictivePruner:
    def __init__(self, window):
        self.window = window

    def predict_needed(self, task: str) -> list[str]:
        # heuristic: keywords from task
        return [t for t in task.lower().split() if len(t) > 3]

    def prune(self, task: str) -> int:
        needed = set(self.predict_needed(task))
        removed = 0
        # remove messages not containing needed keywords
        keep = []
        for m in self.window.messages:
            content = m.content if hasattr(m, "content") else str(m)
            if any(k in content.lower() for k in needed) or not needed:
                keep.append(m)
            else:
                removed += 1
        self.window.messages = keep
        return removed
