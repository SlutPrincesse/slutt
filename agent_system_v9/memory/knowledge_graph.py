import json
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from collections import defaultdict


class EntityType(Enum):
    CODE_FILE = "code_file"
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    VARIABLE = "variable"
    TYPE = "type"
    CONCEPT = "concept"
    TOOL = "tool"
    FINDING = "finding"
    VULNERABILITY = "vulnerability"
    DEPENDENCY = "dependency"
    API_ENDPOINT = "api_endpoint"
    DATABASE_TABLE = "database_table"
    CONFIGURATION = "configuration"
    DOCUMENTATION = "documentation"
    TEST = "test"
    BUILD_ARTIFACT = "build_artifact"


class RelationType(Enum):
    CONTAINS = "contains"
    CALLS = "calls"
    IMPORTS = "imports"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    DEPENDS_ON = "depends_on"
    DEFINES = "defines"
    REFERENCES = "references"
    USES = "uses"
    DECORATES = "decorates"
    OVERRIDES = "overrides"
    TESTS = "tests"
    DOCUMENTS = "documents"
    CONFIGURES = "configures"
    DEPLOYS = "deploys"
    GENERATES = "generates"
    TRANSFORMS = "transforms"
    RELATED_TO = "related_to"
    SIMILAR_TO = "similar_to"
    FIXES = "fixes"
    INTRODUCES = "introduces"


@dataclass
class Entity:
    id: str
    entity_type: EntityType
    name: str
    qualified_name: str
    properties: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    source: str = ""
    confidence: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    embedding: Optional[List[float]] = None

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["entity_type"] = self.entity_type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        data["entity_type"] = EntityType(data["entity_type"])
        return cls(**data)


@dataclass
class Relation:
    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    properties: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    confidence: float = 1.0
    source: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["relation_type"] = self.relation_type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Relation":
        data["relation_type"] = RelationType(data["relation_type"])
        return cls(**data)


@dataclass
class GraphQuery:
    pattern: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    limit: int = 100
    offset: int = 0


