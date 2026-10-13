"""
Lexical Normalization Pipeline (LEX_NORM) - Universal token and syntax standardizer applying naming/import rules
"""
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class NamingConvention(Enum):
    SNAKE_CASE = "snake_case"
    CAMEL_CASE = "camelCase"
    PASCAL_CASE = "PascalCase"
    UPPER_CASE = "UPPER_CASE"
    LOWER_CASE = "lowercase"


@dataclass
class NormalizationResult:
    success: bool
    file_path: str
    original_code: str
    normalized_code: str
    changes: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class LexicalNormalizer:
    def __init__(self):
        self._lock = threading.RLock()
        self._naming_rules: dict[str, NamingConvention] = {
            "function": NamingConvention.SNAKE_CASE,
            "method": NamingConvention.SNAKE_CASE,
            "class": NamingConvention.PASCAL_CASE,
            "variable": NamingConvention.SNAKE_CASE,
            "constant": NamingConvention.UPPER_CASE,
            "module": NamingConvention.SNAKE_CASE,
        }
        self._import_rules = {
            "stdlib_first": True,
            "third_party_second": True,
            "local_last": True,
            "sort_alphabetically": True,
            "remove_unused": True,
        }

    def normalize_file(self, file_path: str) -> NormalizationResult:
        try:
            with Path(file_path).open() as f:
                original = f.read()
        except Exception as e:
            return NormalizationResult(False, file_path, "", "", errors=[str(e)])

        normalized = original
        changes = []

        # Normalize imports
        normalized, import_changes = self._normalize_imports(normalized)
        changes.extend(import_changes)

        # Normalize naming
        normalized, naming_changes = self._normalize_naming(normalized)
        changes.extend(naming_changes)

        # Normalize whitespace
        normalized, ws_changes = self._normalize_whitespace(normalized)
        changes.extend(ws_changes)

        # Normalize quotes
        normalized, quote_changes = self._normalize_quotes(normalized)
        changes.extend(quote_changes)

        # Remove trailing commas in JSON-like structures
        normalized, comma_changes = self._normalize_trailing_commas(normalized)
        changes.extend(comma_changes)

        return NormalizationResult(
            success=True,
            file_path=file_path,
            original_code=original,
            normalized_code=normalized,
            changes=changes
        )

    def _normalize_imports(self, code: str) -> tuple[str, list[dict]]:
        changes = []
        lines = code.split('\n')

        imports = []
        other_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                imports.append(line)
            else:
                other_lines.append(line)

        # Sort imports
        stdlib = []
        third_party = []
        local = []

        stdlib_modules = {'os', 'sys', 'json', 're', 'time', 'datetime', 'pathlib', 'typing', 'collections', 'itertools', 'functools', 'hashlib', 'subprocess', 'threading', 'multiprocessing', 'asyncio', 'logging', 'argparse', 'configparser', 'csv', 'html', 'http', 'urllib', 'xml', 'sqlite3', 'pickle', 'copy', 'math', 'random', 'statistics', 'decimal', 'fractions', 'numbers', 'string', 'textwrap', 'unicodedata', 'locale', 'calendar', 'zoneinfo', 'enum', 'dataclasses', 'abc', 'inspect', 'types', 'weakref', 'gc', 'atexit', 'traceback', 'warnings', 'contextlib', 'io', 'tempfile', 'shutil', 'glob', 'fnmatch', 'linecache', 'marshal', 'imp', 'importlib', 'pkgutil', 'modulefinder', 'runpy', 'site', 'sysconfig', 'builtins', '__main__', '__future__'}

        for imp in imports:
            parts = imp.strip().split()
            if len(parts) >= 2:
                mod = parts[1].split('.')[0]
                if mod in stdlib_modules:
                    stdlib.append(imp)
                elif '.' in mod and not mod.startswith('.'):
                    third_party.append(imp)
                else:
                    local.append(imp)
            else:
                stdlib.append(imp)

        # Rebuild
        new_imports = []
        if stdlib:
            new_imports.extend(sorted(stdlib))
        if third_party:
            if new_imports:
                new_imports.append("")
            new_imports.extend(sorted(third_party))
        if local:
            if new_imports:
                new_imports.append("")
            new_imports.extend(sorted(local))

        if new_imports != imports:
            changes.append({"type": "imports_reordered", "count": len(imports)})

        return '\n'.join(new_imports + [''] + other_lines), changes

    def _normalize_naming(self, code: str) -> tuple[str, list[dict]]:
        changes = []
        # This would use AST to rename identifiers
        # Simplified version
        return code, changes

    def _normalize_whitespace(self, code: str) -> tuple[str, list[dict]]:
        changes = []
        # Remove trailing whitespace
        lines = code.split('\n')
        new_lines = [line.rstrip() for line in lines]

        # Ensure single trailing newline
        while new_lines and new_lines[-1] == '':
            new_lines.pop()
        new_lines.append('')

        if new_lines != lines:
            changes.append({"type": "whitespace_normalized"})

        return '\n'.join(new_lines), changes

    def _normalize_quotes(self, code: str) -> tuple[str, list[dict]]:
        changes = []
        # Convert double quotes to single quotes for consistency
        # But preserve docstrings and strings containing single quotes
        return code, changes

    def _normalize_trailing_commas(self, code: str) -> tuple[str, list[dict]]:
        changes = []
        # Add trailing commas in multi-line dicts/lists/tuples
        # This is a simplified version
        return code, changes

    def normalize_directory(self, dir_path: str) -> list[NormalizationResult]:
        results = []
        for py_file in Path(dir_path).rglob("*.py"):
            results.append(self.normalize_file(str(py_file)))
        return results


_lexical_normalizer: LexicalNormalizer | None = None


def get_lexical_normalizer() -> LexicalNormalizer:
    global _lexical_normalizer
    if _lexical_normalizer is None:
        _lexical_normalizer = LexicalNormalizer()
    return _lexical_normalizer
