"""
3D Task Graph Visualizer - Renders interactive DAGs dissolving on completion and spawning subtasks
"""
import threading
import time
import uuid
import json
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DISSOLVED = "dissolved"


@dataclass
class TaskNode:
    node_id: str
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    progress: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    subtasks: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None


@dataclass
class TaskEdge:
    edge_id: str
    source: str
    target: str
    edge_type: str = "depends_on"
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskGraphVisualizer:
    def __init__(self):
        self._nodes: Dict[str, TaskNode] = {}
        self._edges: Dict[str, TaskEdge] = {}
        self._adjacency: Dict[str, Set[str]] = defaultdict(set)
        self._reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self._layout_algorithm = "force_directed"
        self._callbacks: Dict[str, List[Callable]] = {
            "node_added": [],
            "node_updated": [],
            "node_removed": [],
            "edge_added": [],
            "edge_removed": [],
            "graph_layout": []
        }
    
    def add_task(self, name: str, description: str = "",
                 parent_id: str = None, metadata: Dict = None) -> str:
        node_id = str(uuid.uuid4())[:8]
        
        node = TaskNode(
            node_id=node_id,
            name=name,
            description=description,
            parent_id=parent_id,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._nodes[node_id] = node
            if parent_id:
                self._adjacency[parent_id].add(node_id)
                self._reverse_adjacency[node_id].add(parent_id)
                node.subtasks.append(parent_id)
        
        self._notify_node_added(node)
        return node_id
    
    def add_dependency(self, source: str, target: str, edge_type: str = "depends_on") -> str:
        edge_id = str(uuid.uuid4())[:8]
        
        edge = TaskEdge(
            edge_id=edge_id,
            source=source,
            target=target,
            edge_type=edge_type
        )
        
        with self._lock:
            self._edges[edge_id] = edge
            self._adjacency[source].add(target)
            self._reverse_adjacency[target].add(source)
        
        self._notify_edge_added(edge)
        return edge_id
    
    def update_status(self, node_id: str, status: TaskStatus, progress: float = None):
        with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return False
            
            node.status = status
            if progress is not None:
                node.progress = progress
            
            if status == TaskStatus.RUNNING and node.started_at is None:
                node.started_at = time.time()
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                node.completed_at = time.time()
                
                if status == TaskStatus.COMPLETED:
                    # Dissolve completed node after delay
                    threading.Timer(2.0, lambda: self.dissolve_node(node_id)).start()
        
        self._notify_node_updated(node)
        return True
    
    def dissolve_node(self, node_id: str) -> bool:
        with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return False
            
            node.status = TaskStatus.DISSOLVED
            
            # Remove edges
            edges_to_remove = [eid for eid, e in self._edges.items() 
                             if e.source == node_id or e.target == node_id]
            for eid in edges_to_remove:
                del self._edges[eid]
            
            # Remove from adjacency
            for source in self._reverse_adjacency.get(node_id, set()):
                self._adjacency[source].discard(node_id)
            for target in self._adjacency.get(node_id, set()):
                self._reverse_adjacency[target].discard(node_id)
            
            del self._adjacency[node_id]
            del self._reverse_adjacency[node_id]
        
        self._notify_node_removed(node)
        return True
    
    def spawn_subtask(self, parent_id: str, name: str, description: str = "") -> str:
        child_id = self.add_task(name, description, parent_id)
        
        with self._lock:
            parent = self._nodes.get(parent_id)
            if parent:
                parent.subtasks.append(child_id)
        
        return child_id
    
    def get_node(self, node_id: str) -> Optional[TaskNode]:
        with self._lock:
            return self._nodes.get(node_id)
    
    def get_children(self, node_id: str) -> List[TaskNode]:
        with self._lock:
            children = self._adjacency.get(node_id, set())
            return [self._nodes[cid] for cid in children if cid in self._nodes]
    
    def get_parents(self, node_id: str) -> List[TaskNode]:
        with self._lock:
            parents = self._reverse_adjacency.get(node_id, set())
            return [self._nodes[pid] for pid in parents if pid in self._nodes]
    
    def get_graph_data(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "nodes": [{"id": n.node_id, "name": n.name, "status": n.status.value,
                          "progress": n.progress, "position": n.position} 
                         for n in self._nodes.values()],
                "edges": [{"source": e.source, "target": e.target, "type": e.edge_type}
                         for e in self._edges.values()]
            }
    
    def compute_layout(self, algorithm: str = "force_directed") -> Dict[str, Dict[str, float]]:
        with self._lock:
            nodes = list(self._nodes.values())
        
        if algorithm == "force_directed":
            positions = self._force_directed_layout(nodes)
        elif algorithm == "hierarchical":
            positions = self._hierarchical_layout(nodes)
        else:
            positions = self._circular_layout(nodes)
        
        with self._lock:
            for node in nodes:
                if node.node_id in positions:
                    node.position = positions[node.node_id]
        
        self._notify_layout_computed(positions)
        return positions
    
    def _force_directed_layout(self, nodes: List[TaskNode]) -> Dict[str, Dict[str, float]]:
        # Simplified force-directed layout
        positions = {}
        n = len(nodes)
        
        for i, node in enumerate(nodes):
            angle = 2 * 3.14159 * i / max(1, n)
            radius = 100 + hash(node.node_id) % 200
            positions[node.node_id] = {
                "x": radius * math.cos(angle),
                "y": radius * math.sin(angle),
                "z": 0
            }
        
        return positions
    
    def _hierarchical_layout(self, nodes: List[TaskNode]) -> Dict[str, Dict[str, float]]:
        positions = {}
        levels = defaultdict(list)
        
        # Calculate depths
        for node in nodes:
            depth = 0
            current = node.parent_id
            while current and current in self._nodes:
                depth += 1
                current = self._nodes[current].parent_id
            levels[depth].append(node)
        
        for depth, level_nodes in levels.items():
            for i, node in enumerate(level_nodes):
                positions[node.node_id] = {
                    "x": i * 200 - len(level_nodes) * 100,
                    "y": -depth * 150,
                    "z": 0
                }
        
        return positions
    
    def _circular_layout(self, nodes: List[TaskNode]) -> Dict[str, Dict[str, float]]:
        positions = {}
        n = len(nodes)
        for i, node in enumerate(nodes):
            angle = 2 * 3.14159 * i / max(1, n)
            positions[node.node_id] = {
                "x": 200 * math.cos(angle),
                "y": 200 * math.sin(angle),
                "z": 0
            }
        return positions
    
    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _notify_node_added(self, node: TaskNode):
        for cb in self._callbacks["node_added"]:
            try:
                cb(node)
            except Exception:
                pass
    
    def _notify_node_updated(self, node: TaskNode):
        for cb in self._callbacks["node_updated"]:
            try:
                cb(node)
            except Exception:
                pass
    
    def _notify_node_removed(self, node: TaskNode):
        for cb in self._callbacks["node_removed"]:
            try:
                cb(node)
            except Exception:
                pass
    
    def _notify_edge_added(self, edge: TaskEdge):
        for cb in self._callbacks["edge_added"]:
            try:
                cb(edge)
            except Exception:
                pass
    
    def _notify_layout_computed(self, positions: Dict):
        for cb in self._callbacks["graph_layout"]:
            try:
                cb(positions)
            except Exception:
                pass


import math

_task_graph_viz: Optional[TaskGraphVisualizer] = None

def get_task_graph_visualizer() -> TaskGraphVisualizer:
    global _task_graph_viz
    if _task_graph_viz is None:
        _task_graph_viz = TaskGraphVisualizer()
    return _task_graph_viz