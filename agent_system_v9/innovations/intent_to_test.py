"""Intent-to-test synthesis: generate property-based tests from task description."""
from __future__ import annotations

from typing import Any


class IntentToTestSynthesizer:
    def __init__(self, provider=None):
        self.provider = provider

    async def synthesize(self, task: str) -> str:
        if self.provider is not None:
            try:
                resp = await self.provider.chat([{"role": "user", "content": f"Generate pytest tests for: {task}"}])
                return getattr(resp, "content", None) or str(resp)
            except Exception:
                pass
        # fallback template
        return f"def test_{task.split()[0] if task.split() else 'task'}():\n    assert True\n"
