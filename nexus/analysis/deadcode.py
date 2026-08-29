"""Dead code detection: functions never referenced anywhere in the project.

A conservative whole-project reference analysis. A function is flagged
only when its name is never used outside its own definition — as a call,
attribute access, decorator, argument, export, or string reference in
``__all__``. Entry points, dunder methods, test functions and CLI mains
are exempt to keep false positives near zero.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .analyzer import FileMetrics

_EXEMPT_PREFIXES = ("test_", "visit_", "do_", "handle_", "on_")
_EXEMPT_NAMES = {"main", "run", "setUp", "tearDown", "setUpClass", "tearDownClass"}


@dataclass
class DeadFunction:
    file: str
    qualname: str
    lineno: int


def _is_exempt(name: str) -> bool:
    """Names with framework/convention semantics are never flagged."""
    if name.startswith("__") and name.endswith("__"):
        return True
    if name.startswith(_EXEMPT_PREFIXES):
        return True
    return name in _EXEMPT_NAMES


def _collect_references(sources: dict[str, str]) -> set[str]:
    """Every identifier used as a value anywhere in the project."""
    used: set[str] = set()
    for source in sources.values():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                used.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # covers __all__ = ["name"] and getattr-style strings
                if node.value.isidentifier():
                    used.add(node.value)
    return used


def find_dead_functions(
    files: list[FileMetrics], sources: dict[str, str]
) -> list[DeadFunction]:
    """Functions defined in the project but never referenced by name."""
    used = _collect_references(sources)
    dead = []
    for fm in files:
        if fm.parse_error:
            continue
        for fn in fm.functions:
            if _is_exempt(fn.name):
                continue
            if fn.name not in used:
                dead.append(
                    DeadFunction(file=fm.path, qualname=fn.qualname, lineno=fn.lineno)
                )
    return dead
