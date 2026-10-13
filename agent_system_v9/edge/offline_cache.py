"""
Offline Cache - Local caching for offline operation
"""
import asyncio
import json
import pickle
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CacheStrategy(Enum):
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"
    TTL = "ttl"
    ADAPTIVE = "adaptive"


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    ttl: float | None = None
    size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl

    def touch(self):
        self.accessed_at = time.time()
        self.access_count += 1


@dataclass
class CacheConfig:
    max_size: int = 1000
    max_memory_mb: int = 100
    default_ttl: float = 3600
    strategy: CacheStrategy = CacheStrategy.LRU
    persist_to_disk: bool = True
    db_path: str = "cache.db"


class MemoryCache:
    def __init__(self, config: CacheConfig):
        self.config = config
        self.cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self.cache.get(key)
            if entry and not entry.is_expired():
                entry.touch()
                self.hits += 1
                return entry.value
            if entry:
                del self.cache[key]
            self.misses += 1
            return None

    async def set(self, key: str, value: Any, ttl: float = None, metadata: dict = None):
        async with self._lock:
            if len(self.cache) >= self.config.max_size:
                await self._evict()

            entry = CacheEntry(
                key=key,
                value=value,
                ttl=ttl or self.config.default_ttl,
                size=self._estimate_size(value),
                metadata=metadata or {},
            )
            self.cache[key] = entry

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                return True
        return False

    async def clear(self):
        async with self._lock:
            self.cache.clear()

    async def _evict(self):
        if self.config.strategy == CacheStrategy.LRU:
            oldest = min(self.cache.items(), key=lambda x: x[1].accessed_at)
        elif self.config.strategy == CacheStrategy.LFU:
            oldest = min(self.cache.items(), key=lambda x: x[1].access_count)
        elif self.config.strategy == CacheStrategy.FIFO:
            oldest = min(self.cache.items(), key=lambda x: x[1].created_at)
        elif self.config.strategy == CacheStrategy.TTL:
            expired = [k for k, v in self.cache.items() if v.is_expired()]
            if expired:
                oldest = (expired[0], self.cache[expired[0]])
            else:
                oldest = min(self.cache.items(), key=lambda x: x[1].created_at)
        else:
            oldest = min(self.cache.items(), key=lambda x: x[1].accessed_at)

        del self.cache[oldest[0]]

    def _estimate_size(self, value: Any) -> int:
        try:
            return len(pickle.dumps(value))
        except Exception:
            return 1024

    async def get_stats(self) -> dict[str, Any]:
        async with self._lock:
            total_size = sum(e.size for e in self.cache.values())
            return {
                "entries": len(self.cache),
                "total_size_bytes": total_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": self.hits / max(self.hits + self.misses, 1),
            }


