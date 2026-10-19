"""Lightweight TF-IDF embedding (stdlib, no external deps)."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class TfidfEmbedder:
    def __init__(self):
        self.idf: dict[str, float] = {}
        self.fitted = False

    def fit(self, corpus: list[str]) -> None:
        n = len(corpus)
        df: Counter = Counter()
        for doc in corpus:
            for t in set(tokenize(doc)):
                df[t] += 1
        self.idf = {t: math.log((n + 1) / (df[t] + 1)) + 1 for t in df}
        self.fitted = True

    def embed(self, text: str) -> list[float]:
        tokens = tokenize(text)
        tf = Counter(tokens)
        # Use a fixed vocabulary from idf; if not fitted, derive
        vocab = list(self.idf.keys()) if self.fitted else sorted(set(tokens))
        if not vocab:
            vocab = sorted(set(tokens))
        vec = []
        for t in vocab:
            val = tf.get(t, 0) * (self.idf.get(t, 1.0) if self.fitted else 1.0)
            vec.append(float(val))
        # normalize
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def similarity(self, a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))
