"""Local pre-processor: reduces what is sent to the LLM.

- AST-based project pruning (Python) to surface only relevant symbols.
- Lightweight typo normalization (SymSpell-lite, stdlib only).
- Vague-command detection for local disambiguation.
- Deterministic cleanup regexes (spec §5.2).
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# Deterministic cleanup rules (spec §5.2). Order matters.
CLEANUP_RULES = [
    ("trailing_ws", re.compile(r"[ \t]+$"), ""),
    ("collapse_blank", re.compile(r"\n{3,}"), "\n\n"),
    ("json_trailing_comma", re.compile(r",(\s*[}\]])"), r"\1"),
    ("normalize_import_quotes", re.compile(r'from\s+"([^"]*)"'), r"from '\1'"),
    ("snake_to_camel", re.compile(r"_([a-z])"), lambda m: m.group(1).upper()),
]

VAGUE_PHRASES = {
    "fix this": ["Fix the failing tests", "Fix a specific lint error", "Fix a runtime exception"],
    "optimize code": ["Reduce time complexity", "Reduce memory usage", "Improve readability"],
    "clean up": ["Remove dead code", "Reformat / style only", "Split large functions"],
    "refactor": ["Rename for clarity", "Extract helper functions", "Restructure modules"],
    "make it better": ["Add tests", "Improve error handling", "Improve documentation"],
}

_IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", ".shadow"}

DEFAULT_WORDS = set(
    """
the be to of and a in that have i it for not on with he as you do at this but his by from they
we say her she or an will my one all would there their what so up out if about who get which go me
when make can like time no just him know take people into year your good some could them see other
than then now look only come its over think also back after use two how our work first well way even
new want because any these give day most us is are was were function class return import from def
value data list dict string int float bool none true false self this that with without error test
code file path module system number example result state index node token model input output
""".split()
)


@dataclass
class Symbol:
    name: str
    kind: str
    file: str
    lineno: int
    end_lineno: int
    doc: str


class ProjectIndex:
    """Walks a directory, parses .py files, and indexes symbols."""

    def __init__(self, root: str):
        self.root = Path(root)
        self.symbols: List[Symbol] = []
        self.build()

    def build(self) -> None:
        if not self.root.exists():
            return
        for path in self.root.rglob("*.py"):
            if any(part in _IGNORE_DIRS for part in path.parts):
                continue
            self._index_file(path)

    def _index_file(self, path: Path) -> None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node) or ""
                self.symbols.append(
                    Symbol(
                        name=node.name,
                        kind=type(node).__name__,
                        file=str(path),
                        lineno=node.lineno,
                        end_lineno=getattr(node, "end_lineno", node.lineno) or node.lineno,
                        doc=doc,
                    )
                )

    def select(self, task: str, top_k: int = 15) -> List[Symbol]:
        keywords = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", task.lower()))
        if not keywords:
            return self.symbols[:top_k]
        scored = []
        for s in self.symbols:
            text = (s.name + " " + s.doc).lower()
            score = sum(1 for k in keywords if k in text)
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]


class TypoCorrector:
    """Minimal SymSpell-style corrector (edit distance 1, stdlib only)."""

    def __init__(self, words: Optional[set] = None):
        self.words = set(w.lower() for w in (words or DEFAULT_WORDS))

    def _edits1(self, word: str) -> set:
        letters = "abcdefghijklmnopqrstuvwxyz"
        splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
        deletes = [a + b[1:] for a, b in splits if b]
        transposes = [a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1]
        replaces = [a + c + b[1:] for a, b in splits if b for c in letters]
        inserts = [a + c + b for a, b in splits for c in letters]
        return set(deletes + transposes + replaces + inserts)

    def correct(self, word: str) -> str:
        w = word.lower().strip(".,!?;:")
        if not w or w in self.words:
            return word
        candidates = self._edits1(w) & self.words
        if candidates:
            return max(candidates, key=len)
        return word

    def correct_text(self, text: str) -> str:
        return re.sub(r"\b[a-zA-Z]+\b", lambda m: self.correct(m.group(0)), text)


def detect_vague(task: str) -> Tuple[Optional[str], Optional[list]]:
    lowered = task.lower()
    for phrase, options in VAGUE_PHRASES.items():
        if phrase in lowered:
            return phrase, options
    return None, None


class PreProcessor:
    def __init__(self, root: str, dict_words: Optional[set] = None):
        self.index = ProjectIndex(root)
        self.corrector = TypoCorrector(dict_words)

    def build_context(self, task: str, top_k: int = 15) -> str:
        symbols = self.index.select(task, top_k)
        entries = []
        for s in symbols:
            try:
                src = Path(s.file).read_text(errors="ignore").splitlines()
                snippet = "\n".join(src[s.lineno - 1 : s.end_lineno])
            except Exception:
                snippet = ""
            entries.append(
                {
                    "file": s.file,
                    "name": s.name,
                    "kind": s.kind,
                    "lines": [s.lineno, s.end_lineno],
                    "snippet": snippet,
                }
            )
        bundle = {"task": task, "symbol_count": len(entries), "symbols": entries}
        return json.dumps(bundle, indent=2)

    def cleanup_text(self, text: str) -> str:
        for _name, pat, repl in CLEANUP_RULES:
            text = pat.sub(repl, text)
        return text
