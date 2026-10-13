"""
Delta Syncer - Efficient data synchronization for edge devices
"""
import asyncio
import hashlib
import json
import time
import zlib
from typing import Dict, List, Optional, Any, Set, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict


class SyncMode(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DELTA = "delta"
    BIDIRECTIONAL = "bidirectional"


class ConflictResolution(Enum):
    SERVER_WINS = "server_wins"
    CLIENT_WINS = "client_wins"
    MERGE = "merge"
    TIMESTAMP = "timestamp"
    MANUAL = "manual"


@dataclass
class SyncConfig:
    mode: SyncMode = SyncMode.INCREMENTAL
    conflict_resolution: ConflictResolution = ConflictResolution.TIMESTAMP
    compression: bool = True
    batch_size: int = 100
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 30.0


@dataclass
class SyncItem:
    key: str
    value: Any
    version: int = 1
    hash: str = ""
    timestamp: float = field(default_factory=time.time)
    deleted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.hash:
            self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        data = json.dumps(self.value, sort_keys=True, default=str).encode()
        return hashlib.sha256(data).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "version": self.version,
            "hash": self.hash,
            "timestamp": self.timestamp,
            "deleted": self.deleted,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncItem':
        return cls(**data)


@dataclass
class Delta:
    delta_id: str
    base_version: int
    target_version: int
    operations: List['DeltaOp'] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delta_id": self.delta_id,
            "base_version": self.base_version,
            "target_version": self.target_version,
            "operations": [op.to_dict() for op in self.operations],
            "timestamp": self.timestamp,
            "checksum": self.checksum,
        }


@dataclass
class DeltaOp:
    op_type: str
    key: str
    old_value: Any = None
    new_value: Any = None
    old_hash: str = ""
    new_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_type": self.op_type,
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "old_hash": self.old_hash,
            "new_hash": self.new_hash,
        }


@dataclass
class SyncResult:
    success: bool
    synced_items: int = 0
    failed_items: int = 0
    conflicts: List[str] = field(default_factory=list)
    delta: Optional[Delta] = None
    error: Optional[str] = None
    duration: float = 0.0


