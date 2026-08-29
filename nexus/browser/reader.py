"""Read mode — a page as a reader sees it, not as an actor does."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    id: int
    kind: str
    text: str
    path: list[str] = field(default_factory=list)
    level: int = 0

    @property
    def citation(self) -> str:
        where = " › ".join(self.path) if self.path else "(top)"
        return f"[{self.id}] {where}"


@dataclass
class Document:
    title: str
    url: str
    blocks: list[Block]

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)

    @property
    def headings(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "heading"]

    def outline(self) -> str:
        return "\n".join(f"{'  ' * (b.level - 1)}{b.text}" for b in self.headings)

    def __len__(self) -> int:
        return len(self.blocks)
