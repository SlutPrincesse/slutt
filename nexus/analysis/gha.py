"""GitHub Actions workflow annotations.

When running inside Actions (GITHUB_ACTIONS=true) or with --gha, Codi
emits `::warning` commands so hotspots, dead code and import cycles show
up inline on the PR's changed files — no marketplace action needed.
"""

from __future__ import annotations

from .scoring import HealthReport


def emit_annotations(health: HealthReport, limit: int = 10) -> list[str]:
    """The `::warning` lines for this report (also printed by the CLI)."""
    lines = []
    for h in health.hotspots[:limit]:
        msg = "; ".join(h.reasons)
        if h.advice:
            msg += f" — try: {h.advice}"
        lines.append(
            f"::warning file={h.file},line={h.function.lineno},"
            f"title=Codi hotspot ({h.function.qualname})::{msg}"
        )
    for d in health.dead_functions[:limit]:
        lines.append(
            f"::warning file={d.file},line={d.lineno},"
            f"title=Codi dead code::{d.qualname} is never referenced"
        )
    for g in health.clone_groups[:limit]:
        first = g.sites[0]
        others = ", ".join(f"{s.file}:{s.lineno}" for s in g.sites[1:])
        lines.append(
            f"::warning file={first.file},line={first.lineno},"
            f"title=Codi duplicate::{first.qualname} duplicated at {others}"
        )
    for cycle in health.cycles:
        lines.append(f"::warning title=Codi import cycle::{' -> '.join(cycle)}")
    return lines
