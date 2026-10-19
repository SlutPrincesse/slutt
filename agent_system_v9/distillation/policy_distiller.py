"""Distill provider/tool routing weights from outcomes."""
from __future__ import annotations

from typing import Any


class PolicyDistiller:
    def __init__(self, provider_registry=None, tool_registry=None):
        self.provider_registry = provider_registry
        self.tool_registry = tool_registry

    def distill(self, metrics: dict[str, Any]) -> dict[str, Any]:
        # Adjust tool priority tags based on success rate (lightweight)
        updates = {"tools": {}, "providers": {}}
        if self.tool_registry is not None:
            for name, m in (metrics.get("tools", {}) or {}).items():
                calls = m.get("calls", 0)
                errors = m.get("errors", 0)
                rate = 1.0 - (errors / max(1, calls))
                updates["tools"][name] = {"success_rate": rate}
        return updates
