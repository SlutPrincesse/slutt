"""In-memory vector store with cosine similarity search."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorEntry:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    def __init__(self):
        self._entries: dict[str, VectorEntry] = {}

    def add(self, entry_id: str, vector: list[float], payload: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._entries[entry_id] = VectorEntry(id=entry_id, vector=list(vector), payload=payload or {}, metadata=metadata or {})

    def remove(self, entry_id: str) -> bool:
        return self._entries.pop(entry_id, None) is not None

    def search(self, query: list[float], top_k: int = 5) -> list[tuple[VectorEntry, float]]:
        results = []
        qn = math.sqrt(sum(x * x for x in query)) or 1.0
        for entry in self._entries.values():
            en = math.sqrt(sum(x * x for x in entry.vector)) or 1.0
            dot = sum(a * b for a, b in zip(query, entry.vector))
            sim = dot / (qn * en)
            results.append((entry, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def size(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
