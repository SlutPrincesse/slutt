"""Federated trace learning: anonymize and share traces across instances."""
from __future__ import annotations

import hashlib
import json
from typing import Any


class FederatedTraceLearner:
    def __init__(self):
        self._shared: list[dict[str, Any]] = []

    def anonymize(self, event: dict[str, Any]) -> dict[str, Any]:
        e = dict(event)
        # hash identifiers
        for k in ("user", "session_id", "path"):
            if k in e:
                e[k] = hashlib.sha256(str(e[k]).encode()).hexdigest()[:12]
        return e

    def contribute(self, events: list[dict[str, Any]]) -> int:
        n = 0
        for e in events:
            self._shared.append(self.anonymize(e))
            n += 1
        return n

    def aggregate_patterns(self) -> dict[str, int]:
        from collections import Counter
        c = Counter()
        for e in self._shared:
            c[e.get("name", "unknown")] += 1
        return dict(c)
