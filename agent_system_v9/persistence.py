"""
Persistence Layer - Redis Streams for EventBus/MessageBus, LMDB for ShadowGit
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class PersistenceBackend(Enum):
    REDIS_STREAMS = "redis_streams"
    LMDB = "lmdb"
    IN_MEMORY = "in_memory"


@dataclass
class PersistenceConfig:
    backend: PersistenceBackend = PersistenceBackend.REDIS_STREAMS
    redis_url: str = "redis://localhost:6379"
    redis_stream_maxlen: int = 10000
    lmdb_path: str = "/tmp/agent_system_v9_lmdb"
    lmdb_map_size: int = 1_000_000_000  # 1GB
    batch_size: int = 100
    flush_interval: float = 1.0


class BasePersistence(ABC):
    """Abstract base class for persistence backends."""

    @abstractmethod
    async def initialize(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def append(self, stream: str, data: dict[str, Any]) -> str:
        pass

    @abstractmethod
    async def read(self, stream: str, start: str = "-", count: int = 100) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    async def delete(self, stream: str, ids: list[str]) -> int:
        pass


class RedisStreamsPersistence(BasePersistence):
    """Redis Streams-based persistence for EventBus and MessageBus."""

    def __init__(self, config: PersistenceConfig):
        self.config = config
        self._client: Optional[redis.Redis] = None
        self._consumer_groups: dict[str, str] = {}

    async def initialize(self) -> None:
        self._client = redis.from_url(
            self.config.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        await self._client.ping()
        logger.info("Redis Streams persistence initialized")

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def append(self, stream: str, data: dict[str, Any]) -> str:
        if not self._client:
            raise RuntimeError("Persistence not initialized")
        # Add metadata
        data["_timestamp"] = time.time()
        data["_id"] = str(uuid.uuid4())
        msg_id = await self._client.xadd(
            stream,
            data,
            maxlen=self.config.redis_stream_maxlen,
            approximate=True
        )
        return msg_id

    async def read(self, stream: str, start: str = "-", count: int = 100) -> list[dict[str, Any]]:
        if not self._client:
            raise RuntimeError("Persistence not initialized")
        messages = await self._client.xrange(stream, min=start, count=count)
        return [msg[1] for msg in messages]

    async def read_new(self, stream: str, group: str, consumer: str, count: int = 100, block: int = 5000) -> list[dict[str, Any]]:
        """Read new messages using consumer group."""
        if not self._client:
            raise RuntimeError("Persistence not initialized")
        try:
            await self._client.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        messages = await self._client.xreadgroup(
            group, consumer,
            {stream: ">"},
            count=count,
            block=block
        )
        result = []
        for stream_name, msgs in messages:
            for msg_id, data in msgs:
                data["_msg_id"] = msg_id
                result.append(data)
        return result

    async def ack(self, stream: str, group: str, msg_ids: list[str]) -> int:
        if not self._client:
            raise RuntimeError("Persistence not initialized")
        return await self._client.xack(stream, group, *msg_ids)

    async def delete(self, stream: str, ids: list[str]) -> int:
        if not self._client:
            raise RuntimeError("Persistence not initialized")
        return await self._client.xdel(stream, *ids)


class LMDBPersistence(BasePersistence):
    """LMDB-based persistence for ShadowGit."""

    def __init__(self, config: PersistenceConfig):
        self.config = config
        self._env = None
        self._dbs: dict[str, Any] = {}

    async def initialize(self) -> None:
        try:
            import lmdb
        except ImportError:
            raise RuntimeError("LMDB not available. Install with: pip install lmdb")

        import os
        os.makedirs(self.config.lmdb_path, exist_ok=True)

        self._env = lmdb.open(
            self.config.lmdb_path,
            map_size=self.config.lmdb_map_size,
            max_dbs=100
        )
        logger.info(f"LMDB persistence initialized at {self.config.lmdb_path}")

    async def close(self) -> None:
        if self._env:
            self._env.close()
            self._env = None

    def _get_db(self, name: str):
        if name not in self._dbs:
            with self._env.begin(write=True) as txn:
                self._dbs[name] = self._env.open_db(name.encode(), txn=txn, create=True)
        return self._dbs[name]

    async def append(self, stream: str, data: dict[str, Any]) -> str:
        if not self._env:
            raise RuntimeError("Persistence not initialized")
        import lmdb
        key = str(uuid.uuid4()).encode()
        value = json.dumps(data).encode()
        db = self._get_db(stream)
        with self._env.begin(db=db, write=True) as txn:
            txn.put(key, value)
        return key.decode()

    async def read(self, stream: str, start: str = "-", count: int = 100) -> list[dict[str, Any]]:
        if not self._env:
            raise RuntimeError("Persistence not initialized")
        db = self._get_db(stream)
        result = []
        with self._env.begin(db=db) as txn:
            cursor = txn.cursor()
            if start != "-":
                cursor.set_range(start.encode())
            else:
                cursor.first()
            for _ in range(count):
                if not cursor.item():
                    break
                key, value = cursor.item()
                result.append(json.loads(value.decode()))
                if not cursor.next():
                    break
        return result

    async def get(self, stream: str, key: str) -> dict[str, Any] | None:
        if not self._env:
            raise RuntimeError("Persistence not initialized")
        db = self._get_db(stream)
        with self._env.begin(db=db) as txn:
            value = txn.get(key.encode(), db=db)
            if value:
                return json.loads(value.decode())
        return None

    async def put(self, stream: str, key: str, data: dict[str, Any]) -> None:
        if not self._env:
            raise RuntimeError("Persistence not initialized")
        db = self._get_db(stream)
        with self._env.begin(db=db, write=True) as txn:
            txn.put(key.encode(), json.dumps(data).encode())

    async def delete(self, stream: str, ids: list[str]) -> int:
        if not self._env:
            raise RuntimeError("Persistence not initialized")
        db = self._get_db(stream)
        deleted = 0
        with self._env.begin(db=db, write=True) as txn:
            for id_str in ids:
                if txn.delete(id_str.encode(), db=db):
                    deleted += 1
        return deleted


class InMemoryPersistence(BasePersistence):
    """In-memory persistence for testing."""

    def __init__(self, config: PersistenceConfig):
        self.config = config
        self._streams: dict[str, list[dict[str, Any]]] = {}

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def append(self, stream: str, data: dict[str, Any]) -> str:
        if stream not in self._streams:
            self._streams[stream] = []
        msg_id = str(uuid.uuid4())
        data["_id"] = msg_id
        data["_timestamp"] = time.time()
        self._streams[stream].append(data)
        if len(self._streams[stream]) > self.config.redis_stream_maxlen:
            self._streams[stream] = self._streams[stream][-self.config.redis_stream_maxlen:]
        return msg_id

    async def read(self, stream: str, start: str = "-", count: int = 100) -> list[dict[str, Any]]:
        if stream not in self._streams:
            return []
        data = self._streams[stream]
        return data[-count:]

    async def delete(self, stream: str, ids: list[str]) -> int:
        if stream not in self._streams:
            return 0
        original_len = len(self._streams[stream])
        self._streams[stream] = [d for d in self._streams[stream] if d.get("_id") not in ids]
        return original_len - len(self._streams[stream])


class PersistenceManager:
    """Manages persistence backends for different subsystems."""

    def __init__(self, config: PersistenceConfig = None):
        self.config = config or PersistenceConfig()
        self._backends: dict[str, BasePersistence] = {}
        self._default_backend: BasePersistence | None = None

    async def initialize(self) -> None:
        """Initialize all backends."""
        if self.config.backend == PersistenceBackend.REDIS_STREAMS:
            self._default_backend = RedisStreamsPersistence(self.config)
        elif self.config.backend == PersistenceBackend.LMDB:
            self._default_backend = LMDBPersistence(self.config)
        else:
            self._default_backend = InMemoryPersistence(self.config)

        await self._default_backend.initialize()
        logger.info(f"Persistence manager initialized with {self.config.backend.value}")

    async def close(self) -> None:
        if self._default_backend:
            await self._default_backend.close()

    def get_backend(self, name: str = "default") -> BasePersistence:
        if name not in self._backends:
            if name == "default" or self._default_backend is None:
                raise ValueError("Default backend not initialized")
            self._backends[name] = self._default_backend
        return self._backends.get(name, self._default_backend)

    @property
    def default(self) -> BasePersistence:
        if self._default_backend is None:
            raise RuntimeError("Persistence not initialized")
        return self._default_backend


# Convenience functions
_persistence_manager: Optional[PersistenceManager] = None


async def get_persistence_manager(config: PersistenceConfig = None) -> PersistenceManager:
    """Get global persistence manager."""
    global _persistence_manager
    if _persistence_manager is None:
        _persistence_manager = PersistenceManager(config)
        await _persistence_manager.initialize()
    return _persistence_manager


async def close_persistence_manager() -> None:
    """Close global persistence manager."""
    global _persistence_manager
    if _persistence_manager:
        await _persistence_manager.close()
        _persistence_manager = None


__all__ = [
    "PersistenceBackend",
    "PersistenceConfig",
    "BasePersistence",
    "RedisStreamsPersistence",
    "LMDBPersistence",
    "InMemoryPersistence",
    "PersistenceManager",
    "get_persistence_manager",
    "close_persistence_manager",
]