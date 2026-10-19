"""
Context Compressor - extractive summarization, rolling summary, dedupe.

Complements ContextWindow by providing reusable compression primitives that
do not depend on an LLM provider. Token estimation aligned with
DynamicPromptAssembler._estimate_tokens (chars // 4).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "at", "for", "with", "by", "from", "as",
    "and", "or", "but", "not", "this", "that", "these", "those", "it",
    "its", "i", "you", "he", "she", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "our", "their", "what", "which",
    "who", "whom", "when", "where", "why", "how", "all", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "only", "own",
    "same", "so", "than", "too", "very", "can", "will", "just", "should",
    "now", "do", "does", "did", "doing", "have", "has", "had", "having",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _fingerprint(text: str) -> str:
    tokens = [t for t in re.findall(r"\w+", _normalize(text)) if t not in _STOPWORDS]
    return " ".join(sorted(set(tokens)))


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


@dataclass
class CompressionResult:
    summary: str
    source_tokens: int
    summary_tokens: int
    compression_ratio: float


class ContextCompressor:
    """Extractive + optional abstractive context compression."""

    def __init__(self, llm_provider: Optional[Callable[[str, int], str]] = None):
        self.llm_provider = llm_provider

    def summarize(self, text: str, max_tokens: int = 256) -> CompressionResult:
        source_tokens = estimate_tokens(text)
        if source_tokens <= max_tokens:
            return CompressionResult(
                summary=text,
                source_tokens=source_tokens,
                summary_tokens=source_tokens,
                compression_ratio=1.0,
            )

        # Optional LLM abstraction when provider configured.
        if self.llm_provider is not None:
            try:
                abstract = self.llm_provider(text, max_tokens)
                if abstract and estimate_tokens(abstract) <= max_tokens:
                    return CompressionResult(
                        summary=abstract,
                        source_tokens=source_tokens,
                        summary_tokens=estimate_tokens(abstract),
                        compression_ratio=source_tokens / max(1, estimate_tokens(abstract)),
                    )
            except Exception:
                pass

        summary = self._extractive(text, max_tokens)
        return CompressionResult(
            summary=summary,
            source_tokens=source_tokens,
            summary_tokens=estimate_tokens(summary),
            compression_ratio=source_tokens / max(1, estimate_tokens(summary)),
        )

    def _extractive(self, text: str, max_tokens: int) -> str:
        sentences = _split_sentences(text)
        if not sentences:
            return text[: max_tokens * 4]

        # Keyword frequency
        words = [w for w in re.findall(r"\w+", text.lower()) if w not in _STOPWORDS]
        freq: dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1

        scored = []
        for idx, sent in enumerate(sentences):
            sent_words = [w for w in re.findall(r"\w+", sent.lower()) if w not in _STOPWORDS]
            score = sum(freq.get(w, 0) for w in sent_words)
            # position bias: first and last sentences boosted
            if idx == 0:
                score += len(sent_words)
            if idx == len(sentences) - 1:
                score += len(sent_words) // 2
            scored.append((score, idx, sent))

        # Greedy select highest-scoring until budget
        selected_idx = set()
        selected: list[tuple[int, str]] = []
        total = 0
        for score, idx, sent in sorted(scored, key=lambda x: (-x[0], x[1])):
            cost = estimate_tokens(sent)
            if total + cost > max_tokens:
                continue
            selected.append((idx, sent))
            selected_idx.add(idx)
            total += cost
            if total >= max_tokens * 0.9:
                break

        # Restore original order
        selected.sort(key=lambda x: x[0])
        return " ".join(s for _, s in selected) if selected else sentences[0][: max_tokens * 4]

    def rolling_summary(
        self,
        history: list[dict[str, str]] | list[str],
        new_messages: list[dict[str, str]] | list[str],
        budget: int = 4000,
        verbatim_tail: int = 8,
    ) -> tuple[str, list]:
        """Return (running_summary, verbatim_tail_messages)."""
        all_msgs = list(history) + list(new_messages)

        def _content(m):
            if isinstance(m, str):
                return m
            return m.get("content", "")

        def _role(m):
            if isinstance(m, str):
                return "user"
            return m.get("role", "user")

        if len(all_msgs) <= verbatim_tail:
            return "", all_msgs

        older = all_msgs[:-verbatim_tail]
        tail = all_msgs[-verbatim_tail:]
        combined = "\n".join(f"{_role(m)}: {_content(m)}" for m in older)
        source_tokens = estimate_tokens(combined)
        # cap summary to a fraction of budget
        summary_budget = max(64, budget // 4)
        result = self.summarize(combined, summary_budget)
        summary = result.summary
        # ensure total under budget
        tail_tokens = sum(estimate_tokens(_content(m)) for m in tail)
        while estimate_tokens(summary) + tail_tokens > budget and len(summary) > 64:
            summary = summary[: len(summary) // 2]
        return summary, tail

    def dedupe(self, history: list) -> list:
        """Remove near-duplicate messages by normalized fingerprint."""
        seen: set[str] = set()
        result = []
        for m in history:
            content = m if isinstance(m, str) else (m.get("content", "") if isinstance(m, dict) else getattr(m, "content", ""))
            fp = _fingerprint(content)
            if fp in seen and fp:
                continue
            if fp:
                seen.add(fp)
            result.append(m)
        return result
