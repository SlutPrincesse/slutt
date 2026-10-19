"""Time-travel debugging: snapshot state, step back, branch."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Snapshot:
    id: int
    state: dict[str, Any]


class TimeTravelDebugger:
    def __init__(self):
        self._snapshots: list[Snapshot] = []
        self._cursor: int = -1

    def snapshot(self, state: dict[str, Any]) -> int:
        sid = len(self._snapshots)
        self._snapshots.append(Snapshot(id=sid, state=dict(state)))
        self._cursor = sid
        return sid

    def step_back(self) -> Snapshot | None:
        if self._cursor > 0:
            self._cursor -= 1
            return self._snapshots[self._cursor]
        return None

    def step_forward(self) -> Snapshot | None:
        if self._cursor < len(self._snapshots) - 1:
            self._cursor += 1
            return self._snapshots[self._cursor]
        return None

    def branch(self, snapshot_id: int) -> list[Snapshot]:
        return self._snapshots[:snapshot_id + 1]

    def current(self) -> Snapshot | None:
        if 0 <= self._cursor < len(self._snapshots):
            return self._snapshots[self._cursor]
        return None
