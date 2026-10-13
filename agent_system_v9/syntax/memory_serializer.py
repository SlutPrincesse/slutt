"""
Persistent Memory Serialization Engine - Logs execution insights and fix strategies to persistent store
"""
import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SerializedMemory:
    memory_id: str
    timestamp: float
    memory_type: str
    content: dict[str, Any]
    tags: list[str] = field(default_factory=list)
    importance: float = 1.0
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class MemorySerializer:
    def __init__(self, storage_dir: str = "./agent_memory",
                 max_entries: int = 10000, serialization_interval: float = 60.0):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.serialization_interval = serialization_interval

        self._memories: dict[str, SerializedMemory] = {}
        self._lock = threading.RLock()
        self._running = False
        self._serializer_thread: threading.Thread | None = None
        self._index: dict[str, list[str]] = {}  # tag -> memory_ids
        self._load_existing()

    def _load_existing(self):
        for f in self.storage_dir.glob("memory_*.json"):
            try:
                with Path(f).open() as fp:
                    data = json.load(fp)
                memory = SerializedMemory(**data)
                self._memories[memory.memory_id] = memory
                for tag in memory.tags:
                    if tag not in self._index:
                        self._index[tag] = []
                    self._index[tag].append(memory.memory_id)
            except Exception:
                pass

    def start(self):
        if self._running:
            return
        self._running = True
        self._serializer_thread = threading.Thread(target=self._serialization_loop, daemon=True)
        self._serializer_thread.start()

    def stop(self):
        self._running = False
        self._save_all()
        if self._serializer_thread:
            self._serializer_thread.join(timeout=5.0)

    def store(self, memory_type: str, content: dict[str, Any],
              tags: list[str] = None, importance: float = 1.0,
              metadata: dict[str, Any] = None) -> str:

        memory_id = hashlib.sha256(
            f"{memory_type}{content}{time.time()}".encode()
        ).hexdigest()[:16]

        memory = SerializedMemory(
            memory_id=memory_id,
            timestamp=time.time(),
            memory_type=memory_type,
            content=content,
            tags=tags or [],
            importance=importance,
            metadata=metadata or {}
        )

        with self._lock:
            self._memories[memory_id] = memory
            for tag in memory.tags:
                if tag not in self._index:
                    self._index[tag] = []
                self._index[tag].append(memory_id)

        return memory_id

    def retrieve(self, memory_id: str) -> SerializedMemory | None:
        with self._lock:
            memory = self._memories.get(memory_id)
            if memory:
                memory.access_count += 1
                memory.last_accessed = time.time()
            return memory

    def query(self, tags: list[str] = None, memory_type: str = None,
              min_importance: float = 0.0, limit: int = 100) -> list[SerializedMemory]:

        with self._lock:
            candidates = list(self._memories.values())

        if tags:
            candidates = [m for m in candidates if any(t in m.tags for t in tags)]

        if memory_type:
            candidates = [m for m in candidates if m.memory_type == memory_type]

        candidates = [m for m in candidates if m.importance >= min_importance]
        candidates.sort(key=lambda m: -m.importance)

        return candidates[:limit]

    def update_importance(self, memory_id: str, importance: float):
        with self._lock:
            if memory_id in self._memories:
                self._memories[memory_id].importance = importance

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            memory = self._memories.pop(memory_id, None)
            if memory:
                for tag in memory.tags:
                    if tag in self._index:
                        self._index[tag] = [mid for mid in self._index[tag] if mid != memory_id]
                return True
        return False

    def _serialization_loop(self):
        while self._running:
            time.sleep(self.serialization_interval)
            self._save_all()

    def _save_all(self):
        with self._lock:
            memories = list(self._memories.values())

        for memory in memories:
            try:
                filepath = self.storage_dir / f"memory_{memory.memory_id}.json"
                with Path(filepath).open('w') as f:
                    json.dump(asdict(memory), f, indent=2)
            except Exception:
                pass

        # Cleanup old
        self._cleanup_old()

    def _cleanup_old(self):
        files = sorted(self.storage_dir.glob("memory_*.json"),
                      key=lambda p: p.stat().st_mtime)
        while len(files) > self.max_entries:
            files.pop(0).unlink(missing_ok=True)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_memories": len(self._memories),
                "by_type": {},
                "by_tag": {tag: len(ids) for tag, ids in self._index.items()},
                "storage_size_mb": sum(f.stat().st_size for f in self.storage_dir.glob("*.json")) / 1024 / 1024
            }


_memory_serializer: MemorySerializer | None = None


def get_memory_serializer() -> MemorySerializer:
    global _memory_serializer
    if _memory_serializer is None:
        from ..core.config import config
        interval = config.get_param("syntax", "memory_serialization_interval", 60)
        _memory_serializer = MemorySerializer(serialization_interval=interval)
        _memory_serializer.start()
    return _memory_serializer
