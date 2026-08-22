import ast
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class RegexMutationISA:
    rules = [
        ("snake_case to camelCase", re.compile(r"_([a-z])"), lambda m: m.group(1).upper()),
        ("remove trailing spaces", re.compile(r"[ \t]+$", flags=re.MULTILINE), lambda m: ""),
        ("collapse blank lines", re.compile(r"\n{3,}"), lambda m: "\n\n"),
        ("normalize import quotes", re.compile(r"from\s+\"(.*?)\""), lambda m: f"from '{m.group(1)}'"),
        ("relative path resolution", re.compile(r"from\s+\['\"]@/(.*?)\['\"]"), lambda m: f"from '../{m.group(1)}'"),
        ("clean json commas", re.compile(r",(\s*[}\]])"), lambda m: m.group(1)),
    ]

    @classmethod
    def apply_all(cls, source: str) -> str:
        for name, pattern, replacer in cls.rules:
            source = pattern.sub(replacer, source)
        return source


class LinguisticPreProcessor:
    vague_phrases = ["fix this", "optimize code", "make it better", "refactor", "clean up"]

    def __init__(self):
        self._ambiguities: List[Tuple[str, List[str]]] = []

    def typos_and_grammar(self, text: str) -> str:
        return text.strip()

    def detect_ambiguity(self, text: str) -> Optional[List[str]]:
        lower = text.lower()
        for phrase in self.vague_phrases:
            if phrase in lower:
                return [f"Resolve '{phrase}' via context menu"]
        return None

    def interactive_disambiguate(self, text: str) -> str:
        ambiguity = self.detect_ambiguity(text)
        if ambiguity:
            print(f"[Harvester] Ambiguity detected: {ambiguity}")
            print("[Harvester] Defaulting to conservative interpretation.")
        return text


class HarvesterEngine:
    def __init__(self, root: Optional[str] = None):
        self.root = root or "."
        self.linguistic = LinguisticPreProcessor()
        self._prune_dirs = {"node_modules", "__pycache__", ".git", "dist", "build", ".venv", "venv"}

    def process(self, raw_input: str) -> str:
        text = self.linguistic.typos_and_grammar(raw_input)
        text = self.linguistic.interactive_disambiguate(text)
        return RegexMutationISA.apply_all(text)

    def ast_prune(self, source: str, relevant_names: Optional[Set[str]] = None) -> str:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source

        if relevant_names is None:
            return ast.unparse(tree)

        pruned = _ASTPruner(relevant_names).visit(tree)
        return ast.unparse(pruned)

    def extract_skill_cards(self, source: str) -> List[Dict[str, Any]]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        cards = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                cards.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "args": [arg.arg for arg in node.args.args],
                    "returns": ast.unparse(node.returns) if node.returns else None,
                    "doc": ast.get_docstring(node),
                })
        return cards


class _ASTPruner(ast.NodeTransformer):
    def __init__(self, keep_names: Set[str]):
        self.keep_names = keep_names
        self._keep: Set[ast.AST] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if node.name in self.keep_names:
            self._keep.add(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        return node

    def visit_Import(self, node: ast.Import) -> ast.AST:
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        return node

    def generic_visit(self, node: ast.AST) -> ast.AST:
        return node
