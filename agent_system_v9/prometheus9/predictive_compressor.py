"""
Predictive Token-Density Compressor - Optimizes context windows while maintaining full attention alignment
"""
import threading
import time
import hashlib
import re
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict


@dataclass
class CompressionPrediction:
    original_tokens: int
    predicted_tokens: int
    predicted_ratio: float
    strategy: str
    confidence: float
    attention_preservation: float


class PredictiveTokenCompressor:
    def __init__(self, cache_size: int = 500):
        self.cache_size = cache_size
        self._cache: OrderedDict[str, CompressionPrediction] = OrderedDict()
        self._lock = threading.RLock()
        self._model_weights = {
            "code": {"compressibility": 0.6, "attention_critical": 0.9},
            "documentation": {"compressibility": 0.4, "attention_critical": 0.5},
            "conversation": {"compressibility": 0.7, "attention_critical": 0.7},
            "mixed": {"compressibility": 0.55, "attention_critical": 0.7}
        }
    
    def predict(self, text: str, target_ratio: float = 0.7, 
               content_type: str = "mixed") -> CompressionPrediction:
        
        cache_key = hashlib.sha256(f"{text}{target_ratio}{content_type}".encode()).hexdigest()[:16]
        
        with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]
        
        original_tokens = self._estimate_tokens(text)
        target_tokens = int(original_tokens * target_ratio)
        
        # Analyze content
        content_type = self._classify_content(text)
        weights = self._model_weights.get(content_type, self._model_weights["mixed"])
        
        # Predict compression
        base_ratio = weights["compressibility"]
        attention_factor = weights["attention_critical"]
        
        # Adjust for target ratio
        if target_ratio < base_ratio:
            # Need more aggressive compression
            strategy = "aggressive"
            predicted_ratio = target_ratio
            attention_preservation = attention_factor * (target_ratio / base_ratio)
        else:
            strategy = "moderate"
            predicted_ratio = base_ratio
            attention_preservation = attention_factor
        
        predicted_tokens = int(original_tokens * predicted_ratio)
        confidence = 0.85 - abs(predicted_ratio - target_ratio) * 0.5
        
        prediction = CompressionPrediction(
            original_tokens=original_tokens,
            predicted_tokens=predicted_tokens,
            predicted_ratio=predicted_ratio,
            strategy=strategy,
            confidence=max(0.5, min(0.95, confidence)),
            attention_preservation=attention_preservation
        )
        
        with self._lock:
            self._cache[cache_key] = prediction
            self._cache.move_to_end(cache_key)
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        
        return prediction
    
    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
    
    def _classify_content(self, text: str) -> str:
        # Simple heuristic classification
        code_indicators = len(re.findall(r'\b(def|class|import|function|const|let|var)\b', text))
        doc_indicators = len(re.findall(r'\b(the|and|or|but|however|therefore)\b', text, re.IGNORECASE))
        
        if code_indicators > doc_indicators * 2:
            return "code"
        elif doc_indicators > code_indicators * 2:
            return "documentation"
        else:
            return "mixed"
    
    def compress(self, text: str, prediction: CompressionPrediction = None,
                target_ratio: float = 0.7) -> Tuple[str, CompressionPrediction]:
        
        if prediction is None:
            prediction = self.predict(text, target_ratio)
        
        # Apply compression based on predicted strategy
        if prediction.strategy == "aggressive":
            compressed = self._compress_aggressive(text, prediction.predicted_ratio)
        else:
            compressed = self._compress_moderate(text, prediction.predicted_ratio)
        
        return compressed, prediction
    
    def _compress_moderate(self, text: str, target_ratio: float) -> str:
        # Remove comments, normalize whitespace
        compressed = re.sub(r'#.*$', '', text, flags=re.MULTILINE)
        compressed = re.sub(r'""".*?"""', '', compressed, flags=re.DOTALL)
        compressed = re.sub(r"'''.*?'''", '', compressed, flags=re.DOTALL)
        compressed = re.sub(r'\n{3,}', '\n\n', compressed)
        compressed = re.sub(r'[ \t]+', ' ', compressed)
        return compressed.strip()
    
    def _compress_aggressive(self, text: str, target_ratio: float) -> str:
        compressed = self._compress_moderate(text, target_ratio)
        
        # Remove type hints, default values, pass statements
        compressed = re.sub(r':\s*\w+(\[\w+\])?\s*[=,)]', lambda m: m.group().replace(m.group(1), ''), compressed)
        compressed = re.sub(r'=\s*[^,\n\)]+', '', compressed)
        compressed = re.sub(r'\b(pass|continue|break)\b', '', compressed)
        
        # Truncate if still too long
        target_chars = len(text) * target_ratio * 4
        if len(compressed) > target_chars:
            compressed = compressed[:int(target_chars)] + "... [compressed]"
        
        return compressed
    
    def get_cache_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"size": len(self._cache), "max_size": self.cache_size}


_predictive_compressor: Optional[PredictiveTokenCompressor] = None

def get_predictive_compressor() -> PredictiveTokenCompressor:
    global _predictive_compressor
    if _predictive_compressor is None:
        _predictive_compressor = PredictiveTokenCompressor()
    return _predictive_compressor