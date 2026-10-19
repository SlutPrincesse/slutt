"""Lineage tracking for distillation decisions."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LineageNode:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: str | None = None
    kind: str = ""  # trace, distillation, policy, tool, prompt
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


class LineageTracker:
    def __init__(self):
        self.nodes: dict[str, LineageNode] = {}

    def add(self, node: LineageNode) -> str:
        self.nodes[node.id] = node
        return node.id

    def children_of(self, node_id: str) -> list[LineageNode]:
        return [n for n in self.nodes.values() if n.parent_id == node_id]

    def chain(self, node_id: str) -> list[LineageNode]:
        chain = []
        cur = self.nodes.get(node_id)
        while cur is not None:
            chain.append(cur)
            cur = self.nodes.get(cur.parent_id) if cur.parent_id else None
        return chain
