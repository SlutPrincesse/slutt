"""
Workspace Synchronizer - Sync workspaces across environments
"""
import asyncio
import hashlib
import os
import shutil
import time
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict
import json


class SyncMode(Enum):
    ONE_WAY = "one_way"
    TWO_WAY = "two_way"
    MIRROR = "mirror"
    INCREMENTAL = "incremental"


class ConflictStrategy(Enum):
    SOURCE_WINS = "source_wins"
    TARGET_WINS = "target_wins"
    NEWER_WINS = "newer_wins"
    MANUAL = "manual"
    MERGE = "merge"


@dataclass
class SyncConfig:
    source: str
    target: str
    mode: SyncMode = SyncMode.INCREMENTAL
    conflict_strategy: ConflictStrategy = ConflictStrategy.NEWER_WINS
    exclude_patterns: List[str] = field(default_factory=lambda: ['.git', '__pycache__', 'node_modules', '.venv', 'venv', '*.pyc', '.DS_Store'])
    include_patterns: List[str] = field(default_factory=list)
    delete_extraneous: bool = False
    dry_run: bool = False
    bandwidth_limit: int = 0
    preserve_permissions: bool = True
    preserve_timestamps: bool = True
    follow_symlinks: bool = False


@dataclass
class FileInfo:
    path: str
    size: int
    mtime: float
    hash: str = ""
    is_dir: bool = False
    permissions: int = 0

    @classmethod
    def from_path(cls, path: Path, rel_path: str = None) -> 'FileInfo':
        stat = path.stat()
        rel = rel_path or str(path)
        return cls(
            path=rel,
            size=stat.st_size,
            mtime=stat.st_mtime,
            is_dir=path.is_dir(),
            permissions=stat.st_mode,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "mtime": self.mtime,
            "hash": self.hash,
            "is_dir": self.is_dir,
            "permissions": self.permissions,
        }


@dataclass
class SyncResult:
    success: bool
    files_copied: int = 0
    files_updated: int = 0
    files_deleted: int = 0
    files_skipped: int = 0
    bytes_transferred: int = 0
    errors: List[str] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    duration: float = 0.0


class FileHasher:
    @staticmethod
    def compute_hash(file_path: Path, algorithm: str = "md5") -> str:
        hasher = hashlib.new(algorithm)
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
        except Exception:
            return ""
        return hasher.hexdigest()

    @staticmethod
    def compute_hash_async(file_path: Path, algorithm: str = "md5") -> str:
        return FileHasher.compute_hash(file_path, algorithm)


