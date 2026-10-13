"""
Pre-Commit Validator - Validates code before commit
"""
import ast
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    rule_id: str
    severity: ValidationSeverity
    message: str
    file_path: str = ""
    line_number: int = 0
    column: int = 0
    suggestion: str = ""
    auto_fixable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "suggestion": self.suggestion,
            "auto_fixable": self.auto_fixable,
        }


class PreCommitValidator:
    def __init__(self):
        self.rules: dict[str, Callable] = {}
        self._register_default_rules()

    def _register_default_rules(self):
        self.rules["no_todo"] = self._check_no_todo
        self.rules["no_pass"] = self._check_no_pass
        self.rules["no_not_implemented"] = self._check_no_not_implemented
        self.rules["no_debug_print"] = self._check_no_debug_print
        self.rules["no_hardcoded_secrets"] = self._check_no_hardcoded_secrets
        self.rules["function_docstring"] = self._check_function_docstring
        self.rules["type_hints"] = self._check_type_hints
        self.rules["line_length"] = self._check_line_length
        self.rules["trailing_whitespace"] = self._check_trailing_whitespace
        self.rules["unused_import"] = self._check_unused_import

    def register_rule(self, rule_id: str, checker: Callable):
        self.rules[rule_id] = checker

    def validate_file(self, file_path: str) -> list[ValidationResult]:
        results = []
        path = Path(file_path)

        if not path.exists():
            return [ValidationResult(
                rule_id="file_not_found",
                severity=ValidationSeverity.ERROR,
                message=f"File not found: {file_path}",
                file_path=file_path,
            )]

        if path.suffix == '.py':
            content = path.read_text(encoding='utf-8', errors='ignore')
            for rule_id, checker in self.rules.items():
                results.extend(checker(file_path, content))

        return results

    def validate_directory(self, dir_path: str, pattern: str = "*.py") -> dict[str, list[ValidationResult]]:
        results = {}
        for file_path in Path(dir_path).rglob(pattern):
            file_results = self.validate_file(str(file_path))
            if file_results:
                results[str(file_path)] = file_results
        return results

    def _check_no_todo(self, file_path: str, content: str) -> list[ValidationResult]:
        results = []
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if re.search(r'#\s*TODO|#\s*FIXME|#\s*HACK|#\s*XXX', line, re.IGNORECASE):
                results.append(ValidationResult(
                    rule_id="no_todo",
                    severity=ValidationSeverity.ERROR,
                    message="TODO/FIXME/HACK/XXX comments not allowed",
                    file_path=file_path,
                    line_number=i + 1,
                    suggestion="Resolve the issue or create a proper ticket",
                    auto_fixable=False,
                ))
        return results

    def _check_no_pass(self, file_path: str, content: str) -> list[ValidationResult]:
        results = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        results.append(ValidationResult(
                            rule_id="no_pass",
                            severity=ValidationSeverity.ERROR,
                            message=f"Empty {node.__class__.__name__.lower()} with only 'pass'",
                            file_path=file_path,
                            line_number=node.lineno,
                            suggestion="Implement the function/class or raise NotImplementedError with context",
                        ))
        except SyntaxError:
            pass
        return results

    def _check_no_not_implemented(self, file_path: str, content: str) -> list[ValidationResult]:
        results = []
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if re.search(r'raise\s+NotImplementedError', line):
                results.append(ValidationResult(
                    rule_id="no_not_implemented",
                    severity=ValidationSeverity.ERROR,
                    message="NotImplementedError not allowed in production code",
                    file_path=file_path,
                    line_number=i + 1,
                    suggestion="Implement the functionality or remove the stub",
                ))
        return results

    def _check_no_debug_print(self, file_path: str, content: str) -> list[ValidationResult]:
        results = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == 'print':
                        results.append(ValidationResult(
                            rule_id="no_debug_print",
                            severity=ValidationSeverity.WARNING,
                            message="Debug print statement found",
                            file_path=file_path,
                            line_number=node.lineno,
                            suggestion="Use logging module instead",
                            auto_fixable=True,
                        ))
        except SyntaxError:
            pass
        return results

    def _check_no_hardcoded_secrets(self, file_path: str, content: str) -> list[ValidationResult]:
        results = []
        patterns = [
            (r'api[_-]?key\s*=\s*["\'][^"\']+["\']', "API Key"),
            (r'secret[_-]?key\s*=\s*["\'][^"\']+["\']', "Secret Key"),
            (r'password\s*=\s*["\'][^"\']+["\']', "Password"),
            (r'token\s*=\s*["\'][^"\']+["\']', "Token"),
        ]
        lines = content.split('\n')
        for i, line in enumerate(lines):
            for pattern, desc in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    results.append(ValidationResult(
                        rule_id="no_hardcoded_secrets",
                        severity=ValidationSeverity.ERROR,
                        message=f"Hardcoded {desc} detected",
                        file_path=file_path,
                        line_number=i + 1,
                        suggestion="Use environment variables or secret management",
                    ))
        return results

    def _check_function_docstring(self, file_path: str, content: str) -> list[ValidationResult]:
        results = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not ast.get_docstring(node):
                        results.append(ValidationResult(
                            rule_id="function_docstring",
                            severity=ValidationSeverity.WARNING,
                            message=f"Function '{node.name}' missing docstring",
                            file_path=file_path,
                            line_number=node.lineno,
                            suggestion="Add a docstring describing the function",
                        ))
        except SyntaxError:
            pass
        return results

    def _check_type_hints(self, file_path: str, content: str) -> list[ValidationResult]:
        results = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.args.args and not all(arg.annotation for arg in node.args.args):
                        results.append(ValidationResult(
                            rule_id="type_hints",
                            severity=ValidationSeverity.INFO,
                            message=f"Function '{node.name}' missing type hints for some parameters",
                            file_path=file_path,
                            line_number=node.lineno,
                            suggestion="Add type hints for better code clarity",
                        ))
        except SyntaxError:
            pass
        return results

    def _check_line_length(self, file_path: str, content: str, max_length: int = 120) -> list[ValidationResult]:
        results = []
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if len(line) > max_length:
                results.append(ValidationResult(
                    rule_id="line_length",
                    severity=ValidationSeverity.WARNING,
                    message=f"Line exceeds {max_length} characters ({len(line)})",
                    file_path=file_path,
                    line_number=i + 1,
                    suggestion="Break long lines into multiple lines",
                    auto_fixable=True,
                ))
        return results

    def _check_trailing_whitespace(self, file_path: str, content: str) -> list[ValidationResult]:
        results = []
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.rstrip() != line:
                results.append(ValidationResult(
                    rule_id="trailing_whitespace",
                    severity=ValidationSeverity.INFO,
                    message="Trailing whitespace",
                    file_path=file_path,
                    line_number=i + 1,
                    suggestion="Remove trailing whitespace",
                    auto_fixable=True,
                ))
        return results

    def _check_unused_import(self, file_path: str, content: str) -> list[ValidationResult]:
        results = []
        try:
            tree = ast.parse(content)
            imports = {}
            used_names = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname or alias.name.split('.')[0]
                        imports[name] = (node.lineno, node.col_offset)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        name = alias.asname or alias.name
                        imports[name] = (node.lineno, node.col_offset)
                elif isinstance(node, ast.Name):
                    used_names.add(node.id)

            for name, (lineno, col) in imports.items():
                if name not in used_names and not name.startswith('_'):
                    results.append(ValidationResult(
                        rule_id="unused_import",
                        severity=ValidationSeverity.WARNING,
                        message=f"Unused import: {name}",
                        file_path=file_path,
                        line_number=lineno,
                        suggestion="Remove unused import",
                        auto_fixable=True,
                    ))
        except SyntaxError:
            pass
        return results


class CommitHookRunner:
    def __init__(self, validator: PreCommitValidator):
        self.validator = validator

    def run(self, files: list[str]) -> tuple[bool, list[ValidationResult]]:
        all_results = []
        for file_path in files:
            results = self.validator.validate_file(file_path)
            all_results.extend(results)

        errors = [r for r in all_results if r.severity == ValidationSeverity.ERROR]
        return len(errors) == 0, all_results
