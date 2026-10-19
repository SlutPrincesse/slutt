"""Confidence-calibrated refusal: estimate confidence, refuse below threshold."""
from __future__ import annotations

from typing import Any


class ConfidenceCalibrator:
    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    def estimate(self, task: str, context: dict[str, Any] | None = None) -> float:
        # heuristic: longer context + known tools -> higher confidence
        ctx = context or {}
        base = 0.5
        if ctx.get("tools"):
            base += 0.2
        if ctx.get("memory"):
            base += 0.1
        if len(task) < 20:
            base -= 0.1
        return min(1.0, max(0.0, base))

    def should_refuse(self, confidence: float) -> bool:
        return confidence < self.threshold

    def decide(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        c = self.estimate(task, context)
        return {"confidence": c, "refuse": self.should_refuse(c), "threshold": self.threshold}
