"""Baseline snapshots and trend comparison for CI and long-running projects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .scoring import HealthReport


@dataclass
class Delta:
    """Change of one metric between the baseline and the current run."""

    metric: str
    before: float
    after: float

    @property
    def change(self) -> float:
        return round(self.after - self.before, 3)

    @property
    def improved(self) -> bool:
        lower_is_better = {"avg_complexity", "avg_cognitive", "cycles", "hotspots",
                           "dead_functions", "clone_groups"}
        if self.metric in lower_is_better:
            return self.after < self.before
        return self.after > self.before


def snapshot(health: HealthReport, extra: dict | None = None) -> dict:
    """Serializable summary of one analysis run."""
    data = {
        "score": health.score,
        "grade": health.grade,
        "files": health.total_files,
        "sloc": health.total_sloc,
        "functions": health.total_functions,
        "avg_complexity": health.avg_complexity,
        "docstring_coverage": health.docstring_coverage,
        "annotation_coverage": health.annotation_coverage,
        "avg_cognitive": health.avg_cognitive,
        "cycles": len(health.cycles),
        "hotspots": len(health.hotspots),
    }
    if extra:
        data.update(extra)
    return data


def save_baseline(path: Path, health: HealthReport, extra: dict | None = None) -> None:
    """Write the current run as the new baseline file."""
    path.write_text(json.dumps(snapshot(health, extra), indent=2), encoding="utf-8")


def compare(path: Path, health: HealthReport, extra: dict | None = None) -> list[Delta]:
    """Deltas between a stored baseline and the current run.

    Metrics present in only one side are skipped, so old baselines stay
    compatible when new metrics are added.
    """
    baseline = json.loads(path.read_text(encoding="utf-8"))
    current = snapshot(health, extra)
    deltas = []
    for metric, before in baseline.items():
        after = current.get(metric)
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            if before != after:
                deltas.append(Delta(metric=metric, before=before, after=after))
    return deltas