class DeltaSyncer:
    def __init__(
        self,
        local_store: Dict[str, SyncItem],
        remote_getter: Callable,
        remote_setter: Callable,
        config: SyncConfig = None,
    ):
        self.local_store = local_store
        self.remote_getter = remote_getter
        self.remote_setter = remote_setter
        self.config = config or SyncConfig()
        self.version = 0
        self._lock = asyncio.Lock()
        self.sync_history: List[SyncResult] = []

    async def sync(self) -> SyncResult:
        start = time.time()
        
        async with self._lock:
            try:
                if self.config.mode == SyncMode.FULL:
                    return await self._full_sync()
                elif self.config.mode == SyncMode.INCREMENTAL:
                    return await self._incremental_sync()
                elif self.config.mode == SyncMode.DELTA:
                    return await self._delta_sync()
                elif self.config.mode == SyncMode.BIDIRECTIONAL:
                    return await self._bidirectional_sync()
            except Exception as e:
                result = SyncResult(
                    success=False,
                    error=str(e),
                    duration=time.time() - start,
                )
                self.sync_history.append(result)
                return result
        
        result = SyncResult(success=True, duration=time.time() - start)
        self.sync_history.append(result)
        return result

    async def _full_sync(self) -> SyncResult:
        remote_items = await self._get_remote_items()
        
        for key, remote_item in remote_items.items():
            local_item = self.local_store.get(key)
            
            if not local_item or remote_item.version > local_item.version:
                await self._apply_remote_item(key, remote_item)
            elif local_item.version > remote_item.version:
                await self.remote_setter(key, local_item)
        
        return SyncResult(success=True, synced_items=len(remote_items))

    async def _incremental_sync(self) -> SyncResult:
        local_changes = self._get_local_changes()
        remote_changes = await self._get_remote_changes()
        
        conflicts = []
        
        for key, remote_item in remote_changes.items():
            local_item = self.local_store.get(key)
            
            if local_item and local_item.version > self.version:
                if remote_item.version > self.version:
                    conflict = await self._resolve_conflict(key, local_item, remote_item)
                    if conflict:
                        conflicts.append(key)
                    else:
                        await self._apply_remote_item(key, remote_item)
                else:
                    await self.remote_setter(key, local_item)
            elif remote_item.version > self.version:
                await self._apply_remote_item(key, remote_item)
        
        for key, local_item in local_changes.items():
            if key not in remote_changes:
                await self.remote_setter(key, local_item)
        
        return SyncResult(success=True, synced_items=len(local_changes) + len(remote_changes), conflicts=conflicts)

    async def _delta_sync(self) -> SyncResult:
        delta = await self._generate_delta()
        
        if delta.operations:
            await self._apply_delta(delta)
            await self._send_delta(delta)
        
        return SyncResult(success=True, synced_items=len(delta.operations), delta=delta)

    async def _bidirectional_sync(self) -> SyncResult:
        push_result = await self._push_changes()
        pull_result = await self._pull_changes()
        
        return SyncResult(
            success=push_result.success and pull_result.success,
            synced_items=push_result.synced_items + pull_result.synced_items,
            conflicts=push_result.conflicts + pull_result.conflicts,
        )

    async def _push_changes(self) -> SyncResult:
        changes = self._get_local_changes()
        for key, item in changes.items():
            await self.remote_setter(key, item)
        return SyncResult(success=True, synced_items=len(changes))

    async def _pull_changes(self) -> SyncResult:
        remote_items = await self._get_remote_items()
        conflicts = []
        
        for key, remote_item in remote_items.items():
            local_item = self.local_store.get(key)
            
            if local_item and local_item.version > remote_item.version:
                conflict = await self._resolve_conflict(key, local_item, remote_item)
                if conflict:
                    conflicts.append(key)
                else:
                    await self._apply_remote_item(key, remote_item)
            elif remote_item.version > (local_item.version if local_item else 0):
                await self._apply_remote_item(key, remote_item)
        
        return SyncResult(success=True, synced_items=len(remote_items), conflicts=conflicts)

    async def _resolve_conflict(self, key: str, local: SyncItem, remote: SyncItem) -> bool:
        if self.config.conflict_resolution == ConflictResolution.SERVER_WINS:
            await self._apply_remote_item(key, remote)
            return False
        elif self.config.conflict_resolution == ConflictResolution.CLIENT_WINS:
            await self.remote_setter(key, local)
            return False
        elif self.config.conflict_resolution == ConflictResolution.TIMESTAMP:
            if remote.timestamp > local.timestamp:
                await self._apply_remote_item(key, remote)
            else:
                await self.remote_setter(key, local)
            return False
        elif self.config.conflict_resolution == ConflictResolution.MERGE:
            merged = self._merge_items(local, remote)
            await self._apply_remote_item(key, merged)
            await self.remote_setter(key, merged)
            return False
        
        return True

    def _merge_items(self, local: SyncItem, remote: SyncItem) -> SyncItem:
        if isinstance(local.value, dict) and isinstance(remote.value, dict):
            merged = dict(local.value)
            merged.update(remote.value)
            return SyncItem(
                key=local.key,
                value=merged,
                version=max(local.version, remote.version) + 1,
                timestamp=time.time(),
            )
        return remote if remote.timestamp > local.timestamp else local

    async def _apply_remote_item(self, key: str, item: SyncItem):
        self.local_store[key] = item
        self.version = max(self.version, item.version)

    def _get_local_changes(self) -> Dict[str, SyncItem]:
        return {k: v for k, v in self.local_store.items() if v.version > self.version}

    async def _get_remote_items(self) -> Dict[str, SyncItem]:
        return await self.remote_getter()

    async def _get_remote_changes(self) -> Dict[str, SyncItem]:
        remote_items = await self._get_remote_items()
        return {k: v for k, v in remote_items.items() if v.version > self.version}

    async def _generate_delta(self) -> Delta:
        operations = []
        local_changes = self._get_local_changes()
        
        for key, item in local_changes.items():
            operations.append(DeltaOp(
                op_type="upsert" if not item.deleted else "delete",
                key=key,
                old_value=None,
                new_value=item.value if not item.deleted else None,
                old_hash="",
                new_hash=item.hash,
            ))
        
        delta = Delta(
            delta_id=hashlib.md5(f"{self.version}:{time.time()}".encode()).hexdigest()[:12],
            base_version=self.version,
            target_version=self.version + len(operations),
            operations=operations,
        )
        
        delta.checksum = hashlib.md5(json.dumps(delta.to_dict(), sort_keys=True).encode()).hexdigest()
        return delta

    async def _apply_delta(self, delta: Delta):
        for op in delta.operations:
            if op.op_type == "delete":
                self.local_store.pop(op.key, None)
            else:
                self.local_store[op.key] = SyncItem(
                    key=op.key,
                    value=op.new_value,
                    version=delta.target_version,
                    hash=op.new_hash,
                )
        
        self.version = delta.target_version

    async def _send_delta(self, delta: Delta):
        pass

    def get_stats(self) -> Dict[str, Any]:
        return {
            "local_items": len(self.local_store),
            "current_version": self.version,
            "sync_history": len(self.sync_history),
            "last_sync": self.sync_history[-1].duration if self.sync_history else 0,
        }


