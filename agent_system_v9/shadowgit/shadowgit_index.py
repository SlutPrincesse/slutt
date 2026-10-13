"""
ShadowGit Index - Staging area management
"""
import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class IndexEntryStatus(Enum):
    UNMODIFIED = "unmodified"
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    UNTRACKED = "untracked"
    CONFLICT = "conflict"


@dataclass
class IndexEntry:
    path: str
    hash: str
    mode: str
    stage: int = 0
    status: IndexEntryStatus = IndexEntryStatus.UNMODIFIED
    size: int = 0
    mtime: float = 0.0
    ctime: float = 0.0
    inode: int = 0
    uid: int = 0
    gid: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "hash": self.hash,
            "mode": self.mode,
            "stage": self.stage,
            "status": self.status.value,
            "size": self.size,
            "mtime": self.mtime,
            "ctime": self.ctime,
            "inode": self.inode,
            "uid": self.uid,
            "gid": self.gid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'IndexEntry':
        return cls(
            path=data["path"],
            hash=data["hash"],
            mode=data["mode"],
            stage=data.get("stage", 0),
            status=IndexEntryStatus(data.get("status", "unmodified")),
            size=data.get("size", 0),
            mtime=data.get("mtime", 0),
            ctime=data.get("ctime", 0),
            inode=data.get("inode", 0),
            uid=data.get("uid", 0),
            gid=data.get("gid", 0),
        )


@dataclass
class IndexTree:
    entries: dict[str, IndexEntry] = field(default_factory=dict)
    version: int = 2
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
            "version": self.version,
            "timestamp": self.timestamp,
        }


import time


