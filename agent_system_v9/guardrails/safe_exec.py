"""Safe execution guard for eval/exec inputs."""
from __future__ import annotations

import ast
from typing import Any


class UnsafeCodeError(Exception):
    pass


_FORBIDDEN_NAMES = {"__import__", "eval", "exec", "open", "compile", "globals", "locals", "vars", "getattr", "setattr", "delattr"}


def validate_code(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise UnsafeCodeError(str(e))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            raise UnsafeCodeError("imports not allowed")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_NAMES:
                raise UnsafeCodeError(f"forbidden call: {node.func.id}")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise UnsafeCodeError(f"forbidden name: {node.id}")
    return True


def safe_eval(expr: str, context: dict[str, Any] | None = None) -> Any:
    validate_code(expr)
    return eval(expr, {"__builtins__": {}}, context or {})


def safe_exec(code: str, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    validate_code(code)
    ns = namespace or {}
    exec(code, {"__builtins__": {}}, ns)
    return ns