class OfflineSyncer(DeltaSyncer):
    def __init__(self, *args, queue: 'DeferredQueue' = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = queue
        self.pending_sync = False

    async def queue_sync(self):
        if self.queue and not self.pending_sync:
            self.pending_sync = True
            await self.queue.enqueue({"type": "sync", "syncer_id": id(self)})

    async def process_queue(self):
        self.pending_sync = False
        await self.sync()


class ConflictFreeSyncer:
    def __init__(self, local_store: Dict[str, SyncItem]):
        self.local_store = local_store
        self.vector_clocks: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.node_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]

    def update(self, key: str, value: Any) -> SyncItem:
        self.vector_clocks[key][self.node_id] += 1
        
        item = SyncItem(
            key=key,
            value=value,
            version=self.vector_clocks[key][self.node_id],
            timestamp=time.time(),
        )
        self.local_store[key] = item
        return item

    def merge(self, remote_store: Dict[str, SyncItem], remote_clocks: Dict[str, Dict[str, int]]) -> List[str]:
        merged = []
        
        all_keys = set(self.local_store.keys()) | set(remote_store.keys())
        
        for key in all_keys:
            local_item = self.local_store.get(key)
            remote_item = remote_store.get(key)
            local_clock = self.vector_clocks.get(key, {})
            remote_clock = remote_clocks.get(key, {})
            
            if not local_item:
                self.local_store[key] = remote_item
                self.vector_clocks[key] = remote_clock
                merged.append(key)
            elif not remote_item:
                pass
            else:
                comparison = self._compare_clocks(local_clock, remote_clock)
                
                if comparison == "remote_newer":
                    self.local_store[key] = remote_item
                    self.vector_clocks[key] = remote_clock
                    merged.append(key)
                elif comparison == "concurrent":
                    merged_item = self._merge_concurrent(local_item, remote_item, local_clock, remote_clock)
                    self.local_store[key] = merged_item
                    self.vector_clocks[key] = self._merge_clocks(local_clock, remote_clock)
                    merged.append(key)
        
        return merged

    def _compare_clocks(self, clock1: Dict[str, int], clock2: Dict[str, int]) -> str:
        all_nodes = set(clock1.keys()) | set(clock2.keys())
        
        clock1_greater = False
        clock2_greater = False
        
        for node in all_nodes:
            v1 = clock1.get(node, 0)
            v2 = clock2.get(node, 0)
            if v1 > v2:
                clock1_greater = True
            elif v2 > v1:
                clock2_greater = True
        
        if clock1_greater and not clock2_greater:
            return "local_newer"
        elif clock2_greater and not clock1_greater:
            return "remote_newer"
        return "concurrent"

    def _merge_clocks(self, clock1: Dict[str, int], clock2: Dict[str, int]) -> Dict[str, int]:
        merged = {}
        all_nodes = set(clock1.keys()) | set(clock2.keys())
        for node in all_nodes:
            merged[node] = max(clock1.get(node, 0), clock2.get(node, 0))
        return merged

    def _merge_concurrent(self, local: SyncItem, remote: SyncItem, local_clock: Dict, remote_clock: Dict) -> SyncItem:
        if isinstance(local.value, dict) and isinstance(remote.value, dict):
            merged = dict(local.value)
            merged.update(remote.value)
            return SyncItem(
                key=local.key,
                value=merged,
                version=max(local.version, remote.version) + 1,
                timestamp=time.time(),
            )
        return remote if remote.timestamp > local.timestamp else local


class BackgroundSyncer:
    def __init__(self, syncer: DeltaSyncer, interval: float = 60.0):
        self.syncer = syncer
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable] = []

    def on_sync(self, callback: Callable):
        self._callbacks.append(callback)

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._sync_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _sync_loop(self):
        while self._running:
            await asyncio.sleep(self.interval)
            result = await self.syncer.sync()
            
            for callback in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(result)
                    else:
                        callback(result)
                except Exception:
                    pass