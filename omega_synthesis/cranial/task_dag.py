import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set


class TaskState(Enum):
    PENDING = auto()
    READY = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class TaskNode:
    id: str
    name: str
    state: TaskState = TaskState.PENDING
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Any = None
    error: Optional[Exception] = None

    def duration(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.finished_at or time.time()
        return end - self.started_at


class TaskDAG:
    def __init__(self):
        self._nodes: Dict[str, TaskNode] = {}
        self._lock = threading.RLock()

    def add_task(self, task_id: str, name: str, metadata: Optional[Dict[str, Any]] = None) -> TaskNode:
        with self._lock:
            if task_id in self._nodes:
                raise ValueError(f"Task {task_id} already exists")
            node = TaskNode(id=task_id, name=name, metadata=metadata or {})
            self._nodes[task_id] = node
            return node

    def add_dependency(self, task_id: str, depends_on: str) -> None:
        with self._lock:
            if task_id not in self._nodes or depends_on not in self._nodes:
                raise KeyError("Unknown task id")
            self._nodes[task_id].dependencies.add(depends_on)
            self._nodes[depends_on].dependents.add(task_id)

    def get_ready(self) -> List[TaskNode]:
        with self._lock:
            return [n for n in self._nodes.values() if n.state == TaskState.PENDING and not n.dependencies]

    def mark_running(self, task_id: str) -> None:
        with self._lock:
            node = self._nodes[task_id]
            if node.state != TaskState.PENDING:
                raise RuntimeError(f"Cannot run task {task_id} in state {node.state}")
            node.state = TaskState.RUNNING
            node.started_at = time.time()

    def mark_completed(self, task_id: str, result: Any = None) -> None:
        with self._lock:
            node = self._nodes[task_id]
            node.state = TaskState.COMPLETED
            node.finished_at = time.time()
            node.result = result
            self._propagate(task_id)

    def mark_failed(self, task_id: str, error: Exception) -> None:
        with self._lock:
            node = self._nodes[task_id]
            node.state = TaskState.FAILED
            node.finished_at = time.time()
            node.error = error
            self._propagate(task_id)

    def cancel(self, task_id: str) -> None:
        with self._lock:
            node = self._nodes[task_id]
            if node.state == TaskState.COMPLETED:
                return
            node.state = TaskState.CANCELLED
            node.finished_at = time.time()
            for dep in list(node.dependents):
                self.cancel(dep)

    def status(self) -> Dict[str, int]:
        with self._lock:
            counts = defaultdict(int)
            for node in self._nodes.values():
                counts[node.state.name] += 1
            return dict(counts)

    def topological_order(self) -> List[str]:
        with self._lock:
            in_degree = {tid: len(self._nodes[tid].dependencies) for tid in self._nodes}
            queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
            order = []
            while queue:
                tid = queue.popleft()
                order.append(tid)
                for dep in self._nodes[tid].dependents:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        queue.append(dep)
            if len(order) != len(self._nodes):
                raise RuntimeError("Cycle detected in task DAG")
            return order

    def _propagate(self, completed_id: str) -> None:
        completed = self._nodes[completed_id]
        for dependent_id in completed.dependents:
            dependent = self._nodes[dependent_id]
            if dependent.state == TaskState.PENDING:
                dependent.dependencies.discard(completed_id)
                if not dependent.dependencies:
                    dependent.state = TaskState.READY
