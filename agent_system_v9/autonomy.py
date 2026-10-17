"""
Autonomy harness
"""
from __future__ import annotations

import asyncio
from typing import Optional

from .goal_orchestrator import orchestrate
from .self_heal import heal


async def run_autonomous(goal: str, max_iterations: int = 3) -> None:
    for i in range(max_iterations):
        try:
            res = await orchestrate(goal)
        except Exception as e:
            await heal({"error": str(e), "iteration": i})
            continue