class WorkspaceSynchronizer:
    def __init__(self):
        self.active_syncs: Dict[str, asyncio.Task] = {}
        self.sync_history: List[Dict] = []
        self._lock = asyncio.Lock()

    async def sync(self, config: SyncConfig) -> SyncResult:
        start = time.time()
        result = SyncResult(success=True)
        
        source_path = Path(config.source).resolve()
        target_path = Path(config.target).resolve()
        
        if not source_path.exists():
            result.success = False
            result.errors.append(f"Source does not exist: {source_path}")
            return result
        
        if config.dry_run:
            return await self._dry_run_sync(source_path, target_path, config)
        
        if config.mode == SyncMode.ONE_WAY:
            result = await self._one_way_sync(source_path, target_path, config)
        elif config.mode == SyncMode.TWO_WAY:
            result = await self._two_way_sync(source_path, target_path, config)
        elif config.mode == SyncMode.MIRROR:
            result = await self._mirror_sync(source_path, target_path, config)
        elif config.mode == SyncMode.INCREMENTAL:
            result = await self._incremental_sync(source_path, target_path, config)
        
        result.duration = time.time() - start
        
        async with self._lock:
            self.sync_history.append({
                "timestamp": start,
                "config": config.__dict__,
                "result": result.__dict__,
            })
        
        return result

    async def _dry_run_sync(self, source: Path, target: Path, config: SyncConfig) -> SyncResult:
        result = SyncResult(success=True)
        source_files = await self._scan_directory(source, config)
        target_files = await self._scan_directory(target, config) if target.exists() else {}
        
        for rel_path, src_info in source_files.items():
            if rel_path in target_files:
                tgt_info = target_files[rel_path]
                if src_info.size != tgt_info.size or src_info.mtime > tgt_info.mtime:
                    result.files_updated += 1
                    result.bytes_transferred += src_info.size
                else:
                    result.files_skipped += 1
            else:
                result.files_copied += 1
                result.bytes_transferred += src_info.size
        
        if config.delete_extraneous:
            for rel_path in target_files:
                if rel_path not in source_files:
                    result.files_deleted += 1
        
        return result

    async def _one_way_sync(self, source: Path, target: Path, config: SyncConfig) -> SyncResult:
        result = SyncResult(success=True)
        target.mkdir(parents=True, exist_ok=True)
        
        source_files = await self._scan_directory(source, config)
        
        for rel_path, src_info in source_files.items():
            src_file = source / rel_path
            tgt_file = target / rel_path
            
            if src_info.is_dir:
                tgt_file.mkdir(parents=True, exist_ok=True)
                continue
            
            tgt_file.parent.mkdir(parents=True, exist_ok=True)
            
            if tgt_file.exists():
                tgt_stat = tgt_file.stat()
                if src_info.size == tgt_stat.st_size and src_info.mtime <= tgt_stat.st_mtime:
                    result.files_skipped += 1
                    continue
                result.files_updated += 1
            else:
                result.files_copied += 1
            
            try:
                if config.bandwidth_limit > 0:
                    await self._copy_with_throttle(src_file, tgt_file, config.bandwidth_limit)
                else:
                    shutil.copy2(src_file, tgt_file)
                
                if config.preserve_timestamps:
                    os.utime(tgt_file, (src_info.mtime, src_info.mtime))
                
                result.bytes_transferred += src_info.size
            except Exception as e:
                result.errors.append(f"Failed to copy {rel_path}: {e}")
        
        if config.delete_extraneous:
            target_files = await self._scan_directory(target, config)
            for rel_path in target_files:
                if rel_path not in source_files:
                    tgt_file = target / rel_path
                    try:
                        if tgt_file.is_dir():
                            shutil.rmtree(tgt_file)
                        else:
                            tgt_file.unlink()
                        result.files_deleted += 1
                    except Exception as e:
                        result.errors.append(f"Failed to delete {rel_path}: {e}")
        
        return result

    async def _two_way_sync(self, source: Path, target: Path, config: SyncConfig) -> SyncResult:
        result = SyncResult(success=True)
        
        source_files = await self._scan_directory(source, config)
        target_files = await self._scan_directory(target, config) if target.exists() else {}
        
        all_paths = set(source_files.keys()) | set(target_files.keys())
        
        for rel_path in all_paths:
            src_info = source_files.get(rel_path)
            tgt_info = target_files.get(rel_path)
            
            src_file = source / rel_path
            tgt_file = target / rel_path
            
            if src_info and src_info.is_dir:
                src_file.mkdir(parents=True, exist_ok=True)
                continue
            if tgt_info and tgt_info.is_dir:
                tgt_file.mkdir(parents=True, exist_ok=True)
                continue
            
            if src_info and not tgt_info:
                tgt_file.parent.mkdir(parents=True, exist_ok=True)
                await self._copy_file(src_file, tgt_file, config)
                result.files_copied += 1
                result.bytes_transferred += src_info.size
            elif tgt_info and not src_info:
                src_file.parent.mkdir(parents=True, exist_ok=True)
                await self._copy_file(tgt_file, src_file, config)
                result.files_copied += 1
                result.bytes_transferred += tgt_info.size
            elif src_info and tgt_info:
                if src_info.size != tgt_info.size or src_info.mtime != tgt_info.mtime:
                    conflict = await self._resolve_conflict(src_file, tgt_file, src_info, tgt_info, config)
                    if conflict == "source":
                        await self._copy_file(src_file, tgt_file, config)
                        result.files_updated += 1
                        result.bytes_transferred += src_info.size
                    elif conflict == "target":
                        await self._copy_file(tgt_file, src_file, config)
                        result.files_updated += 1
                        result.bytes_transferred += tgt_info.size
                    else:
                        result.conflicts.append({
                            "path": rel_path,
                            "source": src_info.to_dict(),
                            "target": tgt_info.to_dict(),
                            "resolution": "skipped",
                        })
                        result.files_skipped += 1
                else:
                    result.files_skipped += 1
        
        return result

    async def _mirror_sync(self, source: Path, target: Path, config: SyncConfig) -> SyncResult:
        config = SyncConfig(**config.__dict__, delete_extraneous=True)
        return await self._one_way_sync(source, target, config)

    async def _incremental_sync(self, source: Path, target: Path, config: SyncConfig) -> SyncResult:
        state_file = target / ".sync_state.json"
        last_sync = await self._load_sync_state(state_file)
        
        source_files = await self._scan_directory(source, config)
        changed_files = {}
        
        for rel_path, info in source_files.items():
            if rel_path not in last_sync or last_sync[rel_path].get('mtime', 0) < info.mtime:
                changed_files[rel_path] = info
        
        config_changed = SyncConfig(**config.__dict__)
        result = SyncResult(success=True)
        target.mkdir(parents=True, exist_ok=True)
        
        for rel_path, src_info in changed_files.items():
            src_file = source / rel_path
            tgt_file = target / rel_path
            
            if src_info.is_dir:
                tgt_file.mkdir(parents=True, exist_ok=True)
                continue
            
            tgt_file.parent.mkdir(parents=True, exist_ok=True)
            await self._copy_file(src_file, tgt_file, config)
            
            if tgt_file.exists():
                result.files_updated += 1
            else:
                result.files_copied += 1
            result.bytes_transferred += src_info.size
        
        current_state = {p: i.to_dict() for p, i in source_files.items()}
        await self._save_sync_state(state_file, current_state)
        
        return result

    async def _resolve_conflict(self, src_file: Path, tgt_file: Path, 
                                src_info: FileInfo, tgt_info: FileInfo, 
                                config: SyncConfig) -> str:
        if config.conflict_strategy == ConflictStrategy.SOURCE_WINS:
            return "source"
        elif config.conflict_strategy == ConflictStrategy.TARGET_WINS:
            return "target"
        elif config.conflict_strategy == ConflictStrategy.NEWER_WINS:
            return "source" if src_info.mtime > tgt_info.mtime else "target"
        elif config.conflict_strategy == ConflictStrategy.MANUAL:
            return "skip"
        return "source"

    async def _copy_file(self, src: Path, dst: Path, config: SyncConfig):
        if config.bandwidth_limit > 0:
            await self._copy_with_throttle(src, dst, config.bandwidth_limit)
        else:
            shutil.copy2(src, dst)
        
        if config.preserve_timestamps:
            src_stat = src.stat()
            os.utime(dst, (src_stat.st_atime, src_stat.st_mtime))

    async def _copy_with_throttle(self, src: Path, dst: Path, limit: int):
        chunk_size = min(8192, limit // 10)
        with open(src, 'rb') as fsrc:
            with open(dst, 'wb') as fdst:
                while True:
                    chunk = fsrc.read(chunk_size)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    if limit > 0:
                        await asyncio.sleep(len(chunk) / limit)

    async def _scan_directory(self, root: Path, config: SyncConfig) -> Dict[str, FileInfo]:
        files = {}
        if not root.exists():
            return files
        
        for path in root.rglob('*'):
            try:
                rel = path.relative_to(root)
                rel_str = str(rel)
                
                if self._should_exclude(rel_str, config):
                    continue
                
                if config.include_patterns and not self._matches_include(rel_str, config):
                    continue
                
                files[rel_str] = FileInfo.from_path(path, rel_str)
            except Exception:
                continue
        
        return files

    def _should_exclude(self, path: str, config: SyncConfig) -> bool:
        for pattern in config.exclude_patterns:
            if self._match_pattern(path, pattern):
                return True
        return False

    def _matches_include(self, path: str, config: SyncConfig) -> bool:
        for pattern in config.include_patterns:
            if self._match_pattern(path, pattern):
                return True
        return False

    def _match_pattern(self, path: str, pattern: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern)

    async def _load_sync_state(self, state_file: Path) -> Dict:
        if state_file.exists():
            try:
                with open(state_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    async def _save_sync_state(self, state_file: Path, state: Dict):
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, 'w') as f:
            json.dump(state, f)

    async def start_background_sync(self, sync_id: str, config: SyncConfig, interval: float = 300.0):
        if sync_id in self.active_syncs:
            return False
        
        async def sync_loop():
            while sync_id in self.active_syncs:
                await self.sync(config)
                await asyncio.sleep(interval)
        
        task = asyncio.create_task(sync_loop())
        self.active_syncs[sync_id] = task
        return True

    async def stop_background_sync(self, sync_id: str):
        if sync_id in self.active_syncs:
            self.active_syncs[sync_id].cancel()
            try:
                await self.active_syncs[sync_id]
            except asyncio.CancelledError:
                pass
            del self.active_syncs[sync_id]

    def get_history(self, limit: int = 100) -> List[Dict]:
        return self.sync_history[-limit:]


class WorkspaceReplicator:
    def __init__(self, synchronizer: WorkspaceSynchronizer):
        self.synchronizer = synchronizer

    async def replicate_to_multiple(self, source: str, targets: List[str], config: SyncConfig) -> List[SyncResult]:
        tasks = []
        for target in targets:
            target_config = SyncConfig(**config.__dict__, target=target)
            tasks.append(self.synchronizer.sync(target_config))
        return await asyncio.gather(*tasks)

    async def create_replica(self, source: str, replica_path: str, config: SyncConfig) -> SyncResult:
        replica_config = SyncConfig(**config.__dict__, source=source, target=replica_path, mode=SyncMode.MIRROR)
        return await self.synchronizer.sync(replica_config)


class SyncScheduler:
    def __init__(self):
        self.schedules: Dict[str, Dict] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def add_schedule(self, name: str, config: SyncConfig, cron: str = "0 */5 * * * *"):
        self.schedules[name] = {"config": config, "cron": cron, "last_run": 0}

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _scheduler_loop(self):
        synchronizer = WorkspaceSynchronizer()
        while self._running:
            now = time.time()
            for name, schedule in self.schedules.items():
                if self._should_run(schedule, now):
                    await synchronizer.sync(schedule["config"])
                    schedule["last_run"] = now
            await asyncio.sleep(60)

    def _should_run(self, schedule: Dict, now: float) -> bool:
        return True


class ConflictResolver:
    @staticmethod
    async def resolve_manual(src: Path, tgt: Path, strategy: Callable) -> str:
        return await strategy(src, tgt)

    @staticmethod
    def merge_text_files(src: Path, tgt: Path, output: Path) -> bool:
        try:
            src_lines = src.read_text().splitlines()
            tgt_lines = tgt.read_text().splitlines()
            
            import difflib
            merged = list(difflib.unified_diff(src_lines, tgt_lines, lineterm=''))
            
            output.write_text('\n'.join(merged))
            return True
        except Exception:
            return False