class KnowledgeGraph:
    def __init__(self, storage_path: Optional[Path] = None):
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}
        self._type_index: Dict[EntityType, Set[str]] = defaultdict(set)
        self._name_index: Dict[str, Set[str]] = defaultdict(set)
        self._outgoing: Dict[str, List[Relation]] = defaultdict(list)
        self._incoming: Dict[str, List[Relation]] = defaultdict(list)
        self._source_index: Dict[str, Set[str]] = defaultdict(set)
        self.storage_path = storage_path

        if storage_path and storage_path.exists():
            self.load(storage_path)

    def add_entity(self, entity: Entity) -> str:
        self.entities[entity.id] = entity
        self._type_index[entity.entity_type].add(entity.id)
        self._name_index[entity.name.lower()].add(entity.id)
        for alias in entity.aliases:
            self._name_index[alias.lower()].add(entity.id)
        self._source_index[entity.source].add(entity.id)
        return entity.id

    def add_relation(self, relation: Relation) -> str:
        self.relations[relation.id] = relation
        self._outgoing[relation.source_id].append(relation)
        self._incoming[relation.target_id].append(relation)
        return relation.id

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        return self.entities.get(entity_id)

    def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        return [self.entities[eid] for eid in self._type_index.get(entity_type, set()) if eid in self.entities]

    def get_entities_by_name(self, name: str) -> List[Entity]:
        return [self.entities[eid] for eid in self._name_index.get(name.lower(), set()) if eid in self.entities]

    def get_entities_by_source(self, source: str) -> List[Entity]:
        return [self.entities[eid] for eid in self._source_index.get(source, set()) if eid in self.entities]

    def get_outgoing(self, entity_id: str, relation_type: RelationType = None) -> List[Relation]:
        relations = self._outgoing.get(entity_id, [])
        if relation_type:
            return [r for r in relations if r.relation_type == relation_type]
        return relations

    def get_incoming(self, entity_id: str, relation_type: RelationType = None) -> List[Relation]:
        relations = self._incoming.get(entity_id, [])
        if relation_type:
            return [r for r in relations if r.relation_type == relation_type]
        return relations

    def get_neighbors(self, entity_id: str, relation_types: List[RelationType] = None, direction: str = "both") -> List[Entity]:
        neighbors = []
        if direction in ("both", "outgoing"):
            for rel in self.get_outgoing(entity_id):
                if relation_types is None or rel.relation_type in relation_types:
                    if rel.target_id in self.entities:
                        neighbors.append(self.entities[rel.target_id])
        if direction in ("both", "incoming"):
            for rel in self.get_incoming(entity_id):
                if relation_types is None or rel.relation_type in relation_types:
                    if rel.source_id in self.entities:
                        neighbors.append(self.entities[rel.source_id])
        return neighbors

    def find_path(self, source_id: str, target_id: str, max_depth: int = 4) -> Optional[List[Entity]]:
        from collections import deque
        
        queue = deque([(source_id, [source_id])])
        visited = {source_id}
        
        while queue:
            current_id, path = queue.popleft()
            if current_id == target_id:
                return [self.entities[nid] for nid in path if nid in self.entities]
            
            if len(path) >= max_depth:
                continue
            
            for rel in self.get_outgoing(current_id):
                if rel.target_id not in visited:
                    visited.add(rel.target_id)
                    queue.append((rel.target_id, path + [rel.target_id]))
        
        return None

    def find_cycles(self, entity_id: str, max_depth: int = 5) -> List[List[Entity]]:
        cycles = []
        
        def dfs(current_id: str, path: List[str], depth: int):
            if depth > max_depth:
                return
            if current_id == entity_id and len(path) > 1:
                cycles.append([self.entities[nid] for nid in path if nid in self.entities])
                return
            
            for rel in self.get_outgoing(current_id):
                if rel.target_id not in path:
                    dfs(rel.target_id, path + [rel.target_id], depth + 1)
        
        dfs(entity_id, [entity_id], 0)
        return cycles

    def get_subgraph(self, entity_ids: List[str], depth: int = 1) -> Dict[str, Any]:
        included = set(entity_ids)
        for eid in entity_ids:
            for rel in self.get_outgoing(eid):
                if rel.target_id in self.entities:
                    included.add(rel.target_id)
            for rel in self.get_incoming(eid):
                if rel.source_id in self.entities:
                    included.add(rel.source_id)
        
        if depth > 1:
            for _ in range(depth - 1):
                new_included = set(included)
                for eid in included:
                    for rel in self.get_outgoing(eid):
                        new_included.add(rel.target_id)
                    for rel in self.get_incoming(eid):
                        new_included.add(rel.source_id)
                included = new_included
        
        sub_entities = {eid: self.entities[eid] for eid in included if eid in self.entities}
        sub_relations = []
        for rel in self.relations.values():
            if rel.source_id in included and rel.target_id in included:
                sub_relations.append(rel)
        
        return {
            "entities": [e.to_dict() for e in sub_entities.values()],
            "relations": [r.to_dict() for r in sub_relations],
        }

    def update_entity(self, entity_id: str, **kwargs) -> bool:
        if entity_id not in self.entities:
            return False
        entity = self.entities[entity_id]
        
        old_name = entity.name
        old_type = entity.entity_type
        
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        
        if "name" in kwargs and kwargs["name"] != old_name:
            self._name_index[old_name.lower()].discard(entity_id)
            self._name_index[kwargs["name"].lower()].add(entity_id)
        
        if "entity_type" in kwargs and kwargs["entity_type"] != old_type:
            self._type_index[old_type].discard(entity_id)
            self._type_index[kwargs["entity_type"]].add(entity_id)
        
        entity.updated_at = datetime.utcnow().isoformat()
        return True

    def remove_entity(self, entity_id: str) -> bool:
        if entity_id not in self.entities:
            return False
        entity = self.entities[entity_id]
        
        self._type_index[entity.entity_type].discard(entity_id)
        self._name_index[entity.name.lower()].discard(entity_id)
        for alias in entity.aliases:
            self._name_index[alias.lower()].discard(entity_id)
        self._source_index[entity.source].discard(entity_id)
        
        for rel in self._outgoing.get(entity_id, []):
            self._incoming[rel.target_id].remove(rel)
        for rel in self._incoming.get(entity_id, []):
            self._outgoing[rel.source_id].remove(rel)
        
        del self._outgoing[entity_id]
        del self._incoming[entity_id]
        del self.entities[entity_id]
        return True

    def remove_relation(self, relation_id: str) -> bool:
        if relation_id not in self.relations:
            return False
        rel = self.relations[relation_id]
        self._outgoing[rel.source_id].remove(rel)
        self._incoming[rel.target_id].remove(rel)
        del self.relations[relation_id]
        return True

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_entities": len(self.entities),
            "total_relations": len(self.relations),
            "by_type": {k.value: len(v) for k, v in self._type_index.items()},
            "by_source": {k: len(v) for k, v in self._source_index.items()},
        }

    def save(self, path: Path = None):
        path = path or self.storage_path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "entities": {k: v.to_dict() for k, v in self.entities.items()},
            "relations": {k: v.to_dict() for k, v in self.relations.items()},
        }
        path.write_text(json.dumps(data, indent=2))

    def load(self, path: Path):
        data = json.loads(path.read_text())
        for eid, edata in data.get("entities", {}).items():
            self.entities[eid] = Entity.from_dict(edata)
            self._type_index[self.entities[eid].entity_type].add(eid)
            self._name_index[self.entities[eid].name.lower()].add(eid)
            for alias in self.entities[eid].aliases:
                self._name_index[alias.lower()].add(eid)
            self._source_index[self.entities[eid].source].add(eid)
        
        for rid, rdata in data.get("relations", {}).items():
            self.relations[rid] = Relation.from_dict(rdata)
            self._outgoing[rdata["source_id"]].append(self.relations[rid])
            self._incoming[rdata["target_id"]].append(self.relations[rid])

    def clear(self):
        self.entities.clear()
        self.relations.clear()
        self._type_index.clear()
        self._name_index.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._source_index.clear()