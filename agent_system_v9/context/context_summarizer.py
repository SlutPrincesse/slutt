import asyncio
import hashlib
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SummaryTier(Enum):
    IMMEDIATE = "immediate"      # Last 1-5 turns
    RECENT = "recent"            # Last 6-20 turns
    SESSION = "session"          # Current session
    HISTORICAL = "historical"    # Previous sessions
    SEMANTIC = "semantic"        # Key concepts/themes


@dataclass
class Summary:
    id: str
    tier: SummaryTier
    content: str
    source_tokens: int
    summary_tokens: int
    compression_ratio: float
    key_points: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class HierarchicalSummarizer:
    def __init__(self, max_immediate: int = 5, max_recent: int = 20, max_session: int = 100):
        self.max_immediate = max_immediate
        self.max_recent = max_recent
        self.max_session = max_session
        
        self.immediate_summaries: List[Summary] = []
        self.recent_summaries: List[Summary] = []
        self.session_summaries: List[Summary] = []
        self.historical_summaries: List[Summary] = []
        self.semantic_summaries: List[Summary] = []

    def add_interaction(self, user_msg: str, assistant_msg: str, tokens: int) -> Summary:
        combined = f"User: {user_msg}\nAssistant: {assistant_msg}"
        summary = self._create_summary(combined, tokens, SummaryTier.IMMEDIATE)
        self.immediate_summaries.append(summary)
        
        if len(self.immediate_summaries) > self.max_immediate:
            self._promote_to_recent()
        
        return summary

    def _create_summary(self, content: str, tokens: int, tier: SummaryTier) -> Summary:
        summary_text = self._compress(content)
        summary_tokens = len(summary_text.split()) * 1.3
        
        return Summary(
            id=hashlib.sha256(f"{content}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:12],
            tier=tier,
            content=summary_text,
            source_tokens=tokens,
            summary_tokens=int(summary_tokens),
            compression_ratio=tokens / max(1, summary_tokens),
            key_points=self._extract_key_points(content),
            entities=self._extract_entities(content),
        )

    def _compress(self, text: str) -> str:
        sentences = text.split(". ")
        if len(sentences) <= 3:
            return text
        return ". ".join(sentences[:2] + [sentences[-1]]) + "."

    def _extract_key_points(self, text: str) -> List[str]:
        import re
        sentences = re.split(r'[.!?]+', text)
        key_points = [s.strip() for s in sentences if len(s.strip()) > 20]
        return key_points[:5]

    def _extract_entities(self, text: str) -> List[str]:
        import re
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        return list(set(words))[:10]

    def _promote_to_recent(self):
        if not self.immediate_summaries:
            return
        promoted = self.immediate_summaries.pop(0)
        promoted.tier = SummaryTier.RECENT
        self.recent_summaries.append(promoted)
        
        if len(self.recent_summaries) > self.max_recent:
            self._promote_to_session()

    def _promote_to_session(self):
        if not self.recent_summaries:
            return
        promoted = self.recent_summaries.pop(0)
        promoted.tier = SummaryTier.SESSION
        self.session_summaries.append(promoted)
        
        if len(self.session_summaries) > self.max_session:
            self._promote_to_historical()

    def _promote_to_historical(self):
        if not self.session_summaries:
            return
        promoted = self.session_summaries.pop(0)
        promoted.tier = SummaryTier.HISTORICAL
        self.historical_summaries.append(promoted)

    def create_semantic_summary(self, theme: str, related_summaries: List[Summary]) -> Summary:
        combined = f"Theme: {theme}\n" + "\n".join(s.content for s in related_summaries)
        summary = self._create_summary(combined, sum(s.source_tokens for s in related_summaries), SummaryTier.SEMANTIC)
        summary.metadata["theme"] = theme
        summary.metadata["source_summary_ids"] = [s.id for s in related_summaries]
        self.semantic_summaries.append(summary)
        return summary

    def get_context(self, max_tokens: int = 8000) -> str:
        context_parts = []
        token_count = 0
        
        for tier in [SummaryTier.IMMEDIATE, SummaryTier.RECENT, SummaryTier.SESSION, SummaryTier.SEMANTIC, SummaryTier.HISTORICAL]:
            summaries = getattr(self, f"{tier.value}_summaries")
            for summary in reversed(summaries):
                if token_count + summary.summary_tokens > max_tokens:
                    break
                context_parts.append(f"[{tier.value.upper()}] {summary.content}")
                token_count += summary.summary_tokens
        
        return "\n\n".join(reversed(context_parts))

    def get_all_summaries(self) -> List[Summary]:
        all_summaries = []
        for tier in SummaryTier:
            all_summaries.extend(getattr(self, f"{tier.value}_summaries"))
        return all_summaries

    def get_stats(self) -> Dict[str, Any]:
        return {
            "immediate": len(self.immediate_summaries),
            "recent": len(self.recent_summaries),
            "session": len(self.session_summaries),
            "historical": len(self.historical_summaries),
            "semantic": len(self.semantic_summaries),
            "total_tokens": sum(s.summary_tokens for s in self.get_all_summaries()),
        }

    def clear(self):
        self.immediate_summaries.clear()
        self.recent_summaries.clear()
        self.session_summaries.clear()
        self.historical_summaries.clear()
        self.semantic_summaries.clear()