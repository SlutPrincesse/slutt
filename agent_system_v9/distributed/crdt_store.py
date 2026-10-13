"""
CRDT Store - Conflict-free Replicated Data Types for distributed state
"""
import asyncio
import builtins
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar('T')


class CRDTType(Enum):
    G_COUNTER = "g_counter"
    PN_COUNTER = "pn_counter"
    G_SET = "g_set"
    OR_SET = "or_set"
    LWW_REGISTER = "lww_register"
    LWW_MAP = "lww_map"
    RGA = "rga"
    YATA = "yata"


@dataclass
class VectorClock:
    clocks: dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str):
        self.clocks[node_id] = self.clocks.get(node_id, 0) + 1

    def merge(self, other: 'VectorClock'):
        for node_id, clock in other.clocks.items():
            self.clocks[node_id] = max(self.clocks.get(node_id, 0), clock)

    def happens_before(self, other: 'VectorClock') -> bool:
        dominated = False
        for node_id, clock in self.clocks.items():
            if clock > other.clocks.get(node_id, 0):
                return False
            if clock < other.clocks.get(node_id, 0):
                dominated = True
        return dominated

    def concurrent(self, other: 'VectorClock') -> bool:
        return not self.happens_before(other) and not other.happens_before(self)

    def to_dict(self) -> dict[str, int]:
        return dict(self.clocks)

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> 'VectorClock':
        return cls(clocks=data)


class CRDT(ABC):
    @abstractmethod
    def merge(self, other: 'CRDT') -> 'CRDT':
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> 'CRDT':
        pass


