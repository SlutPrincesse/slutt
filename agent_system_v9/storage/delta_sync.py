"""
Delta Sync - Efficient synchronization using deltas
"""
import hashlib
import json
import time
import asyncio
from typing import Dict, List, Optional, Any, Set, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict


class DeltaType(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DIFF = "diff"
    PATCH = "patch"


@dataclass
class Delta:
    delta_id: str
    delta_type: DeltaType
    base_version: str
    target_version: str
    operations: List['DeltaOperation'] = field(default_factory=list)
    checksum: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delta_id": self.delta_id,
            "delta_type": self.delta_type.value,
            "base_version": self.base_version,
            "target_version": self.target_version,
            "operations": [op.to_dict() for op in self.operations],
            "checksum": self.checksum,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Delta':
        return cls(
            delta_id=data["delta_id"],
            delta_type=DeltaType(data["delta_type"]),
            base_version=data["base_version"],
            target_version=data["target_version"],
            operations=[DeltaOperation.from_dict(op) for op in data["operations"]],
            checksum=data.get("checksum", ""),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DeltaOperation:
    op_type: str
    path: str
    old_value: Any = None
    new_value: Any = None
    offset: int = 0
    length: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_type": self.op_type,
            "path": self.path,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "offset": self.offset,
            "length": self.length,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeltaOperation':
        return cls(
            op_type=data["op_type"],
            path=data["path"],
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            offset=data.get("offset", 0),
            length=data.get("length", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SyncState:
    version: str
    checksum: str
    last_synced: float = field(default_factory=time.time)
    pending_deltas: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DeltaEncoder:
    def __init__(self):
        self.algorithms = {
            'json': self._encode_json,
            'binary': self._encode_binary,
        }

    def encode(self, delta: Delta, format: str = 'json') -> bytes:
        if format in self.algorithms:
            return self.algorithms[format](delta)
        return json.dumps(delta.to_dict()).encode()

    def decode(self, data: bytes, format: str = 'json') -> Delta:
        if format == 'json':
            return Delta.from_dict(json.loads(data.decode()))
        return Delta.from_dict(json.loads(data.decode()))

    def _encode_json(self, delta: Delta) -> bytes:
        return json.dumps(delta.to_dict(), separators=(',', ':')).encode()

    def _encode_binary(self, delta: Delta) -> bytes:
        return json.dumps(delta.to_dict()).encode()


class DeltaGenerator:
    def __init__(self, encoder: DeltaEncoder = None):
        self.encoder = encoder or DeltaEncoder()

    def generate_delta(
        self,
        old_data: Any,
        new_data: Any,
        base_version: str = "",
        target_version: str = "",
    ) -> Delta:
        operations = self._diff(old_data, new_data, "")
        
        delta_id = hashlib.sha256(f"{base_version}:{target_version}:{time.time()}".encode()).hexdigest()[:16]
        
        if isinstance(old_data, bytes) and isinstance(new_data, bytes):
            delta_type = DeltaType.DIFF
            operations = self._binary_diff(old_data, new_data)
        elif old_data == new_data:
            delta_type = DeltaType.FULL
            operations = []
        else:
            delta_type = DeltaType.INCREMENTAL
        
        delta = Delta(
            delta_id=delta_id,
            delta_type=delta_type,
            base_version=base_version,
            target_version=target_version,
            operations=operations,
        )
        
        delta.checksum = self._compute_checksum(delta)
        return delta

    def _diff(self, old: Any, new: Any, path: str) -> List[DeltaOperation]:
        operations = []
        
        if type(old) != type(new):
            operations.append(DeltaOperation("replace", path, old, new))
            return operations
        
        if isinstance(old, dict):
            all_keys = set(old.keys()) | set(new.keys())
            for key in all_keys:
                new_path = f"{path}.{key}" if path else key
                if key not in old:
                    operations.append(DeltaOperation("add", new_path, None, new[key]))
                elif key not in new:
                    operations.append(DeltaOperation("remove", new_path, old[key], None))
                else:
                    operations.extend(self._diff(old[key], new[key], new_path))
        
        elif isinstance(old, list):
            max_len = max(len(old), len(new))
            for i in range(max_len):
                new_path = f"{path}[{i}]"
                if i >= len(old):
                    operations.append(DeltaOperation("add", new_path, None, new[i]))
                elif i >= len(new):
                    operations.append(DeltaOperation("remove", new_path, old[i], None))
                else:
                    operations.extend(self._diff(old[i], new[i], new_path))
        
        elif old != new:
            operations.append(DeltaOperation("replace", path, old, new))
        
        return operations

    def _binary_diff(self, old: bytes, new: bytes) -> List[DeltaOperation]:
        operations = []
        old_len = len(old)
        new_len = len(new)
        
        if old == new:
            return operations
        
        i = 0
        while i < min(old_len, new_len):
            if old[i] != new[i]:
                start = i
                while i < min(old_len, new_len) and old[i] != new[i]:
                    i += 1
                operations.append(DeltaOperation(
                    "replace_bytes",
                    "",
                    old[start:i],
                    new[start:i],
                    offset=start,
                    length=i - start,
                ))
            else:
                i += 1
        
        if old_len > new_len:
            operations.append(DeltaOperation(
                "remove_bytes",
                "",
                old[new_len:],
                None,
                offset=new_len,
                length=old_len - new_len,
            ))
        elif new_len > old_len:
            operations.append(DeltaOperation(
                "add_bytes",
                "",
                None,
                new[old_len:],
                offset=old_len,
                length=new_len - old_len,
            ))
        
        return operations

    def _compute_checksum(self, delta: Delta) -> str:
        data = json.dumps(delta.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(data).hexdigest()


class DeltaApplier:
    def __init__(self):
        self.algorithms = {
            'json': self._apply_json,
            'binary': self._apply_binary,
        }

    def apply(self, base_data: Any, delta: Delta) -> Any:
        if delta.delta_type == DeltaType.FULL:
            return delta.operations[0].new_value if delta.operations else base_data
        elif delta.delta_type == DeltaType.DIFF and isinstance(base_data, bytes):
            return self._apply_binary(base_data, delta)
        else:
            return self._apply_json(base_data, delta)

    def _apply_json(self, base_data: Any, delta: Delta) -> Any:
        if isinstance(base_data, dict):
            result = dict(base_data)
        elif isinstance(base_data, list):
            result = list(base_data)
        else:
            result = base_data
        
        for op in delta.operations:
            self._apply_operation(result, op)
        
        return result

    def _apply_operation(self, data: Any, op: DeltaOperation):
        path_parts = op.path.split('.') if op.path else []
        
        if not path_parts:
            return
        
        current = data
        for i, part in enumerate(path_parts[:-1]):
            if part.endswith(']'):
                key = part[:-1].split('[')
                idx = int(key[1])
                current = current[idx]
            else:
                current = current[part]
        
        last_part = path_parts[-1]
        if last_part.endswith(']'):
            key = last_part[:-1].split('[')
            idx = int(key[1])
            if op.op_type == "add":
                current.insert(idx, op.new_value)
            elif op.op_type == "remove":
                current.pop(idx)
            elif op.op_type == "replace":
                current[idx] = op.new_value
        else:
            if op.op_type == "add":
                current[last_part] = op.new_value
            elif op.op_type == "remove":
                current.pop(last_part, None)
            elif op.op_type == "replace":
                current[last_part] = op.new_value

    def _apply_binary(self, base_data: bytes, delta: Delta) -> bytes:
        result = bytearray(base_data)
        
        for op in sorted(delta.operations, key=lambda x: x.offset, reverse=True):
            if op.op_type == "replace_bytes":
                start = op.offset
                end = start + op.length
                if end <= len(result):
                    result[start:end] = op.new_value or b''
            elif op.op_type == "remove_bytes":
                start = op.offset
                end = start + op.length
                if end <= len(result):
                    del result[start:end]
            elif op.op_type == "add_bytes":
                start = op.offset
                if start <= len(result):
                    result[start:start] = op.new_value or b''
        
        return bytes(result)


class SyncEngine:
    def __init__(self, storage: Any = None):
        self.storage = storage
        self.encoder = DeltaEncoder()
        self.generator = DeltaGenerator(self.encoder)
        self.applier = DeltaApplier()
        self.sync_states: Dict[str, SyncState] = {}
        self._lock = asyncio.Lock()

    async def sync(
        self,
        key: str,
        local_data: Any,
        remote_version: str = None,
    ) -> Tuple[Any, Optional[Delta]]:
        async with self._lock:
            state = self.sync_states.get(key)
            
            if state is None:
                delta = self.generator.generate_delta(None, local_data, "", "1")
                self.sync_states[key] = SyncState(
                    version="1",
                    checksum=delta.checksum,
                )
                return local_data, delta
            
            if remote_version and remote_version != state.version:
                delta = await self._fetch_delta(key, state.version, remote_version)
                if delta:
                    local_data = self.applier.apply(local_data, delta)
                    state.version = remote_version
                    state.checksum = delta.checksum
                    state.last_synced = time.time()
            
            new_delta = self.generator.generate_delta(
                state.checksum, local_data, state.version, str(int(state.version) + 1)
            )
            
            if new_delta.operations:
                state.version = new_delta.target_version
                state.checksum = new_delta.checksum
                state.last_synced = time.time()
                return local_data, new_delta
            
            return local_data, None

    async def _fetch_delta(self, key: str, from_version: str, to_version: str) -> Optional[Delta]:
        return None

    def get_state(self, key: str) -> Optional[SyncState]:
        return self.sync_states.get(key)

    def set_state(self, key: str, state: SyncState):
        self.sync_states[key] = state


class ConflictResolver:
    def __init__(self):
        self.strategies = {
            'last_write_wins': self._last_write_wins,
            'merge': self._merge,
            'manual': self._manual,
        }

    def resolve(
        self,
        local: Any,
        remote: Any,
        base: Any,
        strategy: str = 'last_write_wins',
    ) -> Any:
        if strategy in self.strategies:
            return self.strategies[strategy](local, remote, base)
        return self._last_write_wins(local, remote, base)

    def _last_write_wins(self, local: Any, remote: Any, base: Any) -> Any:
        return remote

    def _merge(self, local: Any, remote: Any, base: Any) -> Any:
        if isinstance(local, dict) and isinstance(remote, dict):
            result = dict(base) if base else {}
            for k, v in local.items():
                result[k] = v
            for k, v in remote.items():
                if k not in result or result[k] != v:
                    result[k] = v
            return result
        return remote

    def _manual(self, local: Any, remote: Any, base: Any) -> Any:
        raise NotImplementedError("Manual resolution required")


class AssetLifecycler:
    def __init__(self, storage: Any, max_versions: int = 10, max_age: float = 86400 * 30):
        self.storage = storage
        self.max_versions = max_versions
        self.max_age = max_age
        self.policies: Dict[str, Dict] = {}

    def set_policy(self, collection: str, policy: Dict):
        self.policies[collection] = policy

    async def lifecycle(self, collection: str) -> Dict[str, int]:
        policy = self.policies.get(collection, {})
        max_versions = policy.get('max_versions', self.max_versions)
        max_age = policy.get('max_age', self.max_age)
        
        deleted = 0
        archived = 0
        
        return {"deleted": deleted, "archived": archived}

    async def prune_old_versions(self, key: str, keep: int = 5) -> int:
        return 0


class BuildLedger:
    def __init__(self, storage: Any):
        self.storage = storage
        self.entries: List[Dict[str, Any]] = []

    def record_build(self, build_info: Dict[str, Any]):
        entry = {
            "build_id": hashlib.sha256(f"{build_info}:{time.time()}".encode()).hexdigest()[:16],
            "timestamp": time.time(),
            **build_info,
        }
        self.entries.append(entry)
        if len(self.entries) > 10000:
            self.entries = self.entries[-10000:]

    def get_build_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.entries[-limit:]

    def get_latest_build(self) -> Optional[Dict[str, Any]]:
        return self.entries[-1] if self.entries else None

    def query_builds(self, filter_fn: Callable) -> List[Dict[str, Any]]:
        return [e for e in self.entries if filter_fn(e)]