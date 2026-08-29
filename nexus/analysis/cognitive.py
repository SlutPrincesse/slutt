"""Cognitive complexity (Sonar-style) and Halstead metrics.

Cyclomatic complexity counts paths; cognitive complexity measures how hard
code is for a human to follow: each break in linear flow costs 1, and each
level of nesting makes further breaks cost more. Per the Sonar spec, an
`elif`/`else` costs a flat +1 with no nesting increment — the reader stays
in the same mental frame. Halstead volume feeds the classic
maintainability-index formula.
"""

from __future__ import annotations

import ast
import math

_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_NESTING_NODES = (ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                  ast.With, ast.AsyncWith)


def cognitive_complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Sonar-style cognitive complexity of one function."""
    return _walk(node, 0)


def _walk(n: ast.AST, depth: int) -> int:
    """Total cognitive cost of n's children at the given nesting depth."""
    total = 0
    for child in ast.iter_child_nodes(n):
        if isinstance(child, _NESTED_SCOPES):
            continue
        if isinstance(child, ast.If):
            total += _if_chain(child, depth, is_elif=False)
        elif isinstance(child, _NESTING_NODES):
            total += 1 + depth
            if isinstance(child, (ast.For, ast.AsyncFor, ast.While)) and child.orelse:
                total += 1
            total += _walk(child, depth + 1)
        elif isinstance(child, ast.IfExp):
            total += 1 + depth + _walk(child, depth + 1)
        elif isinstance(child, ast.BoolOp):
            total += 1 + _walk(child, depth)
        else:
            total += _walk(child, depth)
    return total


def _if_chain(n: ast.If, depth: int, is_elif: bool) -> int:
    """Cost of an if/elif/else chain: nesting charged once, +1 per branch."""
    total = 1 if is_elif else 1 + depth
    total += _walk(n.test, depth)
    for stmt in n.body:
        total += _walk_stmt(stmt, depth + 1)
    if len(n.orelse) == 1 and isinstance(n.orelse[0], ast.If):
        total += _if_chain(n.orelse[0], depth, is_elif=True)
    elif n.orelse:
        total += 1
        for stmt in n.orelse:
            total += _walk_stmt(stmt, depth + 1)
    return total


def _walk_stmt(stmt: ast.stmt, depth: int) -> int:
    """Cost of one statement, dispatching ifs to the chain handler."""
    if isinstance(stmt, ast.If):
        return _if_chain(stmt, depth, is_elif=False)
    if isinstance(stmt, _NESTED_SCOPES):
        return 0
    if isinstance(stmt, _NESTING_NODES):
        extra = 1 if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)) and stmt.orelse else 0
        return 1 + depth + extra + _walk(stmt, depth + 1)
    return _walk(stmt, depth)


_OP_TOKENS = {ast.Assign: "=", ast.AugAssign: "=", ast.AnnAssign: "=",
              ast.Call: "()", ast.Subscript: "[]"}


def halstead_volume(tree: ast.AST) -> float:
    """Halstead volume: (operators + operands) x log2(vocabulary)."""
    operators: list[str] = []
    operands: list[str] = []
    for node in ast.walk(tree):
        token = _OP_TOKENS.get(type(node))
        if token is not None:
            operators.append(token)
        elif isinstance(node, (ast.BinOp, ast.UnaryOp, ast.BoolOp)):
            operators.append(type(node.op).__name__)
        elif isinstance(node, ast.Compare):
            operators.extend(type(op).__name__ for op in node.ops)
        elif isinstance(node, ast.Attribute):
            operators.append(".")
            operands.append(node.attr)
        elif isinstance(node, ast.Name):
            operands.append(node.id)
        elif isinstance(node, ast.Constant):
            operands.append(repr(node.value))
    n1, n2 = len(set(operators)), len(set(operands))
    total = len(operators) + len(operands)
    vocabulary = n1 + n2
    if vocabulary < 2 or total == 0:
        return 0.0
    return total * math.log2(vocabulary)


def maintainability_index(volume: float, avg_complexity: float, sloc: int) -> float:
    """Classic MI normalised to 0-100 (higher is better)."""
    if sloc == 0:
        return 100.0
    mi = (
        171
        - 5.2 * math.log(max(volume, 1.0))
        - 0.23 * avg_complexity
        - 16.2 * math.log(max(sloc, 1))
    )
    return max(0.0, min(100.0, mi * 100 / 171))
