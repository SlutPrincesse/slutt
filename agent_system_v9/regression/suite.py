"""Regression suite: golden traces replayed on every change."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Awaitable


class RegressionSuite:
    def __init__(self, golden_dir: Path | None = None):
        self.golden_dir = golden_dir
        self.results: list[dict[str, Any]] = []

    def load_golden(self) -> list[dict[str, Any]]:
        if not self.golden_dir or not self.golden_dir.exists():
            return []
        out = []
        for p in self.golden_dir.glob("*.json"):
            try:
                out.append(json.loads(p.read_text()))
            except Exception:
                pass
        return out

    async def replay(self, runner: Callable[[dict[str, Any]], Awaitable[Any]]) -> list[dict[str, Any]]:
        goldens = self.load_golden()
        for g in goldens:
            try:
                await runner(g)
                self.results.append({"name": g.get("name"), "status": "pass"})
            except Exception as e:
                self.results.append({"name": g.get("name"), "status": "fail", "error": str(e)})
        return self.results
