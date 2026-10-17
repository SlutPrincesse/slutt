"""
High-level agent facade
"""
from __future__ import annotations

from .agent_core import AgentCore, run_agent
from .goal_orchestrator import GoalOrchestrator, orchestrate
from .autonomy import run_autonomous


class Agent(AgentCore):
    async def think(self, goal: str):
        return await orchestrate(goal)

    async def solve(self, goal: str, iterations: int = 5):
        return await self.run(goal, iterations)


async def create_agent() -> Agent:
    return Agent()
