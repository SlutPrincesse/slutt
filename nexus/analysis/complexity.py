"""Cyclomatic complexity measurement via AST traversal."""

from __future__ import annotations

import ast

# Each occurrence of these node types opens one extra execution path.
_BRANCH_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
    ast.IfExp, ast.Assert, ast.match_case,
)
# Nested callables are measured separately; traversal stops at them.
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


class ComplexityVisitor(ast.NodeVisitor):
    """Counts decision points inside a single function body.

    Complexity starts at 1 (the single entry path) and each branching
    construct adds one path: if/elif, loops, except handlers, boolean
    operators, ternaries, comprehension conditions, assert, and
    match cases.
    """

    def __init__(self) -> None:
        self.complexity = 1

    def visit(self, node: ast.AST) -> None:
        """Tally the node's decision points, skipping nested scopes."""
        if isinstance(node, _NESTED_SCOPES):
            return
        if isinstance(node, _BRANCH_NODES):
            self.complexity += 1
        elif isinstance(node, ast.BoolOp):
            # `a and b and c` is two extra decision points
            self.complexity += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            self.complexity += 1 + len(node.ifs)
        self.generic_visit(node)


def function_complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Cyclomatic complexity of one function, excluding nested defs."""
    visitor = ComplexityVisitor()
    for child in ast.iter_child_nodes(node):
        visitor.visit(child)
    return visitor.complexity


def complexity_grade(score: int) -> str:
    """Letter grade for a complexity score, radon-style bands."""
    if score <= 5:
        return "A"
    if score <= 10:
        return "B"
    if score <= 20:
        return "C"
    if score <= 30:
        return "D"
    return "F"
