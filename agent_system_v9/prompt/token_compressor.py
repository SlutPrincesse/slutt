"""
Token Density Compressor - Semantic token optimizer compressing verbose text blocks without loss of intent
"""
import hashlib
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CompressionStrategy(Enum):
    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    AGGRESSIVE = "aggressive"
    LOSSLESS = "lossless"


@dataclass
class CompressionResult:
    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    strategy: CompressionStrategy
    preserved_elements: list[str] = field(default_factory=list)
    removed_elements: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class TokenDensityCompressor:
    def __init__(self, cache_size: int = 1000):
        self.cache_size = cache_size
        self._cache: OrderedDict[str, CompressionResult] = OrderedDict()
        self._lock = threading.RLock()

        # Patterns for compression
        self._patterns = {
            "whitespace": re.compile(r'\s+'),
            "multiple_newlines": re.compile(r'\n{3,}'),
            "comments": re.compile(r'#.*$|//.*$|/\*.*?\*/', re.MULTILINE | re.DOTALL),
            "docstrings": re.compile(r'""".*?"""|\'\'\'.*?\'\'\'', re.DOTALL),
            "type_hints": re.compile(r':\s*\w+(\[\w+\])?\s*='),
            "default_values": re.compile(r'=\s*[^,\n]+'),
            "redundant_words": re.compile(r'\b(very|really|quite|rather|somewhat|basically|actually|literally)\b', re.IGNORECASE),
            "filler_phrases": re.compile(r'\b(in order to|due to the fact that|at this point in time|it is important to note that)\b', re.IGNORECASE),
            "duplicate_lines": re.compile(r'^(.+)\n\1$', re.MULTILINE),
        }

        # Semantic patterns to preserve
        self._preserve_patterns = [
            re.compile(r'\b(def|class|async|await|import|from|return|yield|raise|try|except|finally|with|lambda)\b'),
            re.compile(r'\b(if|else|elif|for|while|match|case|break|continue|pass)\b'),
            re.compile(r'[{}()\[\]]'),
            re.compile(r'["\'].*?["\']'),  # Strings
            re.compile(r'#.*$'),  # Comments (configurable)
        ]

    def compress(self, text: str, strategy: CompressionStrategy = CompressionStrategy.SEMANTIC,
                 target_ratio: float = 0.7, preserve_comments: bool = False) -> CompressionResult:
        # Check cache
        cache_key = hashlib.sha256(f"{text}{strategy}{target_ratio}{preserve_comments}".encode()).hexdigest()[:16]

        with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]

        original_tokens = self._estimate_tokens(text)
        target_tokens = int(original_tokens * target_ratio)

        compressed = text
        preserved = []
        removed = []

        if strategy == CompressionStrategy.LOSSLESS:
            compressed, preserved, removed = self._lossless_compress(compressed, preserve_comments)
        elif strategy == CompressionStrategy.STRUCTURAL:
            compressed, preserved, removed = self._structural_compress(compressed, preserve_comments)
        elif strategy == CompressionStrategy.AGGRESSIVE:
            compressed, preserved, removed = self._aggressive_compress(compressed, preserve_comments)
        else:  # SEMANTIC
            compressed, preserved, removed = self._semantic_compress(compressed, preserve_comments, target_tokens)

        compressed_tokens = self._estimate_tokens(compressed)
        actual_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

        result = CompressionResult(
            original_text=text,
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=actual_ratio,
            strategy=strategy,
            preserved_elements=preserved,
            removed_elements=removed,
            metadata={
                "target_ratio": target_ratio,
                "preserve_comments": preserve_comments,
            }
        )

        with self._lock:
            self._cache[cache_key] = result
            self._cache.move_to_end(cache_key)
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

        return result

    def _lossless_compress(self, text: str, preserve_comments: bool) -> tuple[str, list[str], list[str]]:
        preserved = []
        removed = []

        # Normalize whitespace
        compressed = self._patterns["whitespace"].sub(' ', text)
        compressed = self._patterns["multiple_newlines"].sub('\n\n', compressed)

        preserved.append("whitespace_structure")
        removed.append("excess_whitespace")

        return compressed.strip(), preserved, removed

    def _structural_compress(self, text: str, preserve_comments: bool) -> tuple[str, list[str], list[str]]:
        preserved = []
        removed = []
        compressed = text

        # Remove duplicate lines
        compressed = self._patterns["duplicate_lines"].sub(r'\1', compressed)
        removed.append("duplicate_lines")

        # Normalize whitespace
        compressed = self._patterns["whitespace"].sub(' ', compressed)
        compressed = self._patterns["multiple_newlines"].sub('\n\n', compressed)
        preserved.append("structure")
        removed.append("excess_whitespace")

        # Remove type hints from assignments (keep in signatures)
        compressed = re.sub(r':\s*\w+(\[\w+\])?\s*=', ' =', compressed)
        removed.append("inline_type_hints")

        return compressed.strip(), preserved, removed

    def _semantic_compress(self, text: str, preserve_comments: bool, target_tokens: int) -> tuple[str, list[str], list[str]]:
        preserved = []
        removed = []
        compressed = text

        # First pass: lossless
        compressed, p, r = self._lossless_compress(compressed, preserve_comments)
        preserved.extend(p)
        removed.extend(r)

        # Second pass: structural
        compressed, p, r = self._structural_compress(compressed, preserve_comments)
        preserved.extend(p)
        removed.extend(r)

        # Third pass: semantic - remove filler but preserve meaning
        current_tokens = self._estimate_tokens(compressed)

        if current_tokens > target_tokens:
            # Remove filler phrases
            compressed = self._patterns["filler_phrases"].sub('', compressed)
            removed.append("filler_phrases")

            # Remove redundant adjectives
            compressed = self._patterns["redundant_words"].sub('', compressed)
            removed.append("redundant_words")

            # Compress verbose explanations
            compressed = self._compress_explanations(compressed)
            removed.append("verbose_explanations")

            # Normalize again
            compressed = self._patterns["whitespace"].sub(' ', compressed)
            compressed = self._patterns["multiple_newlines"].sub('\n\n', compressed)

        # Ensure we preserve critical semantic elements
        preserved.append("semantic_structure")
        preserved.append("code_blocks")
        preserved.append("key_instructions")

        return compressed.strip(), preserved, removed

    def _aggressive_compress(self, text: str, preserve_comments: bool) -> tuple[str, list[str], list[str]]:
        preserved = []
        removed = []
        compressed = text

        # Apply all compressions
        compressed, p, r = self._semantic_compress(compressed, preserve_comments, 0)
        preserved.extend(p)
        removed.extend(r)

        # Additional aggressive compressions
        if not preserve_comments:
            compressed = self._patterns["comments"].sub('', compressed)
            compressed = self._patterns["docstrings"].sub('', compressed)
            removed.append("comments")
            removed.append("docstrings")

        # Remove default values in function signatures
        compressed = re.sub(r'=\s*[^,\n\)]+', '', compressed)
        removed.append("default_values")

        # Compress variable names (keep first char + hash)
        compressed = self._compress_identifiers(compressed)
        removed.append("verbose_identifiers")

        # Final cleanup
        compressed = self._patterns["whitespace"].sub(' ', compressed)
        compressed = self._patterns["multiple_newlines"].sub('\n\n', compressed)

        preserved.append("core_logic")

        return compressed.strip(), preserved, removed

    def _compress_explanations(self, text: str) -> str:
        # Compress verbose explanatory sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        compressed_sentences = []

        for sent in sentences:
            # Skip very short sentences (likely code)
            if len(sent) < 20:
                compressed_sentences.append(sent)
                continue

            # Check if it's an explanation pattern
            if re.search(r'\b(this|that|which|who|where|how|why)\s+(is|are|was|were|does|do|did)', sent, re.IGNORECASE):
                # Compress to key point
                words = sent.split()
                if len(words) > 15:
                    # Keep first 10 and last 5 words
                    compressed_sentences.append(' '.join(words[:10] + ['...'] + words[-5:]))
                else:
                    compressed_sentences.append(sent)
            else:
                compressed_sentences.append(sent)

        return ' '.join(compressed_sentences)

    def _compress_identifiers(self, text: str) -> str:
        # Find long identifiers and compress them
        def replace_long_id(match):
            identifier = match.group(0)
            if len(identifier) > 20 and identifier.isidentifier():
                # Keep first 8 chars + hash
                hash_suffix = hashlib.md5(identifier.encode()).hexdigest()[:4]
                return identifier[:8] + '_' + hash_suffix
            return identifier

        # Match identifiers (variable names, function names, etc.)
        compressed = re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]{19,}\b', replace_long_id, text)
        return compressed

    def _estimate_tokens(self, text: str) -> int:
        # Rough estimation: ~4 chars per token for English/code
        return max(1, len(text) // 4)

    def batch_compress(self, texts: list[str], strategy: CompressionStrategy = CompressionStrategy.SEMANTIC,
                       target_ratio: float = 0.7) -> list[CompressionResult]:
        return [self.compress(text, strategy, target_ratio) for text in texts]

    def clear_cache(self):
        with self._lock:
            self._cache.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.cache_size,
            }


_compressor: TokenDensityCompressor | None = None


def get_token_compressor() -> TokenDensityCompressor:
    global _compressor
    if _compressor is None:
        _compressor = TokenDensityCompressor()
    return _compressor
