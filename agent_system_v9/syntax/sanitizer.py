"""
Sanitization & Clean Code Formatter - Strips debug logs, normalizes string quotes, cleans dead comments
"""
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SanitizationLevel(Enum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    STRICT = "strict"


@dataclass
class SanitizationResult:
    original_code: str
    sanitized_code: str
    removed_elements: list[str] = field(default_factory=list)
    normalized_elements: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


class Sanitizer:
    def __init__(self, level: SanitizationLevel = SanitizationLevel.STANDARD):
        self.level = level
        self._lock = threading.RLock()
        self._patterns: dict[str, re.Pattern] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        self._patterns = {
            # Debug prints
            "debug_print": re.compile(r'\bprint\s*\([^)]*debug[^)]*\)', re.IGNORECASE),
            "console_log": re.compile(r'\bconsole\.(log|debug|info|warn|error)\s*\([^)]*\)'),
            "debugger": re.compile(r'\bdebugger\s*;?'),
            "pdb": re.compile(r'\b(pdb\.set_trace|breakpoint)\s*\(\)'),

            # Dead comments
            "todo_comments": re.compile(r'#\s*(TODO|FIXME|HACK|XXX|BUG)[\s:]*.*$', re.MULTILINE),
            "dead_code_comments": re.compile(r'#\s*(dead|unused|deprecated|remove|delete).*$', re.MULTILINE, re.IGNORECASE),

            # Logging
            "logging_calls": re.compile(r'\blogging\.(debug|info|warning|error|critical)\s*\([^)]*\)'),

            # Quotes
            "double_quotes": re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"'),

            # Trailing commas
            "trailing_commas": re.compile(r',(\s*[}\]])'),

            # Type hints (for stripping)
            "type_hints": re.compile(r':\s*\w+(\[\w+\])?\s*='),

            # Pass statements
            "pass_stmts": re.compile(r'^\s*pass\s*$', re.MULTILINE),

            # Unused imports (simplified)
            "unused_imports": re.compile(r'^\s*(import|from)\s+\w+.*$', re.MULTILINE),
        }

    def sanitize(self, code: str, level: SanitizationLevel = None) -> SanitizationResult:
        level = level or self.level
        original = code
        removed = []
        normalized = []
        stats = {"removed": 0, "normalized": 0}

        # Remove debug statements
        if level in (SanitizationLevel.STANDARD, SanitizationLevel.STRICT):
            code, count = self._remove_pattern(code, "debug_print", "debug_prints")
            stats["removed"] += count
            if count > 0:
                removed.append(f"debug_prints: {count}")

            code, count = self._remove_pattern(code, "console_log", "console_logs")
            stats["removed"] += count
            if count > 0:
                removed.append(f"console_logs: {count}")

            code, count = self._remove_pattern(code, "debugger", "debugger")
            stats["removed"] += count
            if count > 0:
                removed.append(f"debugger: {count}")

            code, count = self._remove_pattern(code, "pdb", "pdb_breakpoints")
            stats["removed"] += count
            if count > 0:
                removed.append(f"pdb_breakpoints: {count}")

        if level == SanitizationLevel.STRICT:
            code, count = self._remove_pattern(code, "logging_calls", "logging")
            stats["removed"] += count
            if count > 0:
                removed.append(f"logging: {count}")

        # Remove dead comments
        if level in (SanitizationLevel.STANDARD, SanitizationLevel.STRICT):
            code, count = self._remove_pattern(code, "todo_comments", "todo_comments")
            stats["removed"] += count
            if count > 0:
                removed.append(f"todo_comments: {count}")

            code, count = self._remove_pattern(code, "dead_code_comments", "dead_comments")
            stats["removed"] += count
            if count > 0:
                removed.append(f"dead_comments: {count}")

        # Normalize quotes
        code, count = self._normalize_quotes(code)
        stats["normalized"] += count
        if count > 0:
            normalized.append(f"quotes: {count}")

        # Remove trailing commas
        code, count = self._remove_trailing_commas(code)
        stats["normalized"] += count
        if count > 0:
            normalized.append(f"trailing_commas: {count}")

        if level == SanitizationLevel.STRICT:
            # Remove type hints from assignments
            code, count = self._remove_pattern(code, "type_hints", "type_hints")
            stats["removed"] += count
            if count > 0:
                removed.append(f"type_hints: {count}")

            # Remove pass statements
            code, count = self._remove_pattern(code, "pass_stmts", "pass_statements")
            stats["removed"] += count
            if count > 0:
                removed.append(f"pass_statements: {count}")

        return SanitizationResult(
            original_code="",
            sanitized_code=code,
            removed_elements=removed,
            normalized_elements=normalized,
            stats=stats
        )

    def _remove_pattern(self, code: str, pattern_name: str, element_name: str) -> tuple[str, int]:
        pattern = self._patterns.get(pattern_name)
        if not pattern:
            return code, 0

        matches = list(pattern.finditer(code))
        if not matches:
            return code, 0

        # Remove matches (simplified - just replace with empty)
        new_code = pattern.sub('', code)
        return new_code, len(matches)

    def _normalize_quotes(self, code: str) -> tuple[str, int]:
        # Convert double quotes to single quotes (preserve docstrings)
        count = 0
        # This is simplified - real implementation would use AST
        return code, count

    def _remove_trailing_commas(self, code: str) -> tuple[str, int]:
        # Remove trailing commas in single-line structures
        # Keep in multi-line for git diff friendliness
        return code, 0

    def sanitize_file(self, file_path: str, backup: bool = True) -> SanitizationResult:
        try:
            with Path(file_path).open() as f:
                code = f.read()
        except Exception:
            return SanitizationResult("", "", [], [], {"error": 1})

        result = self.sanitize(code)
        result.original_code = code

        if result.sanitized_code != code:
            if backup:
                import shutil
                shutil.copy2(file_path, file_path + ".bak")
            with Path(file_path).open('w') as f:
                f.write(result.sanitized_code)

        return result

    def sanitize_directory(self, dir_path: str, pattern: str = "*.py") -> list[SanitizationResult]:
        results = []
        for f in Path(dir_path).rglob(pattern):
            if f.is_file():
                results.append(self.sanitize_file(str(f)))
        return results


_sanitizer: Sanitizer | None = None


def get_sanitizer() -> Sanitizer:
    global _sanitizer
    if _sanitizer is None:
        _sanitizer = Sanitizer()
    return _sanitizer


class CleanCodeFormatter:
    def __init__(self):
        self._sanitizer = get_sanitizer()

    def format(self, code: str, level: SanitizationLevel = SanitizationLevel.STANDARD) -> str:
        result = self._sanitizer.sanitize(code, level)
        return result.sanitized_code