class GCounter(CRDT):
    def __init__(self, node_id: str = ""):
        self.node_id = node_id
        self.counts: dict[str, int] = defaultdict(int)

    def increment(self, node_id: str = None, value: int = 1):
        nid = node_id or self.node_id
        self.counts[nid] += value

    def value(self) -> int:
        return sum(self.counts.values())

    def merge(self, other: 'GCounter') -> 'GCounter':
        result = GCounter(self.node_id)
        all_nodes = set(self.counts.keys()) | set(other.counts.keys())
        for node in all_nodes:
            result.counts[node] = max(self.counts.get(node, 0), other.counts.get(node, 0))
        return result

    def to_dict(self) -> dict[str, Any]:
        return {"type": "g_counter", "node_id": self.node_id, "counts": dict(self.counts)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'GCounter':
        counter = cls(data.get("node_id", ""))
        counter.counts = defaultdict(int, data.get("counts", {}))
        return counter


class PNCounter(CRDT):
    def __init__(self, node_id: str = ""):
        self.node_id = node_id
        self.positive = GCounter(node_id)
        self.negative = GCounter(node_id)

    def increment(self, node_id: str = None, value: int = 1):
        self.positive.increment(node_id, value)

    def decrement(self, node_id: str = None, value: int = 1):
        self.negative.increment(node_id, value)

    def value(self) -> int:
        return self.positive.value() - self.negative.value()

    def merge(self, other: 'PNCounter') -> 'PNCounter':
        result = PNCounter(self.node_id)
        result.positive = self.positive.merge(other.positive)
        result.negative = self.negative.merge(other.negative)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "pn_counter",
            "node_id": self.node_id,
            "positive": self.positive.to_dict(),
            "negative": self.negative.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'PNCounter':
        counter = cls(data.get("node_id", ""))
        counter.positive = GCounter.from_dict(data["positive"])
        counter.negative = GCounter.from_dict(data["negative"])
        return counter


class GSet(CRDT, Generic[T]):
    def __init__(self, node_id: str = ""):
        self.node_id = node_id
        self.elements: set[T] = set()

    def add(self, element: T):
        self.elements.add(element)

    def contains(self, element: T) -> bool:
        return element in self.elements

    def merge(self, other: 'GSet') -> 'GSet':
        result = GSet(self.node_id)
        result.elements = self.elements | other.elements
        return result

    def to_dict(self) -> dict[str, Any]:
        return {"type": "g_set", "node_id": self.node_id, "elements": list(self.elements)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'GSet':
        gset = cls(data.get("node_id", ""))
        gset.elements = set(data.get("elements", []))
        return gset


class ORSet(CRDT, Generic[T]):
    def __init__(self, node_id: str = ""):
        self.node_id = node_id
        self.elements: dict[T, dict[str, float]] = {}
        self.add_tags: dict[T, dict[str, float]] = {}
        self.remove_tags: dict[T, dict[str, float]] = {}

    def _generate_tag(self) -> str:
        return f"{self.node_id}:{time.time()}:{uuid.uuid4().hex[:8]}"

    def add(self, element: T):
        tag = self._generate_tag()
        if element not in self.elements:
            self.elements[element] = {}
            self.add_tags[element] = {}
            self.remove_tags[element] = {}
        self.add_tags[element][tag] = time.time()

    def remove(self, element: T):
        if element in self.elements:
            for tag in self.add_tags.get(element, {}):
                self.remove_tags[element][tag] = time.time()

    def contains(self, element: T) -> bool:
        if element not in self.elements:
            return False
        add_tags = set(self.add_tags.get(element, {}).keys())
        remove_tags = set(self.remove_tags.get(element, {}).keys())
        return len(add_tags - remove_tags) > 0

    def get_elements(self) -> set[T]:
        return {e for e in self.elements if self.contains(e)}

    def merge(self, other: 'ORSet') -> 'ORSet':
        result = ORSet(self.node_id)
        all_elements = set(self.elements.keys()) | set(other.elements.keys())

        for element in all_elements:
            result.add_tags[element] = {}
            result.remove_tags[element] = {}

            result.add_tags[element].update(self.add_tags.get(element, {}))
            result.add_tags[element].update(other.add_tags.get(element, {}))

            result.remove_tags[element].update(self.remove_tags.get(element, {}))
            result.remove_tags[element].update(other.remove_tags.get(element, {}))

            add_tags = set(result.add_tags[element].keys())
            remove_tags = set(result.remove_tags[element].keys())

            if add_tags - remove_tags:
                result.elements[element] = {}

        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "or_set",
            "node_id": self.node_id,
            "elements": {str(k): list(v.keys()) for k, v in self.elements.items()},
            "add_tags": {str(k): v for k, v in self.add_tags.items()},
            "remove_tags": {str(k): v for k, v in self.remove_tags.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ORSet':
        orset = cls(data.get("node_id", ""))
        for k, v in data.get("elements", {}).items():
            orset.elements[eval(k)] = dict.fromkeys(v, True)
        for k, v in data.get("add_tags", {}).items():
            orset.add_tags[eval(k)] = v
        for k, v in data.get("remove_tags", {}).items():
            orset.remove_tags[eval(k)] = v
        return orset


class LWWRegister(CRDT, Generic[T]):
    def __init__(self, node_id: str = "", value: T = None):
        self.node_id = node_id
        self.value = value
        self.timestamp = time.time()
        self.node_ts = node_id

    def set(self, value: T, node_id: str = None, timestamp: float = None):
        ts = timestamp or time.time()
        nid = node_id or self.node_id

        if ts > self.timestamp or (ts == self.timestamp and nid > self.node_ts):
            self.value = value
            self.timestamp = ts
            self.node_ts = nid

    def get(self) -> T:
        return self.value

    def merge(self, other: 'LWWRegister') -> 'LWWRegister':
        result = LWWRegister(self.node_id)
        if other.timestamp > self.timestamp or \
           (other.timestamp == self.timestamp and other.node_ts > self.node_ts):
            result.value = other.value
            result.timestamp = other.timestamp
            result.node_ts = other.node_ts
        else:
            result.value = self.value
            result.timestamp = self.timestamp
            result.node_ts = self.node_ts
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "lww_register",
            "node_id": self.node_id,
            "value": self.value,
            "timestamp": self.timestamp,
            "node_ts": self.node_ts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'LWWRegister':
        reg = cls(data.get("node_id", ""))
        reg.value = data.get("value")
        reg.timestamp = data.get("timestamp", 0)
        reg.node_ts = data.get("node_ts", "")
        return reg


class LWWMap(CRDT):
    def __init__(self, node_id: str = ""):
        self.node_id = node_id
        self.registers: dict[str, LWWRegister] = {}

    def set(self, key: str, value: Any, node_id: str = None, timestamp: float = None):
        if key not in self.registers:
            self.registers[key] = LWWRegister(node_id or self.node_id)
        self.registers[key].set(value, node_id, timestamp)

    def get(self, key: str) -> Any:
        reg = self.registers.get(key)
        return reg.get() if reg else None

    def delete(self, key: str, node_id: str = None, timestamp: float = None):
        self.set(key, None, node_id, timestamp)

    def keys(self) -> builtins.set[str]:
        return {k for k, v in self.registers.items() if v.get() is not None}

    def items(self) -> dict[str, Any]:
        return {k: v.get() for k, v in self.registers.items() if v.get() is not None}

    def merge(self, other: 'LWWMap') -> 'LWWMap':
        result = LWWMap(self.node_id)
        all_keys = set(self.registers.keys()) | set(other.registers.keys())
        for key in all_keys:
            if key in self.registers and key in other.registers:
                result.registers[key] = self.registers[key].merge(other.registers[key])
            elif key in self.registers:
                result.registers[key] = self.registers[key]
            else:
                result.registers[key] = other.registers[key]
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "lww_map",
            "node_id": self.node_id,
            "registers": {k: v.to_dict() for k, v in self.registers.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'LWWMap':
        lww_map = cls(data.get("node_id", ""))
        for k, v in data.get("registers", {}).items():
            lww_map.registers[k] = LWWRegister.from_dict(v)
        return lww_map


class CRDTStore:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.crdts: dict[str, CRDT] = {}
        self.vector_clock = VectorClock()
        self.peers: dict[str, CRDTStore] = {}
        self._lock = asyncio.Lock()
        self._callbacks: dict[str, list[Callable]] = defaultdict(list)

    def register_crdt(self, name: str, crdt: CRDT):
        self.crdts[name] = crdt

    def get_crdt(self, name: str) -> CRDT | None:
        return self.crdts.get(name)

    def g_counter(self, name: str) -> GCounter:
        if name not in self.crdts:
            self.crdts[name] = GCounter(self.node_id)
        return self.crdts[name]

    def pn_counter(self, name: str) -> PNCounter:
        if name not in self.crdts:
            self.crdts[name] = PNCounter(self.node_id)
        return self.crdts[name]

    def g_set(self, name: str) -> GSet:
        if name not in self.crdts:
            self.crdts[name] = GSet(self.node_id)
        return self.crdts[name]

    def or_set(self, name: str) -> ORSet:
        if name not in self.crdts:
            self.crdts[name] = ORSet(self.node_id)
        return self.crdts[name]

    def lww_register(self, name: str) -> LWWRegister:
        if name not in self.crdts:
            self.crdts[name] = LWWRegister(self.node_id)
        return self.crdts[name]

    def lww_map(self, name: str) -> LWWMap:
        if name not in self.crdts:
            self.crdts[name] = LWWMap(self.node_id)
        return self.crdts[name]

    async def merge_from(self, other_store: 'CRDTStore'):
        async with self._lock:
            for name, other_crdt in other_store.crdts.items():
                if name in self.crdts:
                    self.crdts[name] = self.crdts[name].merge(other_crdt)
                else:
                    self.crdts[name] = other_crdt

            self.vector_clock.merge(other_store.vector_clock)
            await self._notify_callbacks()

    async def sync_with_peer(self, peer_id: str, peer_store: 'CRDTStore'):
        await self.merge_from(peer_store)

    def add_peer(self, peer_id: str, peer_store: 'CRDTStore'):
        self.peers[peer_id] = peer_store

    def remove_peer(self, peer_id: str):
        self.peers.pop(peer_id, None)

    def on_change(self, name: str, callback: Callable):
        self._callbacks[name].append(callback)

    async def _notify_callbacks(self):
        for name, crdt in self.crdts.items():
            for callback in self._callbacks.get(name, []):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(crdt)
                    else:
                        callback(crdt)
                except Exception:
                    pass

    def get_state(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "vector_clock": self.vector_clock.to_dict(),
            "crdts": {name: crdt.to_dict() for name, crdt in self.crdts.items()},
        }

    def load_state(self, state: dict[str, Any]):
        self.vector_clock = VectorClock.from_dict(state.get("vector_clock", {}))
        for name, crdt_data in state.get("crdts", {}).items():
            crdt_type = crdt_data.get("type")
            if crdt_type == "g_counter":
                self.crdts[name] = GCounter.from_dict(crdt_data)
            elif crdt_type == "pn_counter":
                self.crdts[name] = PNCounter.from_dict(crdt_data)
            elif crdt_type == "g_set":
                self.crdts[name] = GSet.from_dict(crdt_data)
            elif crdt_type == "or_set":
                self.crdts[name] = ORSet.from_dict(crdt_data)
            elif crdt_type == "lww_register":
                self.crdts[name] = LWWRegister.from_dict(crdt_data)
            elif crdt_type == "lww_map":
                self.crdts[name] = LWWMap.from_dict(crdt_data)


class CRDTCluster:
    def __init__(self, node_id: str):
        self.local_store = CRDTStore(node_id)
        self.peers: dict[str, CRDTStore] = {}

    def add_peer(self, peer_id: str, peer_store: CRDTStore):
        self.peers[peer_id] = peer_store
        self.local_store.add_peer(peer_id, peer_store)

    async def sync_all(self):
        for peer_id, peer_store in self.peers.items():
            await self.local_store.sync_with_peer(peer_id, peer_store)

    async def broadcast_operation(self, crdt_name: str, operation: str, *args, **kwargs):
        crdt = self.local_store.get_crdt(crdt_name)
        if crdt:
            getattr(crdt, operation)(*args, **kwargs)
            for peer_store in self.peers.values():
                await peer_store.merge_from(self.local_store)

    def get_local_store(self) -> CRDTStore:
        return self.local_store
