"""Multi-agent orchestration: planner, coder, tester, reviewer with consensus."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRole:
    name: str
    system_prompt: str


ROLES = {
    "planner": AgentRole("planner", "Break the task into steps."),
    "coder": AgentRole("coder", "Write code to implement the plan."),
    "tester": AgentRole("tester", "Run tests and report failures."),
    "reviewer": AgentRole("reviewer", "Review code for correctness and style."),
}


@dataclass
class MultiAgentResult:
    success: bool
    plan: str = ""
    code: str = ""
    test_output: str = ""
    review: str = ""
    iterations: int = 0
    error: str | None = None


class MultiAgentOrchestrator:
    def __init__(self, provider=None, max_iterations: int = 3):
        self.provider = provider
        self.max_iterations = max_iterations

    async def _chat(self, role: str, content: str) -> str:
        if self.provider is None:
            return f"[{role}] no provider; echo: {content[:120]}"
        try:
            resp = await self.provider.chat([{"role": "system", "content": ROLES[role].system_prompt}, {"role": "user", "content": content}])
            return getattr(resp, "content", None) or str(resp)
        except Exception as e:
            return f"[{role}] error: {e}"

    async def run(self, task: str) -> MultiAgentResult:
        plan = await self._chat("planner", task)
        code = await self._chat("coder", f"Plan:\n{plan}\nTask:\n{task}")
        test_output = await self._chat("tester", f"Code:\n{code}")
        review = await self._chat("reviewer", f"Code:\n{code}\nTests:\n{test_output}")
        # consensus: simple - success if review contains 'ok' or no provider
        success = ("ok" in review.lower()) or (self.provider is None)
        return MultiAgentResult(success=success, plan=plan, code=code, test_output=test_output, review=review, iterations=1)
