"""
Absolute Path & JSON Normalizer - Maps path aliases to relative routes; strips invalid trailing JSON commas
"""
import json
import re
from pathlib import Path


class PathNormalizer:
    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self._alias_map: dict[str, str] = {}

    def add_alias(self, alias: str, path: str):
        self._alias_map[alias] = path

    def normalize(self, path: str) -> str:
        # Expand aliases
        for alias, real_path in self._alias_map.items():
            if path.startswith(alias):
                path = path.replace(alias, real_path, 1)
                break

        # Convert to Path
        p = Path(path)

        # Make relative to project root if possible
        try:
            if p.is_absolute():
                rel = p.relative_to(self.project_root)
                return str(rel)
        except ValueError:
            pass

        # Normalize separators
        return str(p).replace('\\', '/')

    def to_absolute(self, path: str) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = self.project_root / p
        return str(p.resolve())

    def get_relative(self, from_path: str, to_path: str) -> str:
        from_p = Path(from_path).parent if not Path(from_path).is_dir() else Path(from_path)
        to_p = Path(to_path)

        try:
            return str(to_p.relative_to(from_p))
        except ValueError:
            return str(to_p)

    def join(self, *paths: str) -> str:
        return str(Path(*paths)).replace('\\', '/')


class JSONNormalizer:
    def __init__(self):
        self._trailing_comma_pattern = re.compile(r',(\s*[}\]])')

    def normalize(self, json_str: str) -> str:
        # Remove trailing commas
        normalized = self._trailing_comma_pattern.sub(r'\1', json_str)

        # Ensure valid JSON
        try:
            parsed = json.loads(normalized)
            return json.dumps(parsed, separators=(',', ':'))
        except json.JSONDecodeError:
            return normalized

    def normalize_file(self, file_path: str, backup: bool = True) -> bool:
        try:
            with Path(file_path).open() as f:
                content = f.read()
        except Exception:
            return False

        normalized = self.normalize(content)

        if normalized != content:
            if backup:
                import shutil
                shutil.copy2(file_path, file_path + ".bak")
            with Path(file_path).open('w') as f:
                f.write(normalized)
            return True
        return False

    def validate(self, json_str: str) -> bool:
        try:
            json.loads(json_str)
            return True
        except json.JSONDecodeError:
            return False

    def fix_common_errors(self, json_str: str) -> str:
        # Fix single quotes
        fixed = re.sub(r"'([^']*)'", r'"\1"', json_str)

        # Fix trailing commas
        fixed = self._trailing_comma_pattern.sub(r'\1', fixed)

        # Fix unquoted keys
        fixed = re.compile(r'(\w+):').sub(r'"\1":', fixed)

        # Fix Python-style True/False/None
        fixed = re.sub(r'\bTrue\b', 'true', fixed)
        fixed = re.sub(r'\bFalse\b', 'false', fixed)
        fixed = re.sub(r'\bNone\b', 'null', fixed)

        return fixed


_path_normalizer: PathNormalizer | None = None
_json_normalizer: JSONNormalizer | None = None


def get_path_normalizer() -> PathNormalizer:
    global _path_normalizer
    if _path_normalizer is None:
        _path_normalizer = PathNormalizer()
    return _path_normalizer


def get_json_normalizer() -> JSONNormalizer:
    global _json_normalizer
    if _json_normalizer is None:
        _json_normalizer = JSONNormalizer()
    return _json_normalizer
