from __future__ import annotations

import re

_REF_PATTERN = re.compile(r"^e(\d+)$")


class RefRegistry:
    def __init__(self) -> None:
        self._handle_to_ref: dict[str, str] = {}
        self._next: int = 1

    def assign(self, handle: str) -> str:
        if handle not in self._handle_to_ref:
            self._handle_to_ref[handle] = f"e{self._next}"
            self._next += 1
        return self._handle_to_ref[handle]

    def evict(self, live_handles: set[str]) -> None:
        self._handle_to_ref = {
            h: r for h, r in self._handle_to_ref.items() if h in live_handles
        }

    def reset(self) -> None:
        self._handle_to_ref.clear()

    def is_stale(self, ref: str) -> bool:
        m = _REF_PATTERN.match(ref)
        if not m:
            return False
        return int(m.group(1)) < self._next and ref not in self._handle_to_ref.values()
