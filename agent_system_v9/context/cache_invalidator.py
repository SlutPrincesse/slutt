import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class InvalidationTrigger(Enum):
    TOKEN_LIMIT = "token_limit"
    TIME_EXPIRY = "time_expiry"
    RELEVANCE_DROP = "relevance_drop"
    TOOL_EXECUTION = "tool_execution"
    ERROR_OCCURRED = "error_occurred"
    CONTEXT_SWITCH = "context_switch"
    MANUAL = "manual"


@dataclass
class InvalidationRule:
    id: str
    name: str
    trigger: InvalidationTrigger
    condition: Callable[[Dict[str, Any]], bool]
    action: Callable[[Dict[str, Any]], Any]
    priority: int = 50
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha256(f"{self.name}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:12]


class CacheInvalidator:
    def __init__(self, max_cache_size: int = 1000):
        self.max_cache_size = max_cache_size
        self.rules: List[InvalidationRule] = []
        self._cache: Dict[str, Any] = OrderedDict()
        self._access_times: Dict[str, datetime] = {}
        self._token_counts: Dict[str, int] = {}
        self._relevance_scores: Dict[str, float] = {}

    def add_rule(self, rule: InvalidationRule):
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        for i, rule in enumerate(self.rules):
            if rule.id == rule_id:
                self.rules.pop(i)
                return True
        return False

    def put(self, key: str, value: Any, tokens: int = 0, relevance: float = 1.0):
        if len(self._cache) >= self.max_cache_size:
            self._evict_lru()
        
        self._cache[key] = value
        self._access_times[key] = datetime.utcnow()
        self._token_counts[key] = tokens
        self._relevance_scores[key] = relevance

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            self._access_times[key] = datetime.utcnow()
            return self._cache[key]
        return None

    def invalidate(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            self._access_times.pop(key, None)
            self._token_counts.pop(key, None)
            self._relevance_scores.pop(key, None)
            return True
        return False

    def invalidate_by_trigger(self, trigger: InvalidationTrigger, context: Dict[str, Any]) -> List[str]:
        invalidated = []
        for rule in self.rules:
            if rule.enabled and rule.trigger == trigger:
                try:
                    if rule.condition(context):
                        result = rule.action(context)
                        if isinstance(result, list):
                            for key in result:
                                self.invalidate(key)
                                invalidated.append(key)
                        elif result:
                            self.invalidate(str(result))
                            invalidated.append(str(result))
                except Exception:
                    pass
        return invalidated

    def _evict_lru(self):
        if not self._access_times:
            return
        oldest = min(self._access_times.items(), key=lambda x: x[1])[0]
        self.invalidate(oldest)

    def invalidate_low_relevance(self, threshold: float = 0.3) -> List[str]:
        invalidated = []
        for key, score in list(self._relevance_scores.items()):
            if score < threshold:
                self.invalidate(key)
                invalidated.append(key)
        return invalidated

    def invalidate_by_tokens(self, max_tokens: int) -> List[str]:
        total_tokens = sum(self._token_counts.values())
        if total_tokens <= max_tokens:
            return []
        
        sorted_keys = sorted(self._token_counts.items(), key=lambda x: x[1], reverse=True)
        invalidated = []
        for key, tokens in sorted_keys:
            if total_tokens <= max_tokens:
                break
            self.invalidate(key)
            total_tokens -= tokens
            invalidated.append(key)
        return invalidated

    def get_cache_stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self.max_cache_size,
            "total_tokens": sum(self._token_counts.values()),
            "avg_relevance": sum(self._relevance_scores.values()) / max(1, len(self._relevance_scores)),
            "rules_count": len(self.rules),
        }

    def clear(self):
        self._cache.clear()
        self._access_times.clear()
        self._token_counts.clear()
        self._relevance_scores.clear()