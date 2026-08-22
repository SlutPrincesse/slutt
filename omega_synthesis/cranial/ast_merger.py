import ast
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from cranial.task_dag import TaskDAG, TaskNode


class SpeculativeExecutor:
    def __init__(self, dag: TaskDAG):
        self.dag = dag

    def mode_shadow_clones(self, task_id: str, worker_fn: Callable, count: int = 3) -> Optional[TaskNode]:
        clones: List[TaskNode] = []
        for i in range(count):
            clone_id = f"{task_id}__clone_{i}"
            clone = self.dag.add_task(clone_id, f"{task_id} clone {i}")
            self.dag.add_dependency(clone_id, task_id)
            clones.append(clone)

        best: Optional[TaskNode] = None
        best_score = float("-inf")
        for clone in clones:
            result = worker_fn(clone)
            score = self._score(result)
            clone.metadata["score"] = score
            if score > best_score:
                best_score = score
                best = clone

        if best:
            self.dag.mark_completed(task_id, best.result)
        return best

    def mode_schizophrenia(self, task_id: str, prompt_fn: Callable, count: int = 3) -> List[TaskNode]:
        accepted: List[TaskNode] = []
        for i in range(count):
            variant_id = f"{task_id}__variant_{i}"
            variant = self.dag.add_task(variant_id, f"{task_id} variant {i}")
            self.dag.add_dependency(variant_id, task_id)
            result = prompt_fn(variant, index=i)
            if self._verify(result):
                self.dag.mark_completed(variant_id, result)
                accepted.append(variant)
            else:
                self.dag.mark_failed(variant_id, RuntimeError("Verification failed"))
        return accepted

    def _score(self, result: Any) -> float:
        if result is None:
            return 0.0
        return 1.0

    def _verify(self, result: Any) -> bool:
        if result is None:
            return False
        return True


class ASTMerger:
    def __init__(self):
        self._merges: List[Dict[str, Any]] = []

    def merge_functions(self, primary: str, candidates: List[str]) -> str:
        try:
            primary_tree = ast.parse(primary)
            candidate_trees = [ast.parse(c) for c in candidates if c.strip()]
        except SyntaxError:
            return primary

        best_body = primary_tree.body
        best_score = self._function_score(primary_tree)

        for cand in candidate_trees:
            score = self._function_score(cand)
            if score > best_score:
                best_score = score
                best_body = cand.body

        merged = ast.Module(body=best_body, type_ignores=[])
        ast.fix_missing_locations(merged)
        self._merges.append({
            "primary_length": len(primary),
            "candidate_count": len(candidates),
            "selected_score": best_score,
        })
        return ast.unparse(merged)

    def _function_score(self, tree: ast.AST) -> float:
        score = 0.0
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                score += len(node.body)
            if isinstance(node, (ast.While, ast.For)):
                score += 0.5
        return score

    def merge_worktrees(self, worktree_paths: List[str]) -> str:
        combined: Dict[str, str] = {}
        for path in worktree_paths:
            for file in Path(path).rglob("*.py"):
                try:
                    combined[file.name] = file.read_text()
                except Exception:
                    continue

        merged_parts: List[str] = []
        for name, content in combined.items():
            merged_parts.append(content)

        return "\n\n".join(merged_parts)
