"""
ShadowGit Core - Git operations for shadow repositories with LMDB persistence
"""
import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ShadowGitStatus(Enum):
    CLEAN = "clean"
    MODIFIED = "modified"
    STAGED = "staged"
    CONFLICT = "conflict"
    UNTRACKED = "untracked"


@dataclass
class ShadowFile:
    path: str
    hash: str
    size: int
    mode: str
    stage: int = 0
    status: ShadowGitStatus = ShadowGitStatus.CLEAN

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "hash": self.hash,
            "size": self.size,
            "mode": self.mode,
            "stage": self.stage,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ShadowFile':
        return cls(
            path=data["path"],
            hash=data["hash"],
            size=data["size"],
            mode=data["mode"],
            stage=data.get("stage", 0),
            status=ShadowGitStatus(data.get("status", "clean")),
        )


@dataclass
class ShadowCommit:
    commit_id: str
    message: str
    author: str
    timestamp: float
    parent_ids: list[str] = field(default_factory=list)
    tree_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit_id": self.commit_id,
            "message": self.message,
            "author": self.author,
            "timestamp": self.timestamp,
            "parent_ids": self.parent_ids,
            "tree_hash": self.tree_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ShadowCommit':
        return cls(
            commit_id=data["commit_id"],
            message=data["message"],
            author=data["author"],
            timestamp=data["timestamp"],
            parent_ids=data.get("parent_ids", []),
            tree_hash=data.get("tree_hash", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ShadowBranch:
    name: str
    commit_id: str
    is_remote: bool = False
    upstream: str = ""


@dataclass
class ShadowDiff:
    old_path: str
    new_path: str
    old_hash: str
    new_hash: str
    change_type: str
    diff_content: str = ""


class ShadowGit:
    def __init__(
        self,
        repo_path: str = ".shadowgit",
        use_lmdb: bool = False,
        lmdb_path: str = None,
        lmdb_map_size: int = 1_000_000_000,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.objects_path = self.repo_path / "objects"
        self.refs_path = self.repo_path / "refs"
        self.index_path = self.repo_path / "index"
        self.head_path = self.repo_path / "HEAD"
        self.config_path = self.repo_path / "config"

        self._initialized = False
        self._index: dict[str, ShadowFile] = {}
        self._branches: dict[str, ShadowBranch] = {}
        self._commits: dict[str, ShadowCommit] = {}
        self._current_branch = "main"

        # LMDB persistence
        self._use_lmdb = use_lmdb
        self._lmdb_path = lmdb_path or str(self.repo_path / "lmdb")
        self._lmdb_map_size = lmdb_map_size
        self._lmdb_env = None
        self._lmdb_dbs: dict[str, Any] = {}

    async def init(self, bare: bool = False) -> bool:
        if self._use_lmdb:
            return await self._init_lmdb()

        if self.repo_path.exists():
            return await self._load()

        self.repo_path.mkdir(parents=True, exist_ok=True)
        self.objects_path.mkdir(parents=True, exist_ok=True)
        self.refs_path.mkdir(parents=True, exist_ok=True)
        (self.refs_path / "heads").mkdir(parents=True, exist_ok=True)
        (self.refs_path / "tags").mkdir(parents=True, exist_ok=True)

        self._index = {}
        self._branches = {"main": ShadowBranch(name="main", commit_id="")}

        await self._save_index()
        await self._save_refs()

        self._initialized = True
        return True

    async def _init_lmdb(self) -> bool:
        """Initialize with LMDB backend."""
        try:
            import lmdb
        except ImportError:
            raise RuntimeError("LMDB not available. Install with: pip install lmdb")

        import os
        os.makedirs(self._lmdb_path, exist_ok=True)

        self._lmdb_env = lmdb.open(
            self._lmdb_path,
            map_size=self._lmdb_map_size,
            max_dbs=20
        )

        # Create databases for different data types
        with self._lmdb_env.begin(write=True) as txn:
            self._lmdb_dbs["index"] = self._lmdb_env.open_db(b"index", txn=txn, create=True)
            self._lmdb_dbs["branches"] = self._lmdb_env.open_db(b"branches", txn=txn, create=True)
            self._lmdb_dbs["commits"] = self._lmdb_env.open_db(b"commits", txn=txn, create=True)
            self._lmdb_dbs["objects"] = self._lmdb_env.open_db(b"objects", txn=txn, create=True)
            self._lmdb_dbs["refs"] = self._lmdb_env.open_db(b"refs", txn=txn, create=True)
            self._lmdb_dbs["head"] = self._lmdb_env.open_db(b"head", txn=txn, create=True)

        # Load existing data if any
        await self._load_lmdb()

        self._initialized = True
        return True

    async def _load_lmdb(self):
        """Load data from LMDB."""
        if not self._lmdb_env:
            return

        # Load index
        with self._lmdb_env.begin(db=self._lmdb_dbs["index"]) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                file_data = json.loads(value.decode())
                self._index[key.decode()] = ShadowFile.from_dict(file_data)

        # Load branches
        with self._lmdb_env.begin(db=self._lmdb_dbs["branches"]) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                branch_data = json.loads(value.decode())
                self._branches[key.decode()] = ShadowBranch(**branch_data)

        # Load commits
        with self._lmdb_env.begin(db=self._lmdb_dbs["commits"]) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                commit_data = json.loads(value.decode())
                self._commits[key.decode()] = ShadowCommit.from_dict(commit_data)

        # Load HEAD
        with self._lmdb_env.begin(db=self._lmdb_dbs["head"]) as txn:
            head_data = txn.get(b"current")
            if head_data:
                self._current_branch = head_data.decode()
            else:
                self._current_branch = "main"

    def _get_lmdb_db(self, name: str):
        """Get LMDB database by name."""
        return self._lmdb_dbs.get(name)

    def _save_lmdb_index(self):
        """Save index to LMDB."""
        if not self._lmdb_env:
            return
        with self._lmdb_env.begin(db=self._lmdb_dbs["index"], write=True) as txn:
            # Clear existing
            cursor = txn.cursor()
            for key, _ in cursor:
                txn.delete(key)
            # Write new
            for path, file_info in self._index.items():
                txn.put(path.encode(), json.dumps(file_info.to_dict()).encode())

    def _save_lmdb_refs(self):
        """Save branches/refs to LMDB."""
        if not self._lmdb_env:
            return
        with self._lmdb_env.begin(db=self._lmdb_dbs["branches"], write=True) as txn:
            for name, branch in self._branches.items():
                txn.put(name.encode(), json.dumps({
                    "name": branch.name,
                    "commit_id": branch.commit_id,
                    "is_remote": branch.is_remote,
                    "upstream": branch.upstream,
                }).encode())
        with self._lmdb_env.begin(db=self._lmdb_dbs["head"], write=True) as txn:
            txn.put(b"current", self._current_branch.encode())

    def _save_lmdb_commit(self, commit: ShadowCommit):
        """Save commit to LMDB."""
        if not self._lmdb_env:
            return
        with self._lmdb_env.begin(db=self._lmdb_dbs["commits"], write=True) as txn:
            txn.put(commit.commit_id.encode(), json.dumps(commit.to_dict()).encode())

    def _save_lmdb_object(self, obj_hash: str, content: bytes):
        """Save object to LMDB."""
        if not self._lmdb_env:
            return
        with self._lmdb_env.begin(db=self._lmdb_dbs["objects"], write=True) as txn:
            txn.put(obj_hash.encode(), content)

    def _get_lmdb_object(self, obj_hash: str) -> bytes | None:
        """Get object from LMDB."""
        if not self._lmdb_env:
            return None
        with self._lmdb_env.begin(db=self._lmdb_dbs["objects"]) as txn:
            return txn.get(obj_hash.encode())

    async def close(self):
        """Close LMDB environment."""
        if self._lmdb_env:
            self._lmdb_env.close()
            self._lmdb_env = None

    async def _load(self) -> bool:
        if self._use_lmdb:
            return True  # Already loaded in _init_lmdb

        if not self.repo_path.exists():
            return False

        if self.index_path.exists():
            data = json.loads(self.index_path.read_text())
            self._index = {k: ShadowFile.from_dict(v) for k, v in data.items()}

        if self.refs_path.exists():
            for ref_file in (self.refs_path / "heads").glob("*"):
                if ref_file.is_file():
                    commit_id = ref_file.read_text().strip()
                    self._branches[ref_file.name] = ShadowBranch(
                        name=ref_file.name, commit_id=commit_id
                    )

        self._initialized = True
        return True

    async def _save_index(self):
        if self._use_lmdb:
            self._save_lmdb_index()
        else:
            data = {k: v.to_dict() for k, v in self._index.items()}
            self.index_path.write_text(json.dumps(data, indent=2))

    async def _save_refs(self):
        if self._use_lmdb:
            self._save_lmdb_refs()
        else:
            for name, branch in self._branches.items():
                ref_file = self.refs_path / "heads" / name
                ref_file.write_text(branch.commit_id)

    def _hash_content(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _hash_file(self, file_path: Path) -> str:
        return self._hash_content(file_path.read_bytes())

    async def add(self, paths: list[str]) -> list[str]:
        added = []
        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                continue

            if path.is_dir():
                for p in path.rglob('*'):
                    if p.is_file():
                        await self._add_file(p)
                        added.append(str(p))
            else:
                await self._add_file(path)
                added.append(str(path))

        await self._save_index()
        return added

    async def _add_file(self, path: Path):
        rel_path = path.relative_to(self.repo_path.parent) if path.is_relative_to(self.repo_path.parent) else path
        content = path.read_bytes()
        file_hash = self._hash_content(content)

        if self._use_lmdb:
            self._save_lmdb_object(file_hash, content)
        else:
            obj_dir = self.objects_path / file_hash[:2]
            obj_dir.mkdir(exist_ok=True)
            obj_file = obj_dir / file_hash[2:]
            obj_file.write_bytes(content)

        stat = path.stat()
        self._index[str(rel_path)] = ShadowFile(
            path=str(rel_path),
            hash=file_hash,
            size=stat.st_size,
            mode=oct(stat.st_mode)[-3:],
            status=ShadowGitStatus.STAGED,
        )

    async def commit(self, message: str, author: str = "ShadowGit") -> str:
        tree_hash = await self._write_tree()

        parent_ids = []
        head_commit = await self._get_head_commit()
        if head_commit:
            parent_ids.append(head_commit.commit_id)

        commit = ShadowCommit(
            commit_id=hashlib.sha256(f"{message}:{time.time()}:{tree_hash}".encode()).hexdigest()[:12],
            message=message,
            author=author,
            timestamp=time.time(),
            parent_ids=parent_ids,
            tree_hash=tree_hash,
        )

        commit_data = json.dumps(commit.to_dict(), indent=2)
        commit_hash = self._hash_content(commit_data.encode())

        if self._use_lmdb:
            self._save_lmdb_object(commit_hash, commit_data.encode())
            self._save_lmdb_commit(commit)
        else:
            obj_dir = self.objects_path / commit_hash[:2]
            obj_dir.mkdir(exist_ok=True)
            obj_file = obj_dir / commit_hash[2:]
            obj_file.write_text(commit_data)

        self._commits[commit.commit_id] = commit

        current_branch = await self._get_current_branch()
        if current_branch and current_branch in self._branches:
            self._branches[current_branch].commit_id = commit.commit_id
            await self._save_refs()

        for path in self._index:
            self._index[path].status = ShadowGitStatus.CLEAN
        await self._save_index()

        return commit.commit_id

    async def _write_tree(self) -> str:
        tree_entries = []
        for path, file_info in sorted(self._index.items()):
            tree_entries.append(f"{file_info.mode} {file_info.hash} {path}")

        tree_content = "\n".join(tree_entries).encode()
        return self._hash_content(tree_content)

    async def _get_head_commit(self) -> ShadowCommit | None:
        current_branch = await self._get_current_branch()
        if current_branch and current_branch in self._branches:
            commit_id = self._branches[current_branch].commit_id
            return self._commits.get(commit_id)
        return None

    async def _get_current_branch(self) -> str | None:
        if self._use_lmdb:
            return self._current_branch

        if self.head_path.exists():
            content = self.head_path.read_text().strip()
            if content.startswith("ref: refs/heads/"):
                return content[16:]
        return "main"

    async def checkout(self, target: str, create: bool = False) -> bool:
        if target in self._branches:
            branch = self._branches[target]
            await self._checkout_commit(branch.commit_id)
            self._current_branch = target
            if not self._use_lmdb:
                self.head_path.write_text(f"ref: refs/heads/{target}")
            else:
                with self._lmdb_env.begin(db=self._lmdb_dbs["head"], write=True) as txn:
                    txn.put(b"current", target.encode())
            return True

        if create:
            current_branch = await self._get_current_branch()
            if current_branch and current_branch in self._branches:
                commit_id = self._branches[current_branch].commit_id
                self._branches[target] = ShadowBranch(name=target, commit_id=commit_id)
                await self._save_refs()
                self._current_branch = target
                if not self._use_lmdb:
                    self.head_path.write_text(f"ref: refs/heads/{target}")
                else:
                    with self._lmdb_env.begin(db=self._lmdb_dbs["head"], write=True) as txn:
                        txn.put(b"current", target.encode())
                return True

        return False

    async def _checkout_commit(self, commit_id: str):
        commit = self._commits.get(commit_id)
        if not commit:
            if self._use_lmdb:
                commit_data = self._get_lmdb_object(commit_id)
                if commit_data:
                    commit = ShadowCommit.from_dict(json.loads(commit_data.decode()))
                    self._commits[commit_id] = commit
            else:
                obj_dir = self.objects_path / commit_id[:2]
                obj_file = obj_dir / commit_id[2:]
                if obj_file.exists():
                    data = json.loads(obj_file.read_text())
                    commit = ShadowCommit(**data)
                    self._commits[commit_id] = commit

        if commit and commit.tree_hash:
            await self._restore_tree(commit.tree_hash)

    async def _restore_tree(self, tree_hash: str):
        tree_content = None
        if self._use_lmdb:
            tree_data = self._get_lmdb_object(tree_hash)
            if tree_data:
                tree_content = tree_data.decode()
        else:
            obj_dir = self.objects_path / tree_hash[:2]
            obj_file = obj_dir / tree_hash[2:]
            if not obj_file.exists():
                return
            tree_content = obj_file.read_text()

        if not tree_content:
            return

        self._index = {}

        for line in tree_content.strip().split('\n'):
            if not line:
                continue
            parts = line.split(' ', 2)
            if len(parts) == 3:
                mode, file_hash, path = parts
                content = None
                if self._use_lmdb:
                    obj_data = self._get_lmdb_object(file_hash)
                    if obj_data:
                        content = obj_data
                else:
                    obj_file_path = self.objects_path / file_hash[:2] / file_hash[2:]
                    if obj_file_path.exists():
                        content = obj_file_path.read_bytes()

                if content is not None:
                    dest = self.repo_path.parent / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(content)

                    stat = dest.stat()
                    self._index[path] = ShadowFile(
                        path=path,
                        hash=file_hash,
                        size=stat.st_size,
                        mode=mode,
                        status=ShadowGitStatus.CLEAN,
                    )

        await self._save_index()

    async def status(self) -> dict[str, ShadowGitStatus]:
        result = {}

        for path_str, file_info in self._index.items():
            path = self.repo_path.parent / path_str
            if path.exists():
                current_hash = self._hash_file(path)
                if current_hash != file_info.hash:
                    result[path_str] = ShadowGitStatus.MODIFIED
                else:
                    result[path_str] = file_info.status
            else:
                result[path_str] = ShadowGitStatus.UNTRACKED

        for path in (self.repo_path.parent).rglob('*'):
            if path.is_file():
                rel = path.relative_to(self.repo_path.parent)
                rel_str = str(rel)
                if rel_str not in self._index and not self._is_ignored(rel_str):
                    result[rel_str] = ShadowGitStatus.UNTRACKED

        return result

    def _is_ignored(self, path: str) -> bool:
        ignore_patterns = ['.shadowgit', '__pycache__', '.git', 'node_modules', '.venv']
        return any(pattern in path for pattern in ignore_patterns)

    async def diff(self, path: str = None) -> list[ShadowDiff]:
        diffs = []

        paths_to_check = [path] if path else list(self._index.keys())

        for path_str in paths_to_check:
            file_info = self._index.get(path_str)
            if not file_info:
                continue

            full_path = self.repo_path.parent / path_str
            if not full_path.exists():
                diffs.append(ShadowDiff(
                    old_path=path_str,
                    new_path=path_str,
                    old_hash=file_info.hash,
                    new_hash="",
                    change_type="deleted",
                ))
                continue

            current_hash = self._hash_file(full_path)
            if current_hash != file_info.hash:
                old_content = self._get_object_content(file_info.hash)
                new_content = full_path.read_text()

                diff_content = self._generate_diff(old_content, new_content, path_str)
                diffs.append(ShadowDiff(
                    old_path=path_str,
                    new_path=path_str,
                    old_hash=file_info.hash,
                    new_hash=current_hash,
                    change_type="modified",
                    diff_content=diff_content,
                ))

        return diffs

    def _get_object_content(self, obj_hash: str) -> str:
        if self._use_lmdb:
            obj_data = self._get_lmdb_object(obj_hash)
            if obj_data:
                return obj_data.decode(errors='ignore')
            return ""

        obj_file = self.objects_path / obj_hash[:2] / obj_hash[2:]
        if obj_file.exists():
            return obj_file.read_text(errors='ignore')
        return ""

    def _generate_diff(self, old: str, new: str, path: str) -> str:
        import difflib
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}")
        return ''.join(diff)

    async def log(self, limit: int = 10) -> list[ShadowCommit]:
        commits = []
        current_branch = await self._get_current_branch()
        if current_branch and current_branch in self._branches:
            commit_id = self._branches[current_branch].commit_id
            while commit_id and len(commits) < limit:
                commit = self._commits.get(commit_id)
                if not commit:
                    if self._use_lmdb:
                        commit_data = self._get_lmdb_object(commit_id)
                        if commit_data:
                            commit = ShadowCommit.from_dict(json.loads(commit_data.decode()))
                            self._commits[commit_id] = commit
                    else:
                        obj_dir = self.objects_path / commit_id[:2]
                        obj_file = obj_dir / commit_id[2:]
                        if obj_file.exists():
                            data = json.loads(obj_file.read_text())
                            commit = ShadowCommit(**data)
                            self._commits[commit_id] = commit

                if commit:
                    commits.append(commit)
                    commit_id = commit.parent_ids[0] if commit.parent_ids else None
                else:
                    break

        return commits

    async def branch(self, name: str, commit_id: str = None) -> bool:
        if commit_id is None:
            current_branch = await self._get_current_branch()
            if current_branch and current_branch in self._branches:
                commit_id = self._branches[current_branch].commit_id
            else:
                return False

        self._branches[name] = ShadowBranch(name=name, commit_id=commit_id)
        await self._save_refs()
        return True

    async def merge(self, source_branch: str, target_branch: str = None) -> bool:
        target_branch = target_branch or (await self._get_current_branch())

        if source_branch not in self._branches or target_branch not in self._branches:
            return False

        source_commit = self._branches[source_branch].commit_id
        target_commit = self._branches[target_branch].commit_id

        if source_commit == target_commit:
            return True

        self._branches[target_branch].commit_id = source_commit
        await self._save_refs()
        await self._checkout_commit(source_commit)

        return True


class ShadowGitRemote:
    def __init__(self, shadow_git: ShadowGit):
        self.shadow_git = shadow_git
        self.remotes: dict[str, str] = {}

    def add_remote(self, name: str, url: str):
        self.remotes[name] = url

    async def fetch(self, remote: str = "origin") -> bool:
        return True

    async def push(self, remote: str = "origin", branch: str = None) -> bool:
        return True

    async def pull(self, remote: str = "origin", branch: str = None) -> bool:
        return True