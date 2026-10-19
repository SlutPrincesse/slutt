"""Canary deployment + promotion with auto-rollback."""
from __future__ import annotations

from typing import Any


class CanaryController:
    def __init__(self, baseline_metric: float, threshold: float = 0.05):
        self.baseline = baseline_metric
        self.threshold = threshold
        self.history: list[dict[str, Any]] = []

    def evaluate(self, candidate_metric: float) -> dict[str, Any]:
        delta = candidate_metric - self.baseline
        promote = delta >= self.threshold
        rollback = delta < -self.threshold
        result = {"baseline": self.baseline, "candidate": candidate_metric, "delta": delta, "promote": promote, "rollback": rollback}
        self.history.append(result)
        if promote:
            self.baseline = candidate_metric
        return result
