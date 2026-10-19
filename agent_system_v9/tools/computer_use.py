"""
Tool & Computer Use - native agent tool loop with human oversight.

Agent → DynamicPromptAssembler (compressed prompt) → DynamicToolRegistry →
SandboxIsolator.execute_tool → result → ContextWindow/Memory → re-plan.
"""
from __future__ import annotations

import json
from typing import Any

from .tool_registry import DynamicToolRegistry


class ApprovalGuard:
    """Destructive/write tools require explicit approval flag."""

    DESTRUCTIVE_TAGS = {"write", "delete", "exec", "network", "pentest"}

    def __init__(self):
        self._approved: set[str] = set()

    def requires_approval(self, tool_name: str, tags: list[str] | None = None) -> bool:
        tags = tags or []
        if any(t in self.DESTRUCTIVE_TAGS for t in tags):
            return True
        lowered = tool_name.lower()
        return any(k in lowered for k in ("write", "delete", "run_", "exec"))

    def approve(self, tool_name: str) -> None:
        self._approved.add(tool_name)

    def is_approved(self, tool_name: str) -> bool:
        return tool_name in self._approved

    def check(self, tool_name: str, tags: list[str] | None = None, approved: bool = False) -> bool:
        if not self.requires_approval(tool_name, tags):
            return True
        return approved or self.is_approved(tool_name)


class ComputerUseLoop:
    def __init__(
        self,
        registry: DynamicToolRegistry | None = None,
        context_window=None,
        prompt_assembler=None,
        max_steps: int = 10,
        approval_guard: ApprovalGuard | None = None,
    ):
        self.registry = registry or DynamicToolRegistry.get_instance()
        self.context_window = context_window
        self.prompt_assembler = prompt_assembler
        self.max_steps = max_steps
        self.approval_guard = approval_guard or ApprovalGuard()

    async def step(self, tool_name: str, args: dict[str, Any], approved: bool = False) -> dict[str, Any]:
        entry = self.registry._tools.get(tool_name)
        if entry is None:
            return {"success": False, "error": f"tool not found: {tool_name}"}

        if not self.approval_guard.check(tool_name, entry.tags, approved):
            return {"success": False, "error": "approval required", "approval_required": True}

        result = await self.registry.execute(tool_name, args, sandbox=True)
        if self.context_window is not None:
            try:
                self.context_window.append("tool", json.dumps({"tool": tool_name, "result": result})[:2000])
            except Exception:
                pass
        return result if isinstance(result, dict) else {"success": True, "output": result}

    async def run(self, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for i, item in enumerate(plan[: self.max_steps]):
            tool_name = item.get("tool")
            args = item.get("args", {})
            approved = bool(item.get("approved", False))
            r = await self.step(tool_name, args, approved)
            results.append({"step": i, "tool": tool_name, "result": r})
            if isinstance(r, dict) and r.get("approval_required"):
                break
        return results

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [e.to_openai_function() for e in self.registry._tools.values()]
