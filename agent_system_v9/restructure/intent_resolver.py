"""
Zero-Latency Intent Resolution Pipeline - Prioritizes cached heuristic matches before LLM execution
"""
import threading
import time
import hashlib
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict


@dataclass
class IntentMatch:
    intent_id: str
    pattern: str
    intent_type: str
    confidence: float
    handler: Callable
    metadata: Dict[str, Any] = field(default_factory=dict)
    usage_count: int = 0
    last_used: float = field(default_factory=time.time)
    avg_latency_ms: float = 0.0


class IntentResolver:
    def __init__(self, cache_size: int = 1000, cache_ttl: float = 600):
        self.cache_size = cache_size
        self.cache_ttl = cache_ttl
        self._patterns: List[IntentMatch] = []
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.RLock()
        self._llm_handler: Optional[Callable] = None
        self._stats = {"cache_hits": 0, "cache_misses": 0, "llm_calls": 0, "total_latency_ms": 0}
    
    def register_intent(self, pattern: str, intent_type: str, handler: Callable,
                       confidence: float = 0.8, metadata: Dict = None) -> str:
        intent_id = hashlib.sha256(f"{pattern}{intent_type}".encode()).hexdigest()[:12]
        
        match = IntentMatch(
            intent_id=intent_id,
            pattern=pattern,
            intent_type=intent_type,
            confidence=confidence,
            handler=handler,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._patterns.append(match)
            self._patterns.sort(key=lambda x: -x.confidence)
        
        return intent_id
    
    def set_llm_handler(self, handler: Callable[[str], Any]):
        self._llm_handler = handler
    
    def resolve(self, query: str, context: Dict = None) -> Tuple[Any, str, float]:
        start = time.time()
        
        # Check cache first
        cache_key = hashlib.sha256(f"{query}{str(context)}".encode()).hexdigest()[:16]
        
        with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                self._stats["cache_hits"] += 1
                return self._cache[cache_key], "cache", (time.time() - start) * 1000
        
        # Try pattern matching
        for match in self._patterns:
            if self._match_pattern(query, match.pattern):
                match.usage_count += 1
                match.last_used = time.time()
                
                try:
                    result = match.handler(query, context)
                    latency = (time.time() - start) * 1000
                    match.avg_latency_ms = (match.avg_latency_ms * (match.usage_count - 1) + latency) / match.usage_count
                    
                    with self._lock:
                        self._cache[cache_key] = result
                        if len(self._cache) > self.cache_size:
                            self._cache.popitem(last=False)
                    
                    return result, "pattern", latency
                except Exception:
                    continue
        
        # Fallback to LLM
        if self._llm_handler:
            self._stats["llm_calls"] += 1
            try:
                result = self._llm_handler(query, context)
                latency = (time.time() - start) * 1000
                self._stats["total_latency_ms"] += latency
                
                with self._lock:
                    self._cache[cache_key] = result
                    if len(self._cache) > self.cache_size:
                        self._cache.popitem(last=False)
                
                return result, "llm", latency
            except Exception as e:
                pass
        
        return None, "none", (time.time() - start) * 1000
    
    def _match_pattern(self, query: str, pattern: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(query.lower(), pattern.lower())
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                "cache_size": len(self._cache),
                "patterns": len(self._patterns),
                "cache_hit_rate": self._stats["cache_hits"] / max(1, self._stats["cache_hits"] + self._stats["cache_misses"])
            }
    
    def clear_cache(self):
        with self._lock:
            self._cache.clear()


_intent_resolver: Optional[IntentResolver] = None

def get_intent_resolver() -> IntentResolver:
    global _intent_resolver
    if _intent_resolver is None:
        from ..core.config import config
        ttl = config.get_param("restructure", "intent_cache_ttl", 600)
        _intent_resolver = IntentResolver(cache_ttl=ttl)
    return _intent_resolver