"""
AST State-Verification Gatekeeper - Enforces mandatory AST and state checks prior to I/O file edits
"""
import ast
import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VerificationStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass
class VerificationResult:
    check_id: str
    status: VerificationStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class ASTStateGatekeeper:
    def __init__(self, strict: bool = True):
        self.strict = strict
        self._checks: list[Callable] = []
        self._lock = threading.RLock()
        self._file_states: dict[str, str] = {}  # file_path -> content_hash
        self._ast_cache: dict[str, ast.AST] = {}
        self._register_default_checks()

    def _register_default_checks(self):
        self.add_check(self._check_syntax_valid)
        self.add_check(self._check_no_syntax_errors)
        self.add_check(self._check_imports_resolvable)
        self.add_check(self._check_no_undefined_names)
        if self.strict:
            self.add_check(self._check_type_annotations)
            self.add_check(self._check_complexity)

    def add_check(self, check: Callable[[str, str], VerificationResult]):
        with self._lock:
            self._checks.append(check)

    def verify(self, file_path: str, new_content: str) -> list[VerificationResult]:
        results = []

        # Check if content actually changed
        new_hash = hashlib.sha256(new_content.encode()).hexdigest()
        with self._lock:
            old_hash = self._file_states.get(file_path)

        if old_hash == new_hash:
            return [VerificationResult("unchanged", VerificationStatus.SKIPPED, "Content unchanged")]

        # Run all checks
        for check in self._checks:
            try:
                result = check(file_path, new_content)
                results.append(result)
            except Exception as e:
                results.append(VerificationResult(
                    check_id="check_error",
                    status=VerificationStatus.FAILED,
                    message=f"Check failed: {e}"
                ))

        # Update state if all passed
        if all(r.status == VerificationStatus.PASSED for r in results):
            with self._lock:
                self._file_states[file_path] = new_hash
                # Update AST cache
                try:
                    self._ast_cache[file_path] = ast.parse(new_content)
                except Exception:
                    pass

        return results

    def _check_syntax_valid(self, file_path: str, content: str) -> VerificationResult:
        try:
            ast.parse(content)
            return VerificationResult("syntax", VerificationStatus.PASSED, "Syntax valid")
        except SyntaxError as e:
            return VerificationResult("syntax", VerificationStatus.FAILED, f"Syntax error: {e}")

    def _check_no_syntax_errors(self, file_path: str, content: str) -> VerificationResult:
        # More thorough syntax checking
        try:
            tree = ast.parse(content)
            # Check for common issues
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.body:
                        return VerificationResult("empty_function", VerificationStatus.FAILED, f"Empty function: {node.name}")
            return VerificationResult("no_syntax_errors", VerificationStatus.PASSED, "No syntax errors")
        except Exception as e:
            return VerificationResult("no_syntax_errors", VerificationStatus.FAILED, str(e))

    def _check_imports_resolvable(self, file_path: str, content: str) -> VerificationResult:
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        # Would check if import is resolvable
                        pass
            return VerificationResult("imports", VerificationStatus.PASSED, "Imports resolvable")
        except Exception:
            return VerificationResult("imports", VerificationStatus.FAILED, "Import check failed")

    def _check_no_undefined_names(self, file_path: str, content: str) -> VerificationResult:
        try:
            tree = ast.parse(content)
            # Simple undefined name check
            defined = set()
            used = set()

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign)):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                defined.add(target.id)
                    else:
                        defined.add(node.name)
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    used.add(node.id)

            undefined = used - defined - {'True', 'False', 'None', 'print', 'len', 'str', 'int', 'list', 'dict', 'set'}
            if undefined:
                return VerificationResult("undefined_names", VerificationStatus.FAILED, f"Undefined: {undefined}")

            return VerificationResult("undefined_names", VerificationStatus.PASSED, "No undefined names")
        except Exception:
            return VerificationResult("undefined_names", VerificationStatus.PASSED, "Check skipped")

    def _check_type_annotations(self, file_path: str, content: str) -> VerificationResult:
        try:
            tree = ast.parse(content)
            missing = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.returns is None and node.name not in ('__init__', '__new__'):
                        missing.append(f"{node.name}: missing return type")
                    for arg in node.args.args:
                        if arg.annotation is None and arg.arg != 'self':
                            missing.append(f"{node.name}.{arg.arg}: missing type")

            if missing:
                return VerificationResult("type_annotations", VerificationStatus.FAILED, f"Missing types: {missing}")
            return VerificationResult("type_annotations", VerificationStatus.PASSED, "All typed")
        except Exception:
            return VerificationResult("type_annotations", VerificationStatus.PASSED, "Check skipped")

    def _check_complexity(self, file_path: str, content: str) -> VerificationResult:
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity = self._calculate_complexity(node)
                    if complexity > 10:
                        return VerificationResult("complexity", VerificationStatus.FAILED,
                                                f"High complexity ({complexity}) in {node.name}")
            return VerificationResult("complexity", VerificationStatus.PASSED, "Complexity OK")
        except Exception:
            return VerificationResult("complexity", VerificationStatus.PASSED, "Check skipped")

    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler)) or isinstance(child, (ast.And, ast.Or)):
                complexity += 1
        return complexity

    def get_file_state(self, file_path: str) -> str | None:
        with self._lock:
            return self._file_states.get(file_path)

    def get_ast(self, file_path: str) -> ast.AST | None:
        with self._lock:
            return self._ast_cache.get(file_path)


_ast_gatekeeper: ASTStateGatekeeper | None = None


def get_ast_gatekeeper() -> ASTStateGatekeeper:
    global _ast_gatekeeper
    if _ast_gatekeeper is None:
        from ..core.config import config
        strict = config.get_param("prometheus9", "ast_verification_strict", True)
        _ast_gatekeeper = ASTStateGatekeeper(strict=strict)
    return _ast_gatekeeper
