from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_ROLE_PREFIX = r"(?:^|\n|(?<=[.!?])\s)\s*(?:system|assistant|user)\s*:"

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(_ROLE_PREFIX),
    re.compile(r"(ignore|disregard)\s+(?:the\s+|all\s+|any\s+)*"
               r"(?:previous|prior|above|earlier|your)?\s*instructions?"),
    re.compile(r"forget\s+(?:all\s+)?(?:previous|your)\s+instructions?"),
    re.compile(r"new\s+instructions?\s*:"),
    re.compile(r"<\s*system\s*>"),
    re.compile(r"\[inst\]"),
    re.compile(r"#{2,}\s*instruction"),
    re.compile(r"(?:notice|instructions?|message)\s+for\s+ai\s+(?:agents?|assistants?)"),
    re.compile(r"your\s+(?:real\s+)?task\s+has\s+changed"),
    re.compile(r"everything\s+written\s+above"),
    re.compile(r"<\|im_start\|>"),
    re.compile(r"<<sys>>"),
]

_ZERO_WIDTH = re.compile(
    "[\u200b-\u200f\u2060-\u206f\ufeff]"
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "і": "i", "ѕ": "s", "ԁ": "d", "ɡ": "g", "ν": "v", "ο": "o", "ρ": "p",
    "α": "a", "ϲ": "c", "ѡ": "w", "м": "m", "т": "t", "н": "h", "к": "k",
})


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    return text.lower().translate(_CONFUSABLES)


@dataclass
class ScanResult:
    is_clean: bool
    detections: list[str] = field(default_factory=list)
    safe_text: str = ""
    original_text: str = ""

    @property
    def was_modified(self) -> bool:
        return self.safe_text != self.original_text


class InjectionDetector:
    def scan(self, text: str) -> ScanResult:
        detections = self._detect(text)
        if not detections:
            return ScanResult(is_clean=True, safe_text=text, original_text=text)
        return ScanResult(
            is_clean=False,
            detections=detections,
            safe_text=self._strip_injections(text),
            original_text=text,
        )

    def _detect(self, text: str) -> list[str]:
        flat = re.sub(r"\s+", " ", _normalize(text))
        anchored = _normalize(text)
        found: list[str] = []
        for pattern in _INJECTION_PATTERNS:
            target = anchored if pattern.pattern is _ROLE_PREFIX else flat
            if pattern.search(target) or pattern.search(anchored):
                found.append(pattern.pattern)
        return found

    def _looks_injected(self, line: str) -> bool:
        flat = re.sub(r"\s+", " ", _normalize(line))
        return any(p.search(flat) or p.search(_normalize(line))
                   for p in _INJECTION_PATTERNS)

    def _clean_line(self, line: str) -> str:
        if not self._looks_injected(line):
            return line
        sentences = _SENTENCE_SPLIT.split(line)
        if len(sentences) == 1:
            return ""
        survivors = [s for s in sentences if not self._looks_injected(s)]
        return " ".join(survivors).strip()

    def _strip_injections(self, text: str) -> str:
        lines = text.split("\n")
        kept = [self._clean_line(line) for line in lines]
        for i in range(len(kept) - 1):
            if not kept[i] or not kept[i + 1]:
                continue
            if self._looks_injected(f"{kept[i]} {kept[i + 1]}"):
                kept[i] = ""
                kept[i + 1] = ""
        return "\n".join(kept).strip()
