"""Counterfactual replay: re-run failed tasks with modified prompts/tools."""
from __future__ import annotations

from typing import Any, Callable, Awaitable


class CounterfactualReplay:
    def __init__(self):
        self._results: list[dict[str, Any]] = []

    async def replay(self, task: str, variants: list[dict[str, Any]], runner: Callable[[str, dict[str, Any]], Awaitable[Any]]) -> list[dict[str, Any]]:
        out = []
        for v in variants:
            try:
                r = await runner(task, v)
                out.append({"variant": v, "result": r, "success": bool(getattr(r, "success", True))})
            except Exception as e:
                out.append({"variant": v, "error": str(e), "success": False})
        self._results.extend(out)
        return out

    def best(self) -> dict[str, Any] | None:
        succ = [r for r in self._results if r.get("success")]
        return max(succ, key=lambda r: 1) if succ else (self._results[-1] if self._results else None)
