"""Plan-and-execute: decompose tasks into steps."""
from __future__ import annotations

from typing import Any


class TaskPlanner:
    def __init__(self, provider=None):
        self.provider = provider

    async def plan(self, task: str) -> list[str]:
        if self.provider is not None:
            try:
                resp = await self.provider.chat([{"role": "user", "content": f"Break this task into numbered steps:\n{task}"}])
                content = getattr(resp, "content", None) or str(resp)
                steps = [s.strip() for s in content.split("\n") if s.strip()]
                return steps if steps else [task]
            except Exception:
                pass
        # heuristic fallback
        return [f"Analyze: {task}", f"Implement: {task}", f"Test: {task}"]

    async def reflect(self, code: str, test_output: str) -> str:
        if self.provider is not None:
            try:
                resp = await self.provider.chat([{"role": "user", "content": f"Code:\n{code}\nTests:\n{test_output}\nSuggest fixes."}])
                return getattr(resp, "content", None) or str(resp)
            except Exception:
                pass
        return "Review the failing tests and adjust the implementation."