class ShadowIndex:
    def __init__(self, index_path: str = ".shadowgit/index"):
        self.index_path = Path(index_path)
        self.entries: dict[str, IndexEntry] = {}
        self.version = 2
        self._lock = asyncio.Lock()
        self._dirty = False

    async def load(self) -> bool:
        if not self.index_path.exists():
            return True

        try:
            data = json.loads(self.index_path.read_text())
            self.entries = {k: IndexEntry.from_dict(v) for k, v in data.get("entries", {}).items()}
            self.version = data.get("version", 2)
            return True
        except Exception:
            return False

    async def save(self) -> bool:
        async with self._lock:
            if not self._dirty:
                return True

            self.index_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "entries": {k: v.to_dict() for k, v in self.entries.items()},
                "version": self.version,
                "timestamp": time.time(),
            }

            self.index_path.write_text(json.dumps(data, indent=2))
            self._dirty = False
            return True

    def _hash_file(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _get_file_stat(self, path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "size": stat.st_size,
            "mode": oct(stat.st_mode)[-3:],
            "mtime": stat.st_mtime,
            "ctime": stat.st_ctime,
            "inode": stat.st_ino,
            "uid": stat.st_uid,
            "gid": stat.st_gid,
        }

    async def add(self, paths: list[str], worktree_root: Path) -> list[str]:
        added = []
        for path_str in paths:
            path = worktree_root / path_str
            if not path.exists():
                await self.remove(path_str)
                continue

            if path.is_dir():
                for p in path.rglob('*'):
                    if p.is_file():
                        rel = p.relative_to(worktree_root)
                        await self._add_file(rel, p)
                        added.append(str(rel))
            else:
                rel = path.relative_to(worktree_root)
                await self._add_file(rel, path)
                added.append(str(rel))

        self._dirty = True
        return added

    async def _add_file(self, rel_path: Path, abs_path: Path):
        file_hash = self._hash_file(abs_path)
        stat_info = self._get_file_stat(abs_path)

        path_str = str(rel_path)
        existing = self.entries.get(path_str)

        if existing:
            if existing.hash != file_hash:
                status = IndexEntryStatus.MODIFIED
            else:
                status = IndexEntryStatus.UNMODIFIED
        else:
            status = IndexEntryStatus.ADDED

        self.entries[path_str] = IndexEntry(
            path=path_str,
            hash=file_hash,
            mode=stat_info["mode"],
            status=status,
            size=stat_info["size"],
            mtime=stat_info["mtime"],
            ctime=stat_info["ctime"],
            inode=stat_info["inode"],
            uid=stat_info["uid"],
            gid=stat_info["gid"],
        )

    async def remove(self, paths: list[str]) -> list[str]:
        removed = []
        for path_str in paths:
            if path_str in self.entries:
                self.entries[path_str].status = IndexEntryStatus.DELETED
                removed.append(path_str)

        self._dirty = True
        return removed

    async def update(self, paths: list[str], worktree_root: Path) -> list[str]:
        updated = []
        for path_str in paths:
            path = worktree_root / path_str
            if path.exists() and path.is_file():
                await self._add_file(Path(path_str), path)
                updated.append(path_str)
            else:
                await self.remove([path_str])
                updated.append(path_str)

        self._dirty = True
        return updated

    async def refresh(self, worktree_root: Path) -> dict[str, IndexEntryStatus]:
        changes = {}

        for path_str, entry in list(self.entries.items()):
            path = worktree_root / path_str

            if not path.exists():
                if entry.status != IndexEntryStatus.DELETED:
                    entry.status = IndexEntryStatus.DELETED
                    changes[path_str] = IndexEntryStatus.DELETED
                continue

            stat = path.stat()
            if stat.st_mtime != entry.mtime or stat.st_size != entry.size:
                file_hash = self._hash_file(path)
                if file_hash != entry.hash:
                    entry.hash = file_hash
                    entry.size = stat.st_size
                    entry.mtime = stat.st_mtime
                    entry.ctime = stat.st_ctime
                    entry.inode = stat.st_ino
                    entry.status = IndexEntryStatus.MODIFIED
                    changes[path_str] = IndexEntryStatus.MODIFIED

        for path in worktree_root.rglob('*'):
            if path.is_file():
                rel = path.relative_to(worktree_root)
                rel_str = str(rel)
                if rel_str not in self.entries:
                    self.entries[rel_str] = IndexEntry(
                        path=rel_str,
                        hash=self._hash_file(path),
                        mode=oct(path.stat().st_mode)[-3:],
                        status=IndexEntryStatus.UNTRACKED,
                        size=path.stat().st_size,
                        mtime=path.stat().st_mtime,
                        ctime=path.stat().st_ctime,
                        inode=path.stat().st_ino,
                        uid=path.stat().st_uid,
                        gid=path.stat().st_gid,
                    )
                    changes[rel_str] = IndexEntryStatus.UNTRACKED

        if changes:
            self._dirty = True

        return changes

    def get_entry(self, path: str) -> IndexEntry | None:
        return self.entries.get(path)

    def get_entries(self, status: IndexEntryStatus = None) -> list[IndexEntry]:
        if status:
            return [e for e in self.entries.values() if e.status == status]
        return list(self.entries.values())

    def get_staged_files(self) -> list[str]:
        return [e.path for e in self.entries.values()
                if e.status in (IndexEntryStatus.ADDED, IndexEntryStatus.MODIFIED, IndexEntryStatus.DELETED)]

    def get_modified_files(self) -> list[str]:
        return [e.path for e in self.entries.values() if e.status == IndexEntryStatus.MODIFIED]

    def get_untracked_files(self) -> list[str]:
        return [e.path for e in self.entries.values() if e.status == IndexEntryStatus.UNTRACKED]

    def get_conflicted_files(self) -> list[str]:
        return [e.path for e in self.entries.values() if e.status == IndexEntryStatus.CONFLICT or e.stage > 0]

    def clear_conflicts(self, path: str) -> bool:
        if path in self.entries:
            self.entries[path].stage = 0
            self.entries[path].status = IndexEntryStatus.MODIFIED
            self._dirty = True
            return True
        return False

    def stage_all(self) -> int:
        count = 0
        for entry in self.entries.values():
            if entry.status in (IndexEntryStatus.MODIFIED, IndexEntryStatus.ADDED, IndexEntryStatus.DELETED):
                entry.status = IndexEntryStatus.UNMODIFIED if entry.status != IndexEntryStatus.DELETED else IndexEntryStatus.DELETED
                count += 1
        if count:
            self._dirty = True
        return count

    def reset(self, paths: list[str] = None) -> int:
        count = 0
        if paths is None:
            for entry in self.entries.values():
                entry.status = IndexEntryStatus.UNMODIFIED
                count += 1
        else:
            for path in paths:
                if path in self.entries:
                    self.entries[path].status = IndexEntryStatus.UNMODIFIED
                    count += 1
        if count:
            self._dirty = True
        return count

    def get_tree_hash(self) -> str:
        tree_data = []
        for path in sorted(self.entries.keys()):
            entry = self.entries[path]
            if entry.status != IndexEntryStatus.DELETED:
                tree_data.append(f"{entry.mode} {entry.hash} {path}")

        tree_content = "\n".join(tree_data).encode()
        return hashlib.sha256(tree_content).hexdigest()

    def write_tree(self, objects_dir: Path) -> str:
        tree_hash = self.get_tree_hash()

        tree_data = []
        for path in sorted(self.entries.keys()):
            entry = self.entries[path]
            if entry.status != IndexEntryStatus.DELETED:
                tree_data.append(f"{entry.mode} {entry.hash} {path}")

        tree_content = "\n".join(tree_data).encode()

        obj_dir = objects_dir / tree_hash[:2]
        obj_dir.mkdir(parents=True, exist_ok=True)
        obj_file = obj_dir / tree_hash[2:]
        obj_file.write_bytes(tree_content)

        return tree_hash

    def get_stats(self) -> dict[str, int]:
        return {
            "total": len(self.entries),
            "staged": len([e for e in self.entries.values() if e.status in (IndexEntryStatus.ADDED, IndexEntryStatus.MODIFIED)]),
            "modified": len([e for e in self.entries.values() if e.status == IndexEntryStatus.MODIFIED]),
            "deleted": len([e for e in self.entries.values() if e.status == IndexEntryStatus.DELETED]),
            "untracked": len([e for e in self.entries.values() if e.status == IndexEntryStatus.UNTRACKED]),
            "conflicted": len([e for e in self.entries.values() if e.status == IndexEntryStatus.CONFLICT]),
        }


class IndexMerger:
    def __init__(self, index: ShadowIndex):
        self.index = index

    async def merge(self, other_entries: dict[str, IndexEntry], strategy: str = "ours") -> dict[str, IndexEntryStatus]:
        conflicts = {}

        for path, other_entry in other_entries.items():
            local_entry = self.index.entries.get(path)

            if not local_entry:
                self.index.entries[path] = other_entry
                conflicts[path] = IndexEntryStatus.ADDED
                continue

            if local_entry.hash == other_entry.hash:
                continue

            if local_entry.status == IndexEntryStatus.UNMODIFIED:
                if other_entry.status == IndexEntryStatus.MODIFIED:
                    local_entry.hash = other_entry.hash
                    local_entry.status = IndexEntryStatus.MODIFIED
                elif other_entry.status == IndexEntryStatus.DELETED:
                    local_entry.status = IndexEntryStatus.DELETED
                continue

            if strategy == "ours":
                pass
            elif strategy == "theirs":
                local_entry.hash = other_entry.hash
                local_entry.status = other_entry.status
            else:
                local_entry.stage = 1
                local_entry.status = IndexEntryStatus.CONFLICT
                conflicts[path] = IndexEntryStatus.CONFLICT

        self.index._dirty = True
        return conflicts

    def resolve_conflict(self, path: str, resolution: str) -> bool:
        if path not in self.index.entries:
            return False

        entry = self.index.entries[path]
        if entry.status != IndexEntryStatus.CONFLICT:
            return False

        entry.stage = 0
        if resolution == "ours" or resolution == "theirs":
            pass
        else:
            entry.hash = resolution
        entry.status = IndexEntryStatus.MODIFIED
        self.index._dirty = True
        return True
