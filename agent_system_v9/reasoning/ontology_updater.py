import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OntologyRelationType(Enum):
    SUBCLASS_OF = "subclass_of"
    INSTANCE_OF = "instance_of"
    PART_OF = "part_of"
    RELATED_TO = "related_to"
    EQUIVALENT_TO = "equivalent_to"
    DISJOINT_FROM = "disjoint_from"
    PROPERTY_OF = "property_of"
    DOMAIN_OF = "domain_of"
    RANGE_OF = "range_of"


@dataclass
class OntologyConcept:
    id: str
    uri: str
    label: str
    description: str = ""
    concept_type: str = "Class"
    properties: dict[str, Any] = field(default_factory=dict)
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    equivalents: list[str] = field(default_factory=list)
    disjoint: list[str] = field(default_factory=list)
    source: str = ""
    confidence: float = 1.0
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:12]
        if not self.uri:
            self.uri = f"http://agent-system-v9.org/ontology#{self.label.replace(' ', '_')}"


class OntologyUpdater:
    def __init__(self):
        self.concepts: dict[str, OntologyConcept] = {}
        self._uri_index: dict[str, str] = {}
        self._label_index: dict[str, str] = {}
        self._type_index: dict[str, set[str]] = defaultdict(set)
        self._relations: dict[str, list[tuple]] = defaultdict(list)

    def add_concept(self, concept: OntologyConcept) -> str:
        self.concepts[concept.id] = concept
        self._uri_index[concept.uri] = concept.id
        self._label_index[concept.label.lower()] = concept.id
        self._type_index[concept.concept_type].add(concept.id)
        return concept.id

    def get_concept(self, concept_id: str) -> OntologyConcept | None:
        return self.concepts.get(concept_id)

    def get_concept_by_uri(self, uri: str) -> OntologyConcept | None:
        cid = self._uri_index.get(uri)
        return self.concepts.get(cid) if cid else None

    def get_concept_by_label(self, label: str) -> OntologyConcept | None:
        cid = self._label_index.get(label.lower())
        return self.concepts.get(cid) if cid else None

    def get_concepts_by_type(self, concept_type: str) -> list[OntologyConcept]:
        return [self.concepts[cid] for cid in self._type_index.get(concept_type, set()) if cid in self.concepts]

    def add_relation(self, source_id: str, target_id: str, relation_type: OntologyRelationType):
        if source_id in self.concepts and target_id in self.concepts:
            self._relations[source_id].append((target_id, relation_type))
            self.concepts[source_id].updated_at = datetime.utcnow().isoformat()

            if relation_type == OntologyRelationType.SUBCLASS_OF:
                self.concepts[source_id].parents.append(target_id)
                self.concepts[target_id].children.append(source_id)
            elif relation_type == OntologyRelationType.EQUIVALENT_TO:
                self.concepts[source_id].equivalents.append(target_id)
                self.concepts[target_id].equivalents.append(source_id)
            elif relation_type == OntologyRelationType.DISJOINT_FROM:
                self.concepts[source_id].disjoint.append(target_id)
                self.concepts[target_id].disjoint.append(source_id)

    def get_relations(self, concept_id: str) -> list[tuple]:
        return self._relations.get(concept_id, [])

    def get_hierarchy(self, concept_id: str, direction: str = "both") -> dict[str, list[str]]:
        result = {"parents": [], "children": []}

        def collect_parents(cid: str, visited: set[str]):
            if cid in visited:
                return
            visited.add(cid)
            concept = self.concepts.get(cid)
            if concept:
                for parent in concept.parents:
                    result["parents"].append(parent)
                    collect_parents(parent, visited)

        def collect_children(cid: str, visited: set[str]):
            if cid in visited:
                return
            visited.add(cid)
            concept = self.concepts.get(cid)
            if concept:
                for child in concept.children:
                    result["children"].append(child)
                    collect_children(child, visited)

        if direction in ("both", "up"):
            collect_parents(concept_id, set())
        if direction in ("both", "down"):
            collect_children(concept_id, set())

        return result

    def update_from_observations(self, observations: list[dict[str, Any]]) -> list[OntologyConcept]:
        new_concepts = []

        for obs in observations:
            label = obs.get("label", "")
            concept_type = obs.get("type", "Class")
            description = obs.get("description", "")
            properties = obs.get("properties", {})
            relations = obs.get("relations", [])

            existing = self.get_concept_by_label(label)
            if existing:
                existing.description = description
                existing.properties.update(properties)
                existing.confidence = min(1.0, existing.confidence + 0.1)
                existing.version += 1
                existing.updated_at = datetime.utcnow().isoformat()
            else:
                concept = OntologyConcept(
                    id="",
                    uri="",
                    label=label,
                    description=description,
                    concept_type=concept_type,
                    properties=properties,
                    source=obs.get("source", "observation"),
                    confidence=obs.get("confidence", 0.8),
                )
                self.add_concept(concept)
                new_concepts.append(concept)

            for rel in relations:
                target_label = rel.get("target", "")
                rel_type = OntologyRelationType(rel.get("type", "related_to"))
                target = self.get_concept_by_label(target_label)
                if target and existing:
                    self.add_relation(existing.id, target.id, rel_type)
                elif target:
                    new_c = self.get_concept_by_label(label)
                    if new_c:
                        self.add_relation(new_c.id, target.id, rel_type)

        return new_concepts

    def merge_ontology(self, other: "OntologyUpdater", prefix: str = "") -> int:
        merged = 0
        for concept in other.concepts.values():
            new_label = f"{prefix}{concept.label}" if prefix else concept.label
            existing = self.get_concept_by_label(new_label)

            if existing:
                existing.properties.update(concept.properties)
                existing.description = concept.description or existing.description
                existing.confidence = max(existing.confidence, concept.confidence)
                existing.version += 1
            else:
                new_concept = OntologyConcept(
                    id="",
                    uri=concept.uri.replace(concept.label, new_label) if prefix else concept.uri,
                    label=new_label,
                    description=concept.description,
                    concept_type=concept.concept_type,
                    properties=concept.properties.copy(),
                    source=f"{concept.source}_merged",
                    confidence=concept.confidence,
                )
                self.add_concept(new_concept)
                merged += 1

        for source_id, relations in other._relations.items():
            source_concept = other.concepts.get(source_id)
            if not source_concept:
                continue
            new_source_label = f"{prefix}{source_concept.label}" if prefix else source_concept.label
            new_source = self.get_concept_by_label(new_source_label)
            if not new_source:
                continue

            for target_id, rel_type in relations:
                target_concept = other.concepts.get(target_id)
                if not target_concept:
                    continue
                new_target_label = f"{prefix}{target_concept.label}" if prefix else target_concept.label
                new_target = self.get_concept_by_label(new_target_label)
                if new_target:
                    self.add_relation(new_source.id, new_target.id, rel_type)

        return merged

    def export_owl(self) -> str:
        lines = [
            "@prefix : <http://agent-system-v9.org/ontology#> .",
            "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
            "",
        ]

        for concept in self.concepts.values():
            lines.append(f":{concept.label.replace(' ', '_')} a owl:{concept.concept_type} ;")
            lines.append(f'    rdfs:label "{concept.label}" ;')
            if concept.description:
                lines.append(f'    rdfs:comment "{concept.description}" ;')

            for parent in concept.parents:
                parent_concept = self.concepts.get(parent)
                if parent_concept:
                    lines.append(f"    rdfs:subClassOf :{parent_concept.label.replace(' ', '_')} ;")

            for equiv in concept.equivalents:
                equiv_concept = self.concepts.get(equiv)
                if equiv_concept:
                    lines.append(f"    owl:equivalentClass :{equiv_concept.label.replace(' ', '_')} ;")

            lines[-1] = lines[-1].rstrip(" ;") + " ."
            lines.append("")

        return "\n".join(lines)

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_concepts": len(self.concepts),
            "by_type": {k: len(v) for k, v in self._type_index.items()},
            "total_relations": sum(len(r) for r in self._relations.values()),
        }
