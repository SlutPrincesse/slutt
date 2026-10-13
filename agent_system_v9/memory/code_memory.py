import uuid
import hashlib
import json
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path


class NodeType(Enum):
    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    VARIABLE = "variable"
    IMPORT = "import"
    COMMENT = "comment"
    DOCSTRING = "docstring"
    TYPE_DEFINITION = "type_definition"
    MACRO = "macro"


class EdgeType(Enum):
    CALLS = "calls"
    IMPORTS = "imports"
    INHERITS = "inherits"
    CONTAINS = "contains"
    REFERENCES = "references"
    DEFINES = "defines"
    USES = "uses"
    DECORATES = "decorates"
    OVERRIDES = "overrides"
    IMPLEMENTS = "implements"


@dataclass
class CodeNode:
    id: str
    node_type: NodeType
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    summary: str = ""
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        if not self.id:
            content_hash = hashlib.sha256(f"{self.file_path}:{self.start_line}:{self.end_line}".encode()).hexdigest()[:16]
            self.id = f"{self.node_type.value}_{content_hash}"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["node_type"] = self.node_type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeNode":
        data["node_type"] = NodeType(data["node_type"])
        return cls(**data)


@dataclass
class CodeEdge:
    id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        if not self.id:
            content_hash = hashlib.sha256(f"{self.source_id}:{self.target_id}:{self.edge_type.value}".encode()).hexdigest()[:16]
            self.id = f"edge_{content_hash}"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["edge_type"] = self.edge_type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeEdge":
        data["edge_type"] = EdgeType(data["edge_type"])
        return cls(**data)


class CodeMemory:
    def __init__(self, storage_path: Optional[Path] = None):
        self.nodes: Dict[str, CodeNode] = {}
        self.edges: Dict[str, CodeEdge] = {}
        self._node_index: Dict[str, Set[str]] = {}
        self._file_index: Dict[str, Set[str]] = {}
        self._name_index: Dict[str, Set[str]] = {}
        self.storage_path = storage_path
        
        if storage_path and storage_path.exists():
            self.load(storage_path)

    def add_node(self, node: CodeNode) -> str:
        self.nodes[node.id] = node
        self._index_node(node)
        return node.id

    def add_edge(self, edge: CodeEdge) -> str:
        self.edges[edge.id] = edge
        return edge.id

    def _index_node(self, node: CodeNode):
        if node.file_path not in self._file_index:
            self._file_index[node.file_path] = set()
        self._file_index[node.file_path].add(node.id)

        if node.name not in self._name_index:
            self._name_index[node.name] = set()
        self._name_index[node.name].add(node.id)

        if node.node_type.value not in self._node_index:
            self._node_index[node.node_type.value] = set()
        self._node_index[node.node_type.value].add(node.id)

    def get_node(self, node_id: str) -> Optional[CodeNode]:
        return self.nodes.get(node_id)

    def get_nodes_by_file(self, file_path: str) -> List[CodeNode]:
        node_ids = self._file_index.get(file_path, set())
        return [self.nodes[nid] for nid in node_ids if nid in self.nodes]

    def get_nodes_by_name(self, name: str) -> List[CodeNode]:
        node_ids = self._name_index.get(name, set())
        return [self.nodes[nid] for nid in node_ids if nid in self.nodes]

    def get_nodes_by_type(self, node_type: NodeType) -> List[CodeNode]:
        node_ids = self._node_index.get(node_type.value, set())
        return [self.nodes[nid] for nid in node_ids if nid in self.nodes]

    def get_neighbors(self, node_id: str, edge_type: EdgeType = None, direction: str = "both") -> List[CodeNode]:
        neighbors = []
        for edge in self.edges.values():
            if edge_type and edge.edge_type != edge_type:
                continue
            
            if direction in ("both", "outgoing") and edge.source_id == node_id:
                if edge.target_id in self.nodes:
                    neighbors.append(self.nodes[edge.target_id])
            if direction in ("both", "incoming") and edge.target_id == node_id:
                if edge.source_id in self.nodes:
                    neighbors.append(self.nodes[edge.source_id])
        return neighbors

    def get_call_graph(self, root_id: str, depth: int = 3) -> Dict[str, Any]:
        visited = set()
        result = {"nodes": [], "edges": []}
        
        def traverse(node_id: str, current_depth: int):
            if current_depth > depth or node_id in visited:
                return
            visited.add(node_id)
            node = self.nodes.get(node_id)
            if node:
                result["nodes"].append(node.to_dict())
                for edge in self.edges.values():
                    if edge.source_id == node_id and edge.edge_type == EdgeType.CALLS:
                        result["edges"].append(edge.to_dict())
                        traverse(edge.target_id, current_depth + 1)
        
        traverse(root_id, 0)
        return result

    def find_path(self, source_id: str, target_id: str, max_depth: int = 5) -> Optional[List[CodeNode]]:
        from collections import deque
        
        queue = deque([(source_id, [source_id])])
        visited = {source_id}
        
        while queue:
            current_id, path = queue.popleft()
            if current_id == target_id:
                return [self.nodes[nid] for nid in path if nid in self.nodes]
            
            if len(path) >= max_depth:
                continue
            
            for edge in self.edges.values():
                if edge.source_id == current_id and edge.target_id not in visited:
                    visited.add(edge.target_id)
                    queue.append((edge.target_id, path + [edge.target_id]))
        
        return None

    def update_node(self, node_id: str, **kwargs) -> bool:
        if node_id not in self.nodes:
            return False
        node = self.nodes[node_id]
        for key, value in kwargs.items():
            if hasattr(node, key):
                setattr(node, key, value)
        node.updated_at = datetime.utcnow().isoformat()
        return True

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self.nodes:
            return False
        node = self.nodes[node_id]
        self._file_index.get(node.file_path, set()).discard(node_id)
        self._name_index.get(node.name, set()).discard(node_id)
        self._node_index.get(node.node_type.value, set()).discard(node_id)
        
        edges_to_remove = [eid for eid, e in self.edges.items() if e.source_id == node_id or e.target_id == node_id]
        for eid in edges_to_remove:
            del self.edges[eid]
        
        del self.nodes[node_id]
        return True

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "by_type": {k: len(v) for k, v in self._node_index.items()},
            "by_file": len(self._file_index),
            "unique_names": len(self._name_index),
        }

    def save(self, path: Path = None):
        path = path or self.storage_path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": {k: v.to_dict() for k, v in self.edges.items()},
        }
        path.write_text(json.dumps(data, indent=2))

    def load(self, path: Path):
        data = json.loads(path.read_text())
        for nid, ndata in data.get("nodes", {}).items():
            self.nodes[nid] = CodeNode.from_dict(ndata)
        for eid, edata in data.get("edges", {}).items():
            self.edges[eid] = CodeEdge.from_dict(edata)
        
        for node in self.nodes.values():
            self._index_node(node)

    def clear(self):
        self.nodes.clear()
        self.edges.clear()
        self._node_index.clear()
        self._file_index.clear()
        self._name_index.clear()