"""
Context Window - session-scoped context store that bounds the effective
context fed to the model so long coding sessions do not suffer context rot.

Keeps the most recent messages verbatim and compresses older messages into a
rolling summary via the HierarchicalSummarizer. Exposes a model-ready message
list whose estimated token count never exceeds the configured budget.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .context_summarizer import HierarchicalSummarizer, SummaryTier

DEFAULT_BUDGET_TOKENS = int(os.getenv("V9_CONTEXT_BUDGET_TOKENS", "4000"))
DEFAULT_VERBATIM_TAIL = int(os.getenv("V9_CONTEXT_VERBATIM_TAIL", "8"))


def estimate_tokens(text: str) -> int:
    """Rough token estimate aligned with DynamicPromptAssembler (~4 chars/token)."""
    return max(1, len(text) // 4)


@dataclass
class ContextMessage:
    role: str  # system, user, assistant, tool
    content: str
    tokens: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.tokens == 0:
            self.tokens = estimate_tokens(self.content)


class ContextWindow:
    """Session-scoped rolling context window with automatic compression."""

    def __init__(
        self,
        session_id: str = "default",
        budget_tokens: int = DEFAULT_BUDGET_TOKENS,
        verbatim_tail: int = DEFAULT_VERBATIM_TAIL,
        storage_path: Path | None = None,
    ):
        self.session_id = session_id
        self.budget_tokens = budget_tokens
        self.verbatim_tail = verbatim_tail
        self.storage_path = storage_path

        self.messages: list[ContextMessage] = []
        self.summarizer = HierarchicalSummarizer()
        self._running_summary: str = ""
        self._running_summary_tokens: int = 0

        if storage_path and storage_path.exists():
            self.load(storage_path)

    def append(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> ContextMessage:
        message = ContextMessage(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(message)
        self._maybe_compress()
        return message

    def get_messages(self) -> list[ContextMessage]:
        return list(self.messages)

    def get_messages_for_model(self) -> list[dict[str, str]]:
        self._maybe_compress()

        messages: list[dict[str, str]] = []

        if self._running_summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"[Compressed conversation memory]\n{self._running_summary}",
                }
            )

        tail = self.messages[-self.verbatim_tail :] if self.verbatim_tail > 0 else []
        for message in tail:
            messages.append({"role": message.role, "content": message.content})

        return messages

    def get_total_tokens(self) -> int:
        return sum(m.tokens for m in self.messages) + self._running_summary_tokens

    def _maybe_compress(self):
        total = self.get_total_tokens()
        if total <= self.budget_tokens:
            return

        if len(self.messages) <= self.verbatim_tail:
            return

        older = self.messages[: -self.verbatim_tail]
        combined = "\n".join(f"{m.role}: {m.content}" for m in older)
        source_tokens = sum(m.tokens for m in older)

        summary = self.summarizer._create_summary(
            combined, source_tokens, SummaryTier.SESSION
        )

        self.messages = self.messages[-self.verbatim_tail :]
        self._running_summary = summary.content
        self._running_summary_tokens = summary.summary_tokens

        self.summarizer.session_summaries.append(summary)

    def save(self, path: Path | None = None):
        path = path or self.storage_path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": self.session_id,
            "budget_tokens": self.budget_tokens,
            "verbatim_tail": self.verbatim_tail,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "tokens": m.tokens,
                    "timestamp": m.timestamp,
                    "metadata": m.metadata,
                }
                for m in self.messages
            ],
            "running_summary": self._running_summary,
            "running_summary_tokens": self._running_summary_tokens,
        }
        path.write_text(json.dumps(data, indent=2))

    def load(self, path: Path):
        data = json.loads(path.read_text())
        self.session_id = data.get("session_id", self.session_id)
        self.budget_tokens = data.get("budget_tokens", self.budget_tokens)
        self.verbatim_tail = data.get("verbatim_tail", self.verbatim_tail)
        self.messages = [
            ContextMessage(
                role=item["role"],
                content=item["content"],
                tokens=item.get("tokens", 0),
                timestamp=item.get("timestamp", ""),
                metadata=item.get("metadata", {}),
            )
            for item in data.get("messages", [])
        ]
        self._running_summary = data.get("running_summary", "")
        self._running_summary_tokens = data.get("running_summary_tokens", 0)

    def clear(self):
        self.messages.clear()
        self._running_summary = ""
        self._running_summary_tokens = 0

    def get_stats(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "budget_tokens": self.budget_tokens,
            "verbatim_tail": self.verbatim_tail,
            "message_count": len(self.messages),
            "total_tokens": self.get_total_tokens(),
            "running_summary_tokens": self._running_summary_tokens,
            "summarizer": self.summarizer.get_stats(),
        }
