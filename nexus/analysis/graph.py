"""Internal import dependency graph with cycle detection."""

from __future__ import annotations

from dataclasses import dataclass, field

from .analyzer import FileMetrics


def _module_name(path: str) -> str:
    """Convert a relative file path to a dotted module name."""
    name = path[:-3] if path.endswith(".py") else path
    name = name.replace("/", ".").replace("\\", ".")
    if name.endswith(".__init__"):
        name = name[: -len(".__init__")]
    return name


@dataclass
class DependencyGraph:
    """Directed graph of imports between modules inside the project."""

    edges: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def build(cls, files: list[FileMetrics]) -> "DependencyGraph":
        """Construct the graph from analyzed files' import lists."""
        modules = {_module_name(f.path): f for f in files}
        graph = cls(edges={m: set() for m in modules})
        for module, metrics in modules.items():
            for imp in metrics.imports:
                # Match the import (or any parent package) to a project module
                target = cls._resolve(imp, modules, importer=module)
                if target and target != module:
                    graph.edges[module].add(target)
        return graph

    @staticmethod
    def _resolve(imp: str, modules: dict, importer: str) -> str | None:
        """Map an imported name to a project module, if it is one."""
        candidates = [imp]
        # from package.mod import name -> package.mod
        parts = imp.split(".")
        for i in range(len(parts), 0, -1):
            candidates.append(".".join(parts[:i]))
        # relative-style: importer's package + imp
        pkg = importer.rsplit(".", 1)[0] if "." in importer else ""
        if pkg:
            candidates.append(f"{pkg}.{imp}")
        for cand in candidates:
            if cand in modules:
                return cand
        return None

    def fan_in(self) -> dict[str, int]:
        """How many project modules import each module."""
        counts = {m: 0 for m in self.edges}
        for targets in self.edges.values():
            for t in targets:
                counts[t] = counts.get(t, 0) + 1
        return counts

    def fan_out(self) -> dict[str, int]:
        """How many project modules each module imports."""
        return {m: len(t) for m, t in self.edges.items()}

    def find_cycles(self) -> list[list[str]]:
        """All elementary import cycles (DFS with path tracking)."""
        cycles: list[list[str]] = []
        seen_cycles: set[frozenset[str]] = set()

        def dfs(node: str, path: list[str], on_path: set[str]) -> None:
            """Depth-first search recording any edge back into the path."""
            for nxt in sorted(self.edges.get(node, ())):
                if nxt in on_path:
                    cycle = path[path.index(nxt):] + [nxt]
                    key = frozenset(cycle)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        cycles.append(cycle)
                elif len(path) < 50:
                    dfs(nxt, path + [nxt], on_path | {nxt})

        for start in sorted(self.edges):
            dfs(start, [start], {start})
        return cycles
