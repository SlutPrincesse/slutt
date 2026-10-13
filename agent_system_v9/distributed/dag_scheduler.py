"""
DAG Scheduler - Directed Acyclic Graph task scheduler
"""
import asyncio
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from heapq import heappop, heappush
from typing import Any


class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class TaskPriority(Enum):
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class Task:
    task_id: str
    name: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.NORMAL
    timeout: float | None = None
    retries: int = 0
    max_retries: int = 3
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other):
        return self.priority.value > other.priority.value


@dataclass
class DAG:
    dag_id: str
    name: str
    tasks: dict[str, Task] = field(default_factory=dict)
    edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    reverse_edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_task(self, task: Task):
        self.tasks[task.task_id] = task

    def add_edge(self, from_task: str, to_task: str):
        self.edges[from_task].add(to_task)
        self.reverse_edges[to_task].add(from_task)

    def get_dependencies(self, task_id: str) -> set[str]:
        return self.reverse_edges.get(task_id, set())

    def get_dependents(self, task_id: str) -> set[str]:
        return self.edges.get(task_id, set())

    def topological_sort(self) -> list[str]:
        in_degree = {task_id: len(self.get_dependencies(task_id)) for task_id in self.tasks}
        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        result = []

        while queue:
            task_id = queue.popleft()
            result.append(task_id)
            for dependent in self.get_dependents(task_id):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(self.tasks):
            raise ValueError("DAG contains cycles")

        return result

    def validate(self) -> list[str]:
        errors = []
        for task_id, task in self.tasks.items():
            for dep in task.dependencies:
                if dep not in self.tasks:
                    errors.append(f"Task {task_id} depends on non-existent task {dep}")
        return errors


class DAGScheduler:
    def __init__(
        self,
        max_concurrent: int = 10,
        default_timeout: float = 300.0,
        enable_priority: bool = True,
    ):
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.enable_priority = enable_priority
        self.dags: dict[str, DAG] = {}
        self.running_tasks: dict[str, asyncio.Task] = {}
        self.completed_tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._semaphore: asyncio.Semaphore | None = None
        self._task_queue: list[Task] = []
        _callbacks: list[Callable] = []

    async def start(self):
        self._running = True
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        asyncio.create_task(self._scheduler_loop())

    async def stop(self, wait: bool = True):
        self._running = False
        if wait:
            while self.running_tasks:
                await asyncio.sleep(0.1)

    def register_dag(self, dag: DAG) -> str:
        errors = dag.validate()
        if errors:
            raise ValueError(f"DAG validation failed: {errors}")
        self.dags[dag.dag_id] = dag
        return dag.dag_id

    def submit_dag(self, dag: DAG) -> str:
        dag_id = self.register_dag(dag)
        self._enqueue_ready_tasks(dag)
        return dag_id

    def _enqueue_ready_tasks(self, dag: DAG):
        for task in dag.tasks.values():
            if task.status == TaskStatus.PENDING and not dag.get_dependencies(task.task_id):
                task.status = TaskStatus.READY
                heappush(self._task_queue, task)

    async def _scheduler_loop(self):
        while self._running:
            if self._task_queue and len(self.running_tasks) < self.max_concurrent:
                task = heappop(self._task_queue)
                if task.status == TaskStatus.READY:
                    asyncio.create_task(self._execute_task(task))
            await asyncio.sleep(0.01)

    async def _execute_task(self, task: Task):
        async with self._semaphore:
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()

            try:
                if asyncio.iscoroutinefunction(task.func):
                    if task.timeout:
                        task.result = await asyncio.wait_for(
                            task.func(*task.args, **task.kwargs),
                            timeout=task.timeout,
                        )
                    else:
                        task.result = await task.func(*task.args, **task.kwargs)
                else:
                    task.result = task.func(*task.args, **task.kwargs)

                task.status = TaskStatus.COMPLETED
                task.completed_at = time.time()
            except asyncio.TimeoutError:
                task.error = f"Task timed out after {task.timeout}s"
                await self._handle_failure(task)
            except Exception as e:
                task.error = str(e)
                await self._handle_failure(task)

            self.completed_tasks[task.task_id] = task
            await self._notify_callbacks(task)

            dag = self._find_dag_for_task(task.task_id)
            if dag:
                await self._check_dependents(dag, task)

    async def _handle_failure(self, task: Task):
        if task.retries < task.max_retries:
            task.retries += 1
            task.status = TaskStatus.READY
            heappush(self._task_queue, task)
        else:
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()

    async def _check_dependents(self, dag: DAG, completed_task: Task):
        for dependent_id in dag.get_dependents(completed_task.task_id):
            dependent = dag.tasks[dependent_id]
            if dependent.status == TaskStatus.PENDING:
                deps = dag.get_dependencies(dependent_id)
                all_completed = all(
                    dag.tasks[dep_id].status == TaskStatus.COMPLETED
                    for dep_id in deps
                )
                if all_completed:
                    dependent.status = TaskStatus.READY
                    heappush(self._task_queue, dependent)

    def _find_dag_for_task(self, task_id: str) -> DAG | None:
        for dag in self.dags.values():
            if task_id in dag.tasks:
                return dag
        return None

    def add_callback(self, callback: Callable):
        self._callbacks.append(callback)

    async def _notify_callbacks(self, task: Task):
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(task)
                else:
                    callback(task)
            except Exception:
                pass

    def get_task_status(self, task_id: str) -> TaskStatus | None:
        for dag in self.dags.values():
            if task_id in dag.tasks:
                return dag.tasks[task_id].status
        if task_id in self.completed_tasks:
            return self.completed_tasks[task_id].status
        return None

    def get_dag_status(self, dag_id: str) -> dict[str, Any]:
        dag = self.dags.get(dag_id)
        if not dag:
            return {}

        status_counts = defaultdict(int)
        for task in dag.tasks.values():
            status_counts[task.status.value] += 1

        return {
            "dag_id": dag_id,
            "name": dag.name,
            "total_tasks": len(dag.tasks),
            "status_counts": dict(status_counts),
            "is_complete": all(
                t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)
                for t in dag.tasks.values()
            ),
        }

    def get_results(self, dag_id: str) -> dict[str, Any]:
        dag = self.dags.get(dag_id)
        if not dag:
            return {}
        return {tid: task.result for tid, task in dag.tasks.items() if task.status == TaskStatus.COMPLETED}

    def cancel_dag(self, dag_id: str):
        dag = self.dags.get(dag_id)
        if not dag:
            return
        for task in dag.tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.READY):
                task.status = TaskStatus.CANCELLED

    def retry_failed(self, dag_id: str):
        dag = self.dags.get(dag_id)
        if not dag:
            return
        for task in dag.tasks.values():
            if task.status == TaskStatus.FAILED:
                task.status = TaskStatus.READY
                task.retries = 0
                task.error = None
                heappush(self._task_queue, task)


