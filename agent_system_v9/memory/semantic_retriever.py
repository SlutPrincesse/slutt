"""Semantic retriever combining vector store + episodic memory."""
from __future__ import annotations

from typing import Any

from .vector_store import VectorStore


class SemanticRetriever:
    def __init__(self, vector_store: VectorStore | None = None, episodic_store=None):
        self.vector_store = vector_store or VectorStore()
        self.episodic_store = episodic_store

    def retrieve(self, query: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        results = self.vector_store.search(query, top_k=top_k)
        out = []
        for entry, score in results:
            out.append({"id": entry.id, "score": score, "payload": entry.payload, "metadata": entry.metadata})
        return out
