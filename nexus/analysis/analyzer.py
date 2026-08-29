"""Per-file AST analysis: functions, classes, metrics, docstring coverage."""

from __future__ import annotations

import ast
import math
import os
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from .cognitive import cognitive_complexity, halstead_volume, maintainability_index
from .complexity import complexity_grade, function_complexity

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env",
    "node_modules", ".tox", ".mypy_cache", ".pytest_cache", "build",
    "dist", ".eggs", "site-packages", ".dart_tool", ".gradle", ".idea",
    ".cxx", ".ruff_cache", "target", ".next", ".nuxt",
}


@dataclass
class FunctionMetrics:
    name: str
    qualname: str
    lineno: int
    end_lineno: int
    complexity: int
    grade: str
    length: int
    args: int
    has_docstring: bool
    is_async: bool
    cognitive: int = 0
    is_annotated: bool = False


@dataclass
class FileMetrics:
    path: str
    loc: int = 0
    sloc: int = 0
    comment_lines: int = 0
    functions: list[FunctionMetrics] = field(default_factory=list)
    classes: int = 0
    imports: list[str] = field(default_factory=list)
    parse_error: str | None = None
    halstead: float = 0.0

    @property
    def avg_complexity(self) -> float:
        """Mean cyclomatic complexity across the file's functions."""
        if not self.functions:
            return 0.0
        return statistics.fmean(f.complexity for f in self.functions)

    @property
    def max_complexity(self) -> int:
        """Highest cyclomatic complexity in the file."""
        return max((f.complexity for f in self.functions), default=0)

    def _share(self, predicate) -> float:
        """Share of this file's functions matching predicate (1.0 when none)."""
        if not self.functions:
            return 1.0
        return sum(1 for f in self.functions if predicate(f)) / len(self.functions)

    @property
    def docstring_coverage(self) -> float:
        """Share of functions in the file that carry a docstring."""
        return self._share(lambda f: f.has_docstring)

    @property
    def annotation_coverage(self) -> float:
        """Share of functions with complete type hints (args + return)."""
        return self._share(lambda f: f.is_annotated)

    @property
    def maintainability_index(self) -> float:
        """Classic maintainability index (0-100, higher is better).

        Uses real Halstead volume when available, falling back to a
        SLOC-based proxy for files analyzed without it.
        """
        volume = self.halstead or self.sloc * math.log2(max(self.sloc, 2))
        return maintainability_index(volume, self.avg_complexity, self.sloc)


def discover_python_files(root: Path) -> list[Path]:
    """All .py files under root, skipping vendored/cache directories."""
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in place so huge build/vendor trees
        # (node_modules, .gradle, .dart_tool, ...) are never traversed.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".py"):
                files.append(Path(dirpath) / name)
    return sorted(files)


def _count_lines(source: str) -> tuple[int, int, int]:
    """Return (loc, sloc, comment_lines) for a source string."""
    loc = sloc = comments = 0
    for line in source.splitlines():
        loc += 1
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            comments += 1
        else:
            sloc += 1
    return loc, sloc, comments


def _walk_functions(
    tree: ast.AST, parent_qual: str = ""
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]]:
    """Yield (node, qualified name) for every function, including nested."""
    found: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = f"{parent_qual}.{node.name}" if parent_qual else node.name
            found.append((node, qual))
            found.extend(_walk_functions(node, qual))
        elif isinstance(node, ast.ClassDef):
            qual = f"{parent_qual}.{node.name}" if parent_qual else node.name
            found.extend(_walk_functions(node, qual))
        else:
            found.extend(_walk_functions(node, parent_qual))
    return found


def _extract_imports(tree: ast.AST) -> list[str]:
    """Absolute module names imported anywhere in the tree."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.append(node.module)
    return imports


def _is_fully_annotated(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when every parameter (except self/cls) and the return are typed."""
    args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
    params = [a for a in args if a.arg not in ("self", "cls")]
    for extra in (node.args.vararg, node.args.kwarg):
        if extra is not None:
            params.append(extra)
    if any(a.annotation is None for a in params):
        return False
    return node.returns is not None


def analyze_file(path: Path, display_path: str | None = None) -> FileMetrics:
    """Full metrics for a single Python file."""
    display = display_path or str(path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError as exc:
        metrics = FileMetrics(path=display, parse_error=str(exc))
        try:
            loc, sloc, comments = _count_lines(source)
            metrics.loc, metrics.sloc, metrics.comment_lines = loc, sloc, comments
        except Exception:
            pass
        return metrics

    loc, sloc, comments = _count_lines(source)
    metrics = FileMetrics(
        path=display, loc=loc, sloc=sloc, comment_lines=comments,
        imports=_extract_imports(tree),
    )
    metrics.classes = sum(
        isinstance(n, ast.ClassDef) for n in ast.walk(tree)
    )
    metrics.halstead = halstead_volume(tree)

    for node, qual in _walk_functions(tree):
        score = function_complexity(node)
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        metrics.functions.append(
            FunctionMetrics(
                name=node.name,
                qualname=qual,
                lineno=node.lineno,
                end_lineno=end,
                complexity=score,
                grade=complexity_grade(score),
                length=end - node.lineno + 1,
                args=len(node.args.args)
                + len(node.args.posonlyargs)
                + len(node.args.kwonlyargs),
                has_docstring=ast.get_docstring(node) is not None,
                is_async=isinstance(node, ast.AsyncFunctionDef),
                cognitive=cognitive_complexity(node),
                is_annotated=_is_fully_annotated(node),
            )
        )
    return metrics


def read_sources(root: Path, files: list[FileMetrics]) -> dict[str, str]:
    """Map each analyzed file's display path back to its source text."""
    base = root if root.is_dir() else root.parent
    sources = {}
    for fm in files:
        try:
            sources[fm.path] = (base / fm.path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            pass
    return sources


def analyze_project(root: Path) -> list[FileMetrics]:
    """Analyze every Python file under root, paths relative to root."""
    results = []
    base = root if root.is_dir() else root.parent
    for file in discover_python_files(root):
        try:
            rel = str(file.relative_to(base))
        except ValueError:
            rel = str(file)
        results.append(analyze_file(file, display_path=rel.replace("\\", "/")))
    return results