class DynamicDAGBuilder:
    def __init__(self, scheduler: DAGScheduler):
        self.scheduler = scheduler
        self.current_dag: DAG | None = None

    def new_dag(self, name: str) -> 'DynamicDAGBuilder':
        self.current_dag = DAG(dag_id=str(uuid.uuid4()), name=name)
        return self

    def add_task(
        self,
        name: str,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        dependencies: list[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: float = None,
        max_retries: int = 3,
    ) -> 'DynamicDAGBuilder':
        if not self.current_dag:
            raise ValueError("No DAG started")

        task = Task(
            task_id=str(uuid.uuid4()),
            name=name,
            func=func,
            args=args,
            kwargs=kwargs or {},
            dependencies=dependencies or [],
            priority=priority,
            timeout=timeout,
            max_retries=max_retries,
        )

        self.current_dag.add_task(task)

        for dep_id in task.dependencies:
            self.current_dag.add_edge(dep_id, task.task_id)

        return self

    def build(self) -> DAG:
        if not self.current_dag:
            raise ValueError("No DAG to build")
        dag = self.current_dag
        self.current_dag = None
        return dag

    def build_and_submit(self) -> str:
        dag = self.build()
        return self.scheduler.submit_dag(dag)


class WorkflowEngine:
    def __init__(self, scheduler: DAGScheduler):
        self.scheduler = scheduler
        self.workflows: dict[str, dict] = {}

    def define_workflow(self, name: str, steps: list[dict]) -> str:
        builder = DynamicDAGBuilder(self.scheduler).new_dag(name)

        task_ids = {}
        for step in steps:
            task_ids[step["name"]] = str(uuid.uuid4())

        for step in steps:
            task_id = task_ids[step["name"]]
            deps = [task_ids[dep] for dep in step.get("depends_on", [])]
            builder.add_task(
                name=step["name"],
                func=step["func"],
                args=step.get("args", ()),
                kwargs=step.get("kwargs", {}),
                dependencies=deps,
                priority=TaskPriority(step.get("priority", TaskPriority.NORMAL.value)),
                timeout=step.get("timeout"),
                max_retries=step.get("max_retries", 3),
            )

        return builder.build_and_submit()

    def execute_workflow(self, workflow_id: str, inputs: dict[str, Any] = None) -> dict[str, Any]:
        # Execute synchronously for simple cases
        pass
