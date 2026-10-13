"""
Idempotent Consumer - Deduplication and exactly-once processing
"""
import asyncio
import hashlib
import time
import uuid
from typing import Dict, List, Optional, Any, Callable, Awaitable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from abc import ABC, abstractmethod


class DeduplicationStrategy(Enum):
    IN_MEMORY = "in_memory"
    REDIS = "redis"
    DATABASE = "database"
    CUSTOM = "custom"


@dataclass
class ProcessingResult:
    success: bool
    result: Any = None
    error: Optional[str] = None
    processed_at: float = field(default_factory=time.time)
    deduplicated: bool = False


@dataclass
class IdempotencyKey:
    key: str
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    result: Optional[ProcessingResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class DeduplicationStore(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[IdempotencyKey]:
        pass

    @abstractmethod
    async def set(self, key: IdempotencyKey) -> bool:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        pass


class InMemoryDeduplicationStore(DeduplicationStore):
    def __init__(self, max_size: int = 10000, default_ttl: float = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.store: Dict[str, IdempotencyKey] = {}
        self._lock = asyncio.Lock()
        self._access_order: List[str] = []

    async def get(self, key: str) -> Optional[IdempotencyKey]:
        async with self._lock:
            item = self.store.get(key)
            if item and item.is_expired():
                del self.store[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return None
            if item:
                self._access_order.remove(key)
                self._access_order.append(key)
            return item

    async def set(self, item: IdempotencyKey) -> bool:
        async with self._lock:
            if len(self.store) >= self.max_size and item.key not in self.store:
                oldest = self._access_order.pop(0)
                self.store.pop(oldest, None)
            
            if item.expires_at is None:
                item.expires_at = time.time() + self.default_ttl
            
            self.store[item.key] = item
            if item.key in self._access_order:
                self._access_order.remove(item.key)
            self._access_order.append(item.key)
            return True

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self.store:
                del self.store[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return True
        return False

    async def cleanup_expired(self) -> int:
        async with self._lock:
            now = time.time()
            expired = [k for k, v in self.store.items() if v.is_expired()]
            for k in expired:
                del self.store[k]
                if k in self._access_order:
                    self._access_order.remove(k)
            return len(expired)


class RedisDeduplicationStore(DeduplicationStore):
    def __init__(self, redis_url: str = "redis://localhost:6379", prefix: str = "idempotency:"):
        self.redis_url = redis_url
        self.prefix = prefix
        self._redis = None

    async def connect(self):
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url)
        except ImportError:
            raise RuntimeError("redis not installed")

    async def get(self, key: str) -> Optional[IdempotencyKey]:
        if not self._redis:
            await self.connect()
        data = await self._redis.get(f"{self.prefix}{key}")
        if data:
            import json
            return IdempotencyKey(**json.loads(data))
        return None

    async def set(self, item: IdempotencyKey) -> bool:
        if not self._redis:
            await self.connect()
        import json
        ttl = int(item.expires_at - time.time()) if item.expires_at else 3600
        await self._redis.setex(f"{self.prefix}{item.key}", ttl, json.dumps(item.__dict__))
        return True

    async def delete(self, key: str) -> bool:
        if not self._redis:
            await self.connect()
        return await self._redis.delete(f"{self.prefix}{key}") > 0

    async def cleanup_expired(self) -> int:
        return 0


class IdempotentConsumer:
    def __init__(
        self,
        store: DeduplicationStore,
        key_generator: Optional[Callable] = None,
    ):
        self.store = store
        self.key_generator = key_generator or self._default_key_generator
        self._processing: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def _default_key_generator(self, message: Any) -> str:
        if isinstance(message, dict):
            return hashlib.sha256(str(sorted(message.items())).encode()).hexdigest()
        return hashlib.sha256(str(message).encode()).hexdigest()

    async def process(
        self,
        message: Any,
        handler: Callable,
        ttl: float = 3600,
    ) -> ProcessingResult:
        key = self.key_generator(message)
        
        existing = await self.store.get(key)
        if existing and existing.result:
            return ProcessingResult(
                success=existing.result.success,
                result=existing.result.result,
                error=existing.result.error,
                deduplicated=True,
            )

        async with self._lock:
            existing = await self.store.get(key)
            if existing and existing.result:
                return ProcessingResult(
                    success=existing.result.success,
                    result=existing.result.result,
                    error=existing.result.error,
                    deduplicated=True,
                )

            future = asyncio.get_event_loop().create_future()
            self._processing[key] = future

        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(message)
            else:
                result = handler(message)

            processing_result = ProcessingResult(success=True, result=result)
        except Exception as e:
            processing_result = ProcessingResult(success=False, error=str(e))

        idempotency_key = IdempotencyKey(
            key=key,
            expires_at=time.time() + ttl,
            result=processing_result,
        )
        await self.store.set(idempotency_key)

        async with self._lock:
            self._processing.pop(key, None)

        return processing_result

    async def process_with_retry(
        self,
        message: Any,
        handler: Callable,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        ttl: float = 3600,
    ) -> ProcessingResult:
        for attempt in range(max_retries + 1):
            result = await self.process(message, handler, ttl)
            if result.success or result.deduplicated:
                return result
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * (attempt + 1))
        return result


class ExactlyOnceProcessor:
    def __init__(
        self,
        store: DeduplicationStore,
        key_generator: Optional[Callable] = None,
    ):
        self.consumer = IdempotentConsumer(store, key_generator)
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._tasks: List[asyncio.Task] = []

    def register_handler(self, topic: str, handler: Callable):
        self._handlers[topic] = handler

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def process_message(self, topic: str, message: Any, **kwargs) -> ProcessingResult:
        handler = self._handlers.get(topic)
        if not handler:
            return ProcessingResult(success=False, error=f"No handler for topic: {topic}")
        
        return await self.consumer.process_with_retry(message, handler, **kwargs)


class MessageDeduplicator:
    def __init__(
        self,
        store: DeduplicationStore,
        key_extractor: Optional[Callable] = None,
    ):
        self.store = store
        self.key_extractor = key_extractor or (lambda m: m.get("id", str(uuid.uuid4())))

    async def is_duplicate(self, message: Any) -> bool:
        key = self.key_extractor(message)
        existing = await self.store.get(key)
        return existing is not None

    async def mark_processed(self, message: Any, result: Any = None, ttl: float = 3600) -> bool:
        key = self.key_extractor(message)
        item = IdempotencyKey(
            key=key,
            expires_at=time.time() + ttl,
            result=ProcessingResult(success=True, result=result),
        )
        return await self.store.set(item)

    async def filter_batch(self, messages: List[Any]) -> List[Any]:
        unique = []
        for msg in messages:
            if not await self.is_duplicate(msg):
                unique.append(msg)
        return unique


class TransactionalOutbox:
    def __init__(
        self,
        store: DeduplicationStore,
        publisher: Callable,
    ):
        self.store = store
        self.publisher = publisher
        self.outbox: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def save(self, topic: str, message: Any, key: str = None) -> str:
        key = key or hashlib.sha256(f"{topic}:{message}".encode()).hexdigest()
        async with self._lock:
            self.outbox[key] = {
                "topic": topic,
                "message": message,
                "created_at": time.time(),
                "published": False,
            }
        return key

    async def publish_pending(self) -> int:
        published = 0
        async with self._lock:
            for key, entry in list(self.outbox.items()):
                if not entry["published"]:
                    try:
                        await self.publisher(entry["topic"], entry["message"])
                        entry["published"] = True
                        published += 1
                    except Exception:
                        pass
        return published

    async def cleanup_published(self, max_age: float = 86400) -> int:
        async with self._lock:
            now = time.time()
            removed = 0
            for key in list(self.outbox.keys()):
                if self.outbox[key]["published"] and now - self.outbox[key]["created_at"] > max_age:
                    del self.outbox[key]
                    removed += 1
        return removed


class DistributedLock:
    def __init__(self, store: DeduplicationStore, lock_ttl: float = 30.0):
        self.store = store
        self.lock_ttl = lock_ttl
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, resource: str, owner: str = None) -> bool:
        owner = owner or str(uuid.uuid4())
        key = f"lock:{resource}:{owner}"
        
        item = IdempotencyKey(
            key=key,
            expires_at=time.time() + self.lock_ttl,
            metadata={"resource": resource, "owner": owner},
        )
        
        return await self.store.set(item)

    async def release(self, resource: str, owner: str = None):
        owner = owner or str(uuid.uuid4())
        key = f"lock:{resource}:{owner}"
        await self.store.delete(key)

    async def extend(self, resource: str, owner: str = None, additional_ttl: float = 30.0) -> bool:
        owner = owner or str(uuid.uuid4())
        key = f"lock:{resource}:{owner}"
        
        existing = await self.store.get(key)
        if existing:
            existing.expires_at = time.time() + additional_ttl
            return await self.store.set(existing)
        return False

    def get_lock(self, resource: str) -> asyncio.Lock:
        return self._locks[resource]