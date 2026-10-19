"""Distill episodic memory into semantic knowledge graph with decay."""
from __future__ import annotations

from typing import Any


class MemoryDistiller:
    def __init__(self, knowledge_graph=None, episodic_store=None):
        self.kg = knowledge_graph
        self.episodic = episodic_store

    def distill(self) -> int:
        if self.episodic is None or self.kg is None:
            return 0
        count = 0
        try:
            from agent_system_v9.memory.knowledge_graph import Entity, EntityType
            import uuid
            for ep in list(self.episodic.episodes.values()):
                if ep.importance < 0.2:
                    continue
                ent = Entity(
                    id=str(uuid.uuid4()),
                    entity_type=EntityType.CONCEPT,
                    name=ep.title,
                    qualified_name=ep.title,
                    description=ep.description,
                    source="distillation",
                    confidence=ep.importance,
                )
                self.kg.add_entity(ent)
                count += 1
            # decay
            self.episodic.decay_importance(0.95)
            self.episodic.prune(0.1)
        except Exception:
            pass
        return count
