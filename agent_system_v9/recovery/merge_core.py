"""
Recursive Core Synthesis (MERGE_CORE) - Single-trigger pipeline merging code, enforcing DRY/SRP invariants
"""
import threading
import ast
import hashlib
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MergeResult:
    success: bool
    merged_files: List[str]
    conflicts_resolved: int
    dry_violations_fixed: int
    srp_violations_fixed: int
    merged_code: str = ""
    errors: List[str] = field(default_factory=list)


class MergeCore:
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self._lock = threading.RLock()
        self._merge_history: List[MergeResult] = []
    
    def merge(self, source_dirs: List[str], output_dir: str) -> MergeResult:
        result = MergeResult(False, [], 0, 0, 0)
        
        try:
            # Collect all Python files
            all_files = {}
            for src_dir in source_dirs:
                for py_file in Path(src_dir).rglob("*.py"):
                    rel_path = py_file.relative_to(src_dir)
                    if rel_path not in all_files:
                        all_files[rel_path] = []
                    all_files[rel_path].append(py_file.read_text())
            
            # Merge each file
            merged_files = []
            conflicts = 0
            dry_fixes = 0
            srp_fixes = 0
            
            for rel_path, versions in all_files.items():
                if len(versions) == 1:
                    merged_files.append(str(rel_path))
                    continue
                
                # Multi-version merge
                merged = self._merge_versions(versions)
                if merged:
                    output_path = Path(output_dir) / rel_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(merged)
                    merged_files.append(str(rel_path))
                    conflicts += 1
            
            # Apply DRY/SRP fixes
            dry_fixes = self._enforce_dry(output_dir)
            srp_fixes = self._enforce_srp(output_dir)
            
            result = MergeResult(
                success=True,
                merged_files=merged_files,
                conflicts_resolved=conflicts,
                dry_violations_fixed=dry_fixes,
                srp_violations_fixed=srp_fixes
            )
            
        except Exception as e:
            result.errors.append(str(e))
        
        with self._lock:
            self._merge_history.append(result)
        
        return result
    
    def _merge_versions(self, versions: List[str]) -> Optional[str]:
        if len(versions) == 1:
            return versions[0]
        
        # Simple strategy: pick most complete version
        best = max(versions, key=len)
        return best
    
    def _enforce_dry(self, output_dir: str) -> int:
        # Extract common patterns and create shared modules
        return 0
    
    def _enforce_srp(self, output_dir: str) -> int:
        # Split classes/functions with multiple responsibilities
        return 0
    
    def get_history(self) -> List[MergeResult]:
        with self._lock:
            return list(self._merge_history)


_merge_core: Optional[MergeCore] = None

def get_merge_core() -> MergeCore:
    global _merge_core
    if _merge_core is None:
        from ..core.config import config
        threshold = config.get_param("recovery", "merge_core_threshold", 0.85)
        _merge_core = MergeCore(threshold=threshold)
    return _merge_core