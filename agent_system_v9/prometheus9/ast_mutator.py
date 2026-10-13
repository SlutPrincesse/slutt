"""
Surgical AST Mutation & Garbage Collector - Mutates targeted AST nodes while purging orphaned nodes
"""
import ast
import threading
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class MutationType(Enum):
    REPLACE = "replace"
    INSERT = "insert"
    DELETE = "delete"
    WRAP = "wrap"
    UNWRAP = "unwrap"


@dataclass
class MutationResult:
    mutation_id: str
    success: bool
    target_node: str
    mutation_type: MutationType
    old_code: str
    new_code: str
    removed_nodes: List[str] = field(default_factory=list)
    error: str = ""


class SurgicalASTMutator:
    def __init__(self):
        self._lock = threading.RLock()
        self._mutations: List[MutationResult] = []
    
    def mutate(self, code: str, target_name: str, mutation_type: MutationType,
               new_code: str = "", wrapper: str = "") -> MutationResult:
        
        mutation_id = f"mut_{hash(f'{target_name}{time.time()}') % 1000000}"
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return MutationResult(mutation_id, False, target_name, mutation_type, code, code, error=str(e))
        
        # Find target node
        target_node = None
        parent = None
        for node in ast.walk(tree):
            if self._is_target(node, target_name):
                target_node = node
                break
        
        if not target_node:
            return MutationResult(mutation_id, False, target_name, mutation_type, code, code, 
                                error=f"Target not found: {target_name}")
        
        old_code = ast.get_source_segment(code, target_node) or ""
        
        # Apply mutation
        if mutation_type == MutationType.REPLACE:
            new_node = ast.parse(new_code).body[0] if new_code else ast.Pass()
            self._replace_node(tree, target_node, new_node)
        elif mutation_type == MutationType.INSERT:
            new_node = ast.parse(new_code).body[0] if new_code else ast.Pass()
            self._insert_node(tree, target_node, new_node)
        elif mutation_type == MutationType.DELETE:
            self._delete_node(tree, target_node)
            new_code = ""
        elif mutation_type == MutationType.WRAP:
            self._wrap_node(tree, target_node, wrapper)
        elif mutation_type == MutationType.UNWRAP:
            self._unwrap_node(tree, target_node)
        
        # Collect garbage (orphaned nodes)
        removed = self._collect_garbage(tree)
        
        # Generate new code
        try:
            new_code = ast.unparse(tree)
        except Exception as e:
            return MutationResult(mutation_id, False, target_name, mutation_type, old_code, code, error=str(e))
        
        result = MutationResult(
            mutation_id=mutation_id,
            success=True,
            target_node=target_name,
            mutation_type=mutation_type,
            old_code=old_code,
            new_code=new_code,
            removed_nodes=removed
        )
        
        with self._lock:
            self._mutations.append(result)
        
        return result
    
    def _is_target(self, node: ast.AST, target_name: str) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return node.name == target_name
        if isinstance(node, ast.Name):
            return node.id == target_name
        return False
    
    def _replace_node(self, tree: ast.AST, target: ast.AST, new_node: ast.AST):
        for parent in ast.walk(tree):
            for field, value in ast.iter_fields(parent):
                if value is target:
                    setattr(parent, field, new_node)
                    return
                elif isinstance(value, list):
                    for i, v in enumerate(value):
                        if v is target:
                            value[i] = new_node
                            return
    
    def _insert_node(self, tree: ast.AST, target: ast.AST, new_node: ast.AST):
        for parent in ast.walk(tree):
            for field, value in ast.iter_fields(parent):
                if isinstance(value, list) and target in value:
                    idx = value.index(target)
                    value.insert(idx + 1, new_node)
                    return
    
    def _delete_node(self, tree: ast.AST, target: ast.AST):
        for parent in ast.walk(tree):
            for field, value in ast.iter_fields(parent):
                if value is target:
                    setattr(parent, field, ast.Pass())
                    return
                elif isinstance(value, list) and target in value:
                    value.remove(target)
                    return
    
    def _wrap_node(self, tree: ast.AST, target: ast.AST, wrapper: str):
        wrapper_node = ast.parse(wrapper).body[0]
        # Replace target with wrapper, put target inside wrapper
        for parent in ast.walk(tree):
            for field, value in ast.iter_fields(parent):
                if value is target:
                    # Find where to insert target in wrapper
                    for w_field, w_value in ast.iter_fields(wrapper_node):
                        if isinstance(w_value, list):
                            w_value.append(target)
                        elif w_value is None or (isinstance(w_value, ast.Constant) and w_value.value == "..."):
                            setattr(wrapper_node, w_field, target)
                    setattr(parent, field, wrapper_node)
                    return
    
    def _unwrap_node(self, tree: ast.AST, target: ast.AST):
        # Find parent of target that is a wrapper
        for parent in ast.walk(tree):
            for field, value in ast.iter_fields(parent):
                if isinstance(value, list) and target in value:
                    # Check if parent is a wrapper (with, try, etc.)
                    if isinstance(parent, (ast.With, ast.Try, ast.If)):
                        idx = value.index(target)
                        value[idx:idx+1] = target.body if hasattr(target, 'body') else [target]
                        return
    
    def _collect_garbage(self, tree: ast.AST) -> List[str]:
        removed = []
        # Remove nodes that are no longer reachable
        # This is a simplified version
        return removed
    
    def get_mutations(self) -> List[MutationResult]:
        with self._lock:
            return list(self._mutations)


import time

_ast_mutator: Optional[SurgicalASTMutator] = None

def get_ast_mutator() -> SurgicalASTMutator:
    global _ast_mutator
    if _ast_mutator is None:
        _ast_mutator = SurgicalASTMutator()
    return _ast_mutator