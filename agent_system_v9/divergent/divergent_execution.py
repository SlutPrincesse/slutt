"""
Worktree-Isolated Divergent Execution - Spawns parallel worker threads in isolated git worktrees
"""
import os
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ExecutionStatus(Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MERGED = "merged"


@dataclass
class WorktreeConfig:
    base_repo: str
    branch_prefix: str = "divergent-"
    max_worktrees: int = 10
    auto_cleanup: bool = True
    isolation_level: str = "full"  # "full", "partial", "shared"


@dataclass
class ExecutionResult:
    execution_id: str
    worktree_path: str
    branch_name: str
    status: ExecutionStatus
    start_time: float
    end_time: float | None = None
    output: str = ""
    error: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    fitness_score: float = 0.0
    mutations: list[dict[str, Any]] = field(default_factory=list)


class DivergentExecutor:
    def __init__(self, config: WorktreeConfig = None):
        self.config = config or WorktreeConfig()
        self._worktrees: dict[str, str] = {}  # execution_id -> worktree_path
        self._results: dict[str, ExecutionResult] = {}
        self._lock = threading.RLock()
        self._running = False
        self._executor_pool: list[threading.Thread] = []

    def prepare_worktree(self, execution_id: str = None) -> tuple[str, str]:
        """Create a new isolated worktree for divergent execution"""
        if execution_id is None:
            execution_id = str(uuid.uuid4())[:8]

        base_path = Path(self.config.base_repo).resolve()
        if not (base_path / ".git").exists():
            raise ValueError(f"Not a git repository: {base_path}")

        branch_name = f"{self.config.branch_prefix}{execution_id}"
        worktree_path = base_path.parent / f"{base_path.name}-{branch_name}"

        # Create worktree
        try:
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
                cwd=base_path,
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create worktree: {e.stderr.decode()}")

        with self._lock:
            self._worktrees[execution_id] = str(worktree_path)

        return execution_id, str(worktree_path)

    def execute(self, execution_id: str,
                command: list[str],
                env: dict[str, str] = None,
                timeout: float = 300.0) -> ExecutionResult:

        worktree_path = self._worktrees.get(execution_id)
        if not worktree_path:
            raise ValueError(f"Worktree not found for {execution_id}")

        result = ExecutionResult(
            execution_id=execution_id,
            worktree_path=worktree_path,
            branch_name=f"{self.config.branch_prefix}{execution_id}",
            status=ExecutionStatus.RUNNING,
            start_time=time.time()
        )

        with self._lock:
            self._results[execution_id] = result

        try:
            env_vars = os.environ.copy()
            if env:
                env_vars.update(env)

            proc = subprocess.run(
                command,
                cwd=worktree_path,
                env=env_vars,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            result.output = proc.stdout
            result.error = proc.stderr
            result.end_time = time.time()

            if proc.returncode == 0:
                result.status = ExecutionStatus.COMPLETED
            else:
                result.status = ExecutionStatus.FAILED

        except subprocess.TimeoutExpired:
            result.status = ExecutionStatus.FAILED
            result.error = "Execution timeout"
            result.end_time = time.time()
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error = str(e)
            result.end_time = time.time()

        return result

    def execute_async(self, execution_id: str, command: list[str],
                     callback: Callable[[ExecutionResult], None] = None,
                     env: dict[str, str] = None,
                     timeout: float = 300.0):
        """Execute asynchronously with callback"""
        def worker():
            result = self.execute(execution_id, command, env, timeout)
            if callback:
                callback(result)

        thread = threading.Thread(target=worker, daemon=True)
        self._executor_pool.append(thread)
        thread.start()

    def get_result(self, execution_id: str) -> ExecutionResult | None:
        with self._lock:
            return self._results.get(execution_id)

    def list_results(self) -> list[ExecutionResult]:
        with self._lock:
            return list(self._results.values())

    def cleanup_worktree(self, execution_id: str) -> bool:
        worktree_path = self._worktrees.get(execution_id)
        if not worktree_path:
            return False

        try:
            branch_name = f"{self.config.branch_prefix}{execution_id}"
            base_path = Path(self.config.base_repo).resolve()

            # Remove worktree
            subprocess.run(
                ["git", "worktree", "remove", "--force", worktree_path],
                cwd=base_path,
                capture_output=True
            )

            # Delete branch
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=base_path,
                capture_output=True
            )

            # Clean up directory
            shutil.rmtree(worktree_path, ignore_errors=True)

            with self._lock:
                self._worktrees.pop(execution_id, None)

            return True
        except Exception:
            return False

    def cleanup_all(self):
        with self._lock:
            execution_ids = list(self._worktrees.keys())

        for eid in execution_ids:
            self.cleanup_worktree(eid)

    def get_worktree_path(self, execution_id: str) -> str | None:
        with self._lock:
            return self._worktrees.get(execution_id)

    def merge_results(self, execution_ids: list[str],
                     strategy: str = "ast") -> ExecutionResult:
        """Merge results from multiple divergent executions"""
        # Placeholder - actual merging done by ASTNodeMerger
        pass


_divergent_executor: DivergentExecutor | None = None


def get_divergent_executor() -> DivergentExecutor:
    global _divergent_executor
    if _divergent_executor is None:
        from ..core.config import config
        cfg = WorktreeConfig(
            base_repo=config.get_param("divergent", "base_repo", "."),
            max_worktrees=config.get_param("divergent", "max_parallel_worktrees", 10)
        )
        _divergent_executor = DivergentExecutor(cfg)
    return _divergent_executor
