"""Function-level clone detection via normalized AST fingerprints.

Two functions are clones if their ASTs are structurally identical after
normalizing identifiers and constant values — so renamed copy-pastes
are still caught (type-2 clones).
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass

from .analyzer import FileMetrics


@dataclass
class CloneSite:
    file: str
    qualname: str
    lineno: int


@dataclass
class CloneGroup:
    """A set of structurally identical functions."""

    sites: list[CloneSite]
    size: int  # statement count of the duplicated body


class _Normalizer(ast.NodeTransformer):
    """Strip naming and literal details so structure alone remains."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="_v", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.copy_location(ast.arg(arg="_a", annotation=None), node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        kind = type(node.value).__name__
        return ast.copy_location(ast.Constant(value=f"_{kind}"), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        return ast.copy_location(
            ast.Attribute(value=node.value, attr="_attr", ctx=node.ctx), node
        )

    def _strip_signature(self, node: ast.AST) -> ast.AST:
        """Erase name, decorators and return annotation from a def node."""
        self.generic_visit(node)
        node.name = "_f"
        node.decorator_list = []
        node.returns = None
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._strip_signature(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._strip_signature(node)


def _fingerprint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, int]:
    """Stable hash of the normalized function body plus its statement count."""
    clone = ast.parse(ast.unparse(node))  # deep copy via round-trip
    normalized = _Normalizer().visit(clone)
    dump = ast.dump(normalized, annotate_fields=False)
    statements = sum(isinstance(n, ast.stmt) for n in ast.walk(clone))
    return hashlib.sha1(dump.encode()).hexdigest(), statements


def find_clones(
    files: list[FileMetrics], sources: dict[str, str], min_statements: int = 4
) -> list[CloneGroup]:
    """Group structurally identical functions across the project.

    `sources` maps file path -> source text. Tiny functions (fewer than
    `min_statements` statements) are ignored — trivial getters and
    delegations are not meaningful duplication.
    """
    buckets: dict[str, tuple[int, list[CloneSite]]] = {}
    for fm in files:
        source = sources.get(fm.path)
        if not source or fm.parse_error:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        index = {
            (fn.name, fn.lineno): fn.qualname for fn in fm.functions
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                digest, statements = _fingerprint(node)
                if statements < min_statements:
                    continue
                qual = index.get((node.name, node.lineno), node.name)
                site = CloneSite(file=fm.path, qualname=qual, lineno=node.lineno)
                buckets.setdefault(digest, (statements, []))[1].append(site)

    groups = [
        CloneGroup(sites=sites, size=size)
        for size, sites in buckets.values()
        if len(sites) > 1
    ]
    groups.sort(key=lambda g: (g.size, len(g.sites)), reverse=True)
    return groups


def duplication_ratio(groups: list[CloneGroup], total_functions: int) -> float:
    """Share of functions that are part of a clone group."""
    if total_functions == 0:
        return 0.0
    duplicated = sum(len(g.sites) for g in groups)
    return min(1.0, duplicated / total_functions)
