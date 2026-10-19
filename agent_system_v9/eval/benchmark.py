"""Benchmark harness: pass@k, task completion rate, latency."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class BenchmarkResult:
    name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    pass_at_k: float = 0.0
    avg_latency_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


class BenchmarkHarness:
    def __init__(self):
        self.results: list[BenchmarkResult] = []

    async def run_tasks(self, name: str, tasks: list[Any], runner: Callable[[Any], Awaitable[bool]], k: int = 1) -> BenchmarkResult:
        res = BenchmarkResult(name=name, total=len(tasks))
        latencies = []
        for task in tasks:
            passed = False
            for _ in range(k):
                start = time.monotonic()
                try:
                    ok = await runner(task)
                    if ok:
                        passed = True
                except Exception as e:
                    res.errors.append(str(e))
                latencies.append((time.monotonic() - start) * 1000)
            if passed:
                res.passed += 1
            else:
                res.failed += 1
        res.pass_at_k = res.passed / max(1, res.total)
        res.avg_latency_ms = sum(latencies) / max(1, len(latencies))
        self.results.append(res)
        return res
