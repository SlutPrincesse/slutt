"""Semantic diff memory: store intent + impact of changes in knowledge graph."""
from __future__ import annotations

from typing import Any
import uuid


class SemanticDiffMemory:
    def __init__(self, knowledge_graph=None):
        self.kg = knowledge_graph

    def record(self, old: str, new: str, intent: str, impact: str) -> str:
        node_id = str(uuid.uuid4())
        if self.kg is not None:
            try:
                from agent_system_v9.memory.knowledge_graph import Entity, EntityType
                ent = Entity(
                    id=node_id,
                    entity_type=EntityType.CONCEPT,
                    name=intent[:60],
                    qualified_name=intent[:60],
                    properties={"old": old[:200], "new": new[:200], "impact": impact},
                    source="semantic_diff",
                    confidence=0.9,
                )
                self.kg.add_entity(ent)
            except Exception:
                pass
        return node_id
