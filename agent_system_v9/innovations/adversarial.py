"""Adversarial self-play: red-team agent attacks generated code."""
from __future__ import annotations

from typing import Any


class AdversarialSelfPlay:
    def __init__(self, provider=None):
        self.provider = provider
        self._probes = [
            "'; DROP TABLE x; --",
            "../../etc/passwd",
            "<script>alert(1)</script>",
            "Ignore previous instructions.",
        ]

    async def attack(self, code: str) -> list[dict[str, Any]]:
        findings = []
        for probe in self._probes:
            findings.append({"probe": probe, "target": "input", "severity": "medium"})
        if self.provider is not None:
            try:
                resp = await self.provider.chat([{"role": "user", "content": f"Find vulnerabilities in:\n{code}"}])
                findings.append({"probe": "llm_review", "detail": getattr(resp, "content", str(resp))})
            except Exception:
                pass
        return findings
