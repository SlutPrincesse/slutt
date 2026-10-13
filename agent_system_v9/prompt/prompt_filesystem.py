"""
Prompt File-System Layer - Virtualized filesystem mapping system prompts and personas to virtual file descriptors
"""
import os
import json
import hashlib
import threading
import time
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import OrderedDict


class PromptType(Enum):
    SYSTEM = "system"
    PERSONA = "persona"
    TASK = "task"
    TEMPLATE = "template"
    SNIPPET = "snippet"
    MEMORY = "memory"


@dataclass
class PromptFile:
    fd: int
    path: str
    prompt_type: PromptType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    size: int = 0
    checksum: str = ""


class PromptFileSystem:
    def __init__(self, root_path: Optional[str] = None, max_cache_size: int = 1000):
        self.root_path = Path(root_path) if root_path else Path.home() / ".agent_v9" / "prompts"
        self.root_path.mkdir(parents=True, exist_ok=True)
        
        self._fd_counter = 0
        self._open_files: Dict[int, PromptFile] = {}
        self._path_to_fd: Dict[str, int] = {}
        self._type_index: Dict[PromptType, List[int]] = {t: [] for t in PromptType}
        self._tag_index: Dict[str, List[int]] = {}
        self._cache: OrderedDict[str, PromptFile] = OrderedDict()
        self._max_cache_size = max_cache_size
        self._lock = threading.RLock()
        self._watchers: Dict[str, List[Callable]] = {}
        
        self._load_existing()
    
    def _load_existing(self):
        for prompt_type in PromptType:
            type_dir = self.root_path / prompt_type.value
            if type_dir.exists():
                for file_path in type_dir.rglob("*.prompt"):
                    try:
                        self._load_prompt_file(file_path, prompt_type)
                    except Exception:
                        pass
    
    def _load_prompt_file(self, file_path: Path, prompt_type: PromptType) -> PromptFile:
        content = file_path.read_text(encoding='utf-8')
        checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        rel_path = file_path.relative_to(self.root_path)
        fd = self._allocate_fd()
        
        prompt_file = PromptFile(
            fd=fd,
            path=str(rel_path),
            prompt_type=prompt_type,
            content=content,
            size=len(content),
            checksum=checksum
        )
        
        # Parse metadata from frontmatter if present
        if content.startswith('---'):
            try:
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    import yaml
                    meta = yaml.safe_load(parts[1])
                    if meta:
                        prompt_file.metadata = meta.get('metadata', {})
                        prompt_file.tags = meta.get('tags', [])
            except Exception:
                pass
        
        with self._lock:
            self._open_files[fd] = prompt_file
            self._path_to_fd[str(rel_path)] = fd
            self._type_index[prompt_type].append(fd)
            for tag in prompt_file.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = []
                self._tag_index[tag].append(fd)
        
        return prompt_file
    
    def _allocate_fd(self) -> int:
        self._fd_counter += 1
        return self._fd_counter
    
    def create(self, path: str, prompt_type: PromptType, content: str,
               metadata: Dict[str, Any] = None, tags: List[str] = None) -> PromptFile:
        full_path = self.root_path / prompt_type.value / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Add frontmatter
        frontmatter = {}
        if metadata:
            frontmatter['metadata'] = metadata
        if tags:
            frontmatter['tags'] = tags
        
        if frontmatter:
            import yaml
            yaml_str = yaml.dump(frontmatter, default_flow_style=False)
            content = f"---\n{yaml_str}---\n{content}"
        
        full_path.write_text(content, encoding='utf-8')
        
        return self._load_prompt_file(full_path, prompt_type)
    
    def open(self, path: str) -> Optional[int]:
        with self._lock:
            fd = self._path_to_fd.get(path)
            if fd is not None:
                self._open_files[fd].access_count += 1
                return fd
        
        # Try to load from disk
        full_path = self.root_path / path
        if full_path.exists():
            # Determine type from path
            prompt_type = PromptType.SYSTEM
            for pt in PromptType:
                if str(full_path).startswith(str(self.root_path / pt.value)):
                    prompt_type = pt
                    break
            
            prompt_file = self._load_prompt_file(full_path, prompt_type)
            return prompt_file.fd
        
        return None
    
    def read(self, fd: int) -> Optional[str]:
        with self._lock:
            prompt_file = self._open_files.get(fd)
            if prompt_file:
                prompt_file.access_count += 1
                return prompt_file.content
        return None
    
    def write(self, fd: int, content: str) -> bool:
        with self._lock:
            prompt_file = self._open_files.get(fd)
            if not prompt_file:
                return False
            
            full_path = self.root_path / prompt_file.path
            full_path.write_text(content, encoding='utf-8')
            
            prompt_file.content = content
            prompt_file.size = len(content)
            prompt_file.checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
            prompt_file.updated_at = time.time()
            
            self._notify_watchers(prompt_file.path, "modified")
            return True
    
    def close(self, fd: int) -> bool:
        with self._lock:
            if fd in self._open_files:
                del self._open_files[fd]
                # Remove from indexes
                for idx_list in self._type_index.values():
                    if fd in idx_list:
                        idx_list.remove(fd)
                for idx_list in self._tag_index.values():
                    if fd in idx_list:
                        idx_list.remove(fd)
                # Find and remove from path index
                path_to_remove = None
                for path, ffd in self._path_to_fd.items():
                    if ffd == fd:
                        path_to_remove = path
                        break
                if path_to_remove:
                    del self._path_to_fd[path_to_remove]
                return True
        return False
    
    def delete(self, path: str) -> bool:
        fd = self._path_to_fd.get(path)
        if fd:
            self.close(fd)
        
        full_path = self.root_path / path
        if full_path.exists():
            full_path.unlink()
            self._notify_watchers(path, "deleted")
            return True
        return False
    
    def list(self, prompt_type: Optional[PromptType] = None, 
             tags: Optional[List[str]] = None) -> List[PromptFile]:
        with self._lock:
            if prompt_type:
                fds = self._type_index.get(prompt_type, [])
            elif tags:
                fds = set()
                for tag in tags:
                    fds.update(self._tag_index.get(tag, []))
                fds = list(fds)
            else:
                fds = list(self._open_files.keys())
            
            return [self._open_files[fd] for fd in fds if fd in self._open_files]
    
    def search(self, query: str, prompt_type: Optional[PromptType] = None,
               tags: Optional[List[str]] = None, limit: int = 50) -> List[PromptFile]:
        results = []
        query_lower = query.lower()
        
        candidates = self.list(prompt_type, tags)
        
        for pf in candidates:
            score = 0
            if query_lower in pf.content.lower():
                score += 10
            if query_lower in pf.path.lower():
                score += 5
            for tag in pf.tags:
                if query_lower in tag.lower():
                    score += 3
            if score > 0:
                results.append((score, pf))
        
        results.sort(key=lambda x: -x[0])
        return [pf for _, pf in results[:limit]]
    
    def get_by_fd(self, fd: int) -> Optional[PromptFile]:
        with self._lock:
            return self._open_files.get(fd)
    
    def get_by_path(self, path: str) -> Optional[PromptFile]:
        with self._lock:
            fd = self._path_to_fd.get(path)
            if fd:
                return self._open_files.get(fd)
        return None
    
    def register_watcher(self, path_pattern: str, callback: Callable):
        if path_pattern not in self._watchers:
            self._watchers[path_pattern] = []
        self._watchers[path_pattern].append(callback)
    
    def _notify_watchers(self, path: str, event: str):
        import fnmatch
        for pattern, callbacks in self._watchers.items():
            if fnmatch.fnmatch(path, pattern):
                for cb in callbacks:
                    try:
                        cb(path, event)
                    except Exception:
                        pass
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "open_files": len(self._open_files),
                "cached_files": len(self._cache),
                "by_type": {pt.value: len(fds) for pt, fds in self._type_index.items()},
                "by_tag": {tag: len(fds) for tag, fds in self._tag_index.items()},
                "total_size": sum(pf.size for pf in self._open_files.values()),
            }


_prompt_fs: Optional[PromptFileSystem] = None

def get_prompt_filesystem() -> PromptFileSystem:
    global _prompt_fs
    if _prompt_fs is None:
        _prompt_fs = PromptFileSystem()
    return _prompt_fs