class DiskCache:
    def __init__(self, config: CacheConfig):
        self.config = config
        self.db_path = Path(config.db_path)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value BLOB,
                created_at REAL,
                accessed_at REAL,
                access_count INTEGER,
                ttl REAL,
                size INTEGER,
                metadata TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON cache(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_accessed_at ON cache(accessed_at)")
        conn.commit()
        conn.close()

    async def get(self, key: str) -> Any | None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT value, created_at, ttl, accessed_at, access_count FROM cache WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            value, created_at, ttl, accessed_at, access_count = row
            if ttl and time.time() - created_at > ttl:
                await self.delete(key)
                return None

            await self._touch(key, access_count + 1)
            return pickle.loads(value)
        return None

    async def set(self, key: str, value: Any, ttl: float = None, metadata: dict = None):
        data = pickle.dumps(value)
        size = len(data)
        now = time.time()
        ttl = ttl or self.config.default_ttl

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO cache (key, value, created_at, accessed_at, access_count, ttl, size, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (key, data, now, now, 1, ttl, size, json.dumps(metadata or {})))
        conn.commit()
        conn.close()

    async def delete(self, key: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    async def clear(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM cache")
        conn.commit()
        conn.close()

    async def _touch(self, key: str, access_count: int):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE cache SET accessed_at = ?, access_count = ? WHERE key = ?",
            (time.time(), access_count, key)
        )
        conn.commit()
        conn.close()

    async def cleanup_expired(self) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM cache WHERE ttl IS NOT NULL AND created_at + ttl < ?", (time.time(),))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted

    async def get_stats(self) -> dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT COUNT(*), SUM(size) FROM cache")
        count, total_size = cursor.fetchone()
        conn.close()
        return {
            "entries": count or 0,
            "total_size_bytes": total_size or 0,
        }


class OfflineCache:
    def __init__(self, config: CacheConfig = None):
        self.config = config or CacheConfig()
        self.memory_cache = MemoryCache(self.config)
        self.disk_cache = DiskCache(self.config) if self.config.persist_to_disk else None
        self._running = False
        self._cleanup_task: asyncio.Task | None = None

    async def start(self):
        self._running = True
        if self.disk_cache:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def get(self, key: str) -> Any | None:
        value = await self.memory_cache.get(key)
        if value is not None:
            return value

        if self.disk_cache:
            value = await self.disk_cache.get(key)
            if value is not None:
                await self.memory_cache.set(key, value)
                return value

        return None

    async def set(self, key: str, value: Any, ttl: float = None, metadata: dict = None):
        await self.memory_cache.set(key, value, ttl, metadata)
        if self.disk_cache:
            await self.disk_cache.set(key, value, ttl, metadata)

    async def delete(self, key: str) -> bool:
        mem_deleted = await self.memory_cache.delete(key)
        disk_deleted = await self.disk_cache.delete(key) if self.disk_cache else False
        return mem_deleted or disk_deleted

    async def clear(self):
        await self.memory_cache.clear()
        if self.disk_cache:
            await self.disk_cache.clear()

    async def _cleanup_loop(self):
        while self._running:
            await asyncio.sleep(3600)
            if self.disk_cache:
                await self.disk_cache.cleanup_expired()

    async def get_stats(self) -> dict[str, Any]:
        mem_stats = await self.memory_cache.get_stats()
        disk_stats = await self.disk_cache.get_stats() if self.disk_cache else {}
        return {
            "memory": mem_stats,
            "disk": disk_stats,
        }

    async def prefetch(self, keys: list[str], loader: Callable[[str], Awaitable[Any]]):
        for key in keys:
            if await self.get(key) is None:
                try:
                    value = await loader(key)
                    await self.set(key, value)
                except Exception:
                    pass


class WriteThroughCache(OfflineCache):
    async def set(self, key: str, value: Any, ttl: float = None, metadata: dict = None, writer: Callable = None):
        if writer:
            try:
                await writer(key, value)
            except Exception:
                pass
        await super().set(key, value, ttl, metadata)


class WriteBehindCache(OfflineCache):
    def __init__(self, config: CacheConfig = None, flush_interval: float = 10.0):
        super().__init__(config)
        self.flush_interval = flush_interval
        self.write_queue: asyncio.Queue = asyncio.Queue()
        self._flush_task: asyncio.Task | None = None

    async def start(self):
        await super().start()
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self):
        await super().stop()
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

    async def set(self, key: str, value: Any, ttl: float = None, metadata: dict = None, writer: Callable = None):
        await super().set(key, value, ttl, metadata)
        if writer:
            await self.write_queue.put((key, value, writer))

    async def _flush_loop(self):
        while self._running:
            await asyncio.sleep(self.flush_interval)
            await self._flush()

    async def _flush(self):
        while not self.write_queue.empty():
            key, value, writer = await self.write_queue.get()
            try:
                await writer(key, value)
            except Exception:
                await self.write_queue.put((key, value, writer))
                break


class CacheWarmer:
    def __init__(self, cache: OfflineCache):
        self.cache = cache

    async def warm(self, keys: list[str], loader: Callable[[str], Awaitable[Any]], concurrency: int = 10):
        semaphore = asyncio.Semaphore(concurrency)

        async def load(key: str):
            async with semaphore:
                if await self.cache.get(key) is None:
                    try:
                        value = await loader(key)
                        await self.cache.set(key, value)
                    except Exception:
                        pass

        await asyncio.gather(*[load(key) for key in keys])

    async def warm_from_pattern(self, pattern: str, loader: Callable[[str], Awaitable[Any]], max_keys: int = 100):
        keys = [f"{pattern}:{i}" for i in range(max_keys)]
        await self.warm(keys, loader)
