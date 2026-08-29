"""Run history: append-only trend log powering sparklines and charts."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from .baseline import snapshot
from .scoring import HealthReport

_SPARK_CHARS = "▁▂▃▄▅▆▇█"
MAX_ENTRIES = 200


def append_history(path: Path, health: HealthReport, extra: dict | None = None) -> list[dict]:
    """Append this run's snapshot to the history file and return all entries."""
    entries = load_history(path)
    entry = snapshot(health, extra)
    entry["date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entries.append(entry)
    entries = entries[-MAX_ENTRIES:]
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return entries


def load_history(path: Path) -> list[dict]:
    """All recorded runs, oldest first; [] when the file is missing/corrupt."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def sparkline(values: list[float], lo: float = 0.0, hi: float = 100.0) -> str:
    """Unicode sparkline for a series of values on a fixed scale."""
    if not values:
        return ""
    span = max(hi - lo, 1e-9)
    return "".join(
        _SPARK_CHARS[min(len(_SPARK_CHARS) - 1,
                         int((max(lo, min(hi, v)) - lo) / span * (len(_SPARK_CHARS) - 1)))]
        for v in values
    )
