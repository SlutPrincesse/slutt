import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConceptType(Enum):
    ENTITY = "entity"
    RELATION = "relation"
    PROPERTY = "property"
    CLASS = "class"
    FUNCTION = "function"
    PATTERN = "pattern"
    ABSTRACTION = "abstraction"
    HEURISTIC = "heuristic"


@dataclass
class Concept:
    id: str
    name: str
    concept_type: ConceptType
    definition: str
    properties: dict[str, Any] = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)
    counter_examples: list[str] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)
    confidence: float = 1.0
    abstraction_level: int = 0
    source: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha256(f"{self.name}:{self.concept_type.value}".encode()).hexdigest()[:12]


class ConceptAbstractor:
    def __init__(self):
        self.concepts: dict[str, Concept] = {}
        self._name_index: dict[str, str] = {}
        self._type_index: dict[ConceptType, set[str]] = defaultdict(set)
        self._abstraction_hierarchy: dict[str, set[str]] = defaultdict(set)

    def add_concept(self, concept: Concept) -> str:
        self.concepts[concept.id] = concept
        self._name_index[concept.name.lower()] = concept.id
        self._type_index[concept.concept_type].add(concept.id)
        return concept.id

    def get_concept(self, concept_id: str) -> Concept | None:
        return self.concepts.get(concept_id)

    def get_concept_by_name(self, name: str) -> Concept | None:
        cid = self._name_index.get(name.lower())
        return self.concepts.get(cid) if cid else None

    def get_concepts_by_type(self, concept_type: ConceptType) -> list[Concept]:
        return [self.concepts[cid] for cid in self._type_index.get(concept_type, set()) if cid in self.concepts]

    def abstract_from_examples(self, name: str, examples: list[str], concept_type: ConceptType = ConceptType.PATTERN) -> Concept:
        common = self._find_common_pattern(examples)
        concept = Concept(
            id="",
            name=name,
            concept_type=concept_type,
            definition=common,
            examples=examples[:5],
            abstraction_level=1,
            source="abstraction",
        )
        self.add_concept(concept)
        return concept

    def _find_common_pattern(self, examples: list[str]) -> str:
        if not examples:
            return ""
        if len(examples) == 1:
            return examples[0]

        words = [set(ex.split()) for ex in examples]
        common_words = set.intersection(*words) if words else set()
        return " ".join(sorted(common_words)) if common_words else "Common pattern across examples"

    def create_abstraction(self, name: str, base_concepts: list[str], definition: str) -> Concept:
        base_ids = [self._name_index.get(c.lower()) for c in base_concepts if c.lower() in self._name_index]
        concept = Concept(
            id="",
            name=name,
            concept_type=ConceptType.ABSTRACTION,
            definition=definition,
            related_concepts=base_ids,
            abstraction_level=max((self.concepts[cid].abstraction_level for cid in base_ids), default=0) + 1,
            source="abstraction",
        )
        self.add_concept(concept)

        for cid in base_ids:
            self._abstraction_hierarchy[concept.id].add(cid)

        return concept

    def relate_concepts(self, concept_id: str, related_id: str, relation: str = "related"):
        if concept_id in self.concepts and related_id in self.concepts:
            self.concepts[concept_id].related_concepts.append(related_id)
            self.concepts[concept_id].updated_at = datetime.utcnow().isoformat()

    def get_abstraction_chain(self, concept_id: str) -> list[Concept]:
        chain = []
        current = concept_id
        while current in self._abstraction_hierarchy and self._abstraction_hierarchy[current]:
            parent = next(iter(self._abstraction_hierarchy[current]))
            if parent in self.concepts:
                chain.append(self.concepts[parent])
                current = parent
            else:
                break
        return chain

    def get_specializations(self, concept_id: str) -> list[Concept]:
        specializations = []
        for cid, parents in self._abstraction_hierarchy.items():
            if concept_id in parents and cid in self.concepts:
                specializations.append(self.concepts[cid])
        return specializations

    def search_concepts(self, query: str, limit: int = 10) -> list[Concept]:
        query_lower = query.lower()
        results = []
        for concept in self.concepts.values():
            score = 0
            if query_lower in concept.name.lower():
                score += 10
            if query_lower in concept.definition.lower():
                score += 5
            if any(query_lower in ex.lower() for ex in concept.examples):
                score += 3
            if score > 0:
                results.append((score, concept))

        results.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in results[:limit]]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_concepts": len(self.concepts),
            "by_type": {k.value: len(v) for k, v in self._type_index.items()},
            "abstraction_levels": len(self._abstraction_hierarchy),
        }
