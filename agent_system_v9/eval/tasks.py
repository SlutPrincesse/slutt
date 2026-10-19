"""Concrete benchmark task sets for evaluation."""
from __future__ import annotations

from typing import Any, Callable, Awaitable


def coding_tasks() -> list[dict[str, Any]]:
    return [
        {"name": "add", "prompt": "Write a function add(a,b) returning a+b.", "test": "assert add(2,3)==5"},
        {"name": "factorial", "prompt": "Write factorial(n).", "test": "assert factorial(5)==120"},
        {"name": "is_prime", "prompt": "Write is_prime(n).", "test": "assert is_prime(7) and not is_prime(4)"},
    ]


async def run_coding_benchmark(runner: Callable[[str], Awaitable[bool]]) -> dict[str, Any]:
    tasks = coding_tasks()
    passed = 0
    for t in tasks:
        ok = await runner(t["prompt"])
        if ok:
            passed += 1
    return {"total": len(tasks), "passed": passed, "pass_rate": passed / len(tasks)}
