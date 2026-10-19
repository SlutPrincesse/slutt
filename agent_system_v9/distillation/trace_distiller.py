"""Distill traces into reusable patterns."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


class TraceDistiller:
    def __init__(self):
        self._patterns: dict[str, int] = defaultdict(int)

    def distill(self, events: list[Any]) -> dict[str, Any]:
        tool_seq = []
        for e in events:
            kind = getattr(e, "kind", None) or (e.get("kind") if isinstance(e, dict) else "")
            name = getattr(e, "name", None) or (e.get("name") if isinstance(e, dict) else "")
            if kind == "tool_call":
                tool_seq.append(name)
        # frequent subsequences of length 2
        pairs = Counter()
        for i in range(len(tool_seq) - 1):
            pairs[(tool_seq[i], tool_seq[i + 1])] += 1
        top = pairs.most_common(10)
        return {"tool_sequences": [list(p) for p, _ in top], "counts": [c for _, c in top], "total_events": len(events)}

    def patterns(self) -> dict[str, int]:
        return dict(self._patterns)
