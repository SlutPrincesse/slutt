"""
Deferred Queue - Queue management for offline/deferred operations
"""
import asyncio
import hashlib
import json
import time
import uuid
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict
import sqlite3


class QueueStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class Priority(Enum):
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class QueueItem:
    item_id: str
    queue_name: str
    payload: Any
    priority: Priority = Priority.NORMAL
    status: QueueStatus = QueueStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "queue_name": self.queue_name,
            "payload": self.payload,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueItem':
        return cls(
            item_id=data["item_id"],
            queue_name=data["queue_name"],
            payload=data["payload"],
            priority=Priority(data.get("priority", Priority.NORMAL.value)),
            status=QueueStatus(data.get("status", QueueStatus.PENDING.value)),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class QueueConfig:
    max_size: int = 10000
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    max_retry_delay: float = 300.0
    dead_letter_after_retries: bool = True
    persist: bool = True
    db_path: str = "queue.db"


class DeferredQueue:
    def __init__(self, name: str, config: QueueConfig = None):
        self.name = name
        self.config = config or QueueConfig()
        self.config.db_path = self.config.db_path.replace(".db", f"_{name}.db")
        
        self.memory_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=self.config.max_size)
        self.processing: Dict[str, QueueItem] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._handler: Optional[Callable] = None
        self.stats = {
            "enqueued": 0,
            "dequeued": 0,
            "completed": 0,
            "failed": 0,
            "retried": 0,
            "dead_letter": 0,
        }
        
        if self.config.persist:
            self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.config.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                item_id TEXT PRIMARY KEY,
                queue_name TEXT,
                payload TEXT,
                priority INTEGER,
                status TEXT,
                created_at REAL,
                started_at REAL,
                completed_at REAL,
                retry_count INTEGER,
                max_retries INTEGER,
                error TEXT,
                metadata TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON queue(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_priority ON queue(priority)")
        conn.commit()
        conn.close()

    def register_handler(self, handler: Callable):
        self._handler = handler

    async def enqueue(
        self,
        payload: Any,
        priority: Priority = Priority.NORMAL,
        max_retries: int = None,
        metadata: Dict = None,
    ) -> str:
        item_id = str(uuid.uuid4())
        item = QueueItem(
            item_id=item_id,
            queue_name=self.name,
            payload=payload,
            priority=priority,
            max_retries=max_retries or self.config.max_retries,
            metadata=metadata or {},
        )
        
        if self.config.persist:
            await self._persist_item(item)
        
        await self.memory_queue.put((-priority.value, time.time(), item))
        self.stats["enqueued"] += 1
        
        return item_id

    async def _persist_item(self, item: QueueItem):
        conn = sqlite3.connect(self.config.db_path)
        conn.execute("""
            INSERT INTO queue (item_id, queue_name, payload, priority, status, created_at, 
                             started_at, completed_at, retry_count, max_retries, error, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.item_id, item.queue_name, json.dumps(item.payload), item.priority.value,
            item.status.value, item.created_at, item.started_at, item.completed_at,
            item.retry_count, item.max_retries, item.error, json.dumps(item.metadata)
        ))
        conn.commit()
        conn.close()

    async def _update_item(self, item: QueueItem):
        if not self.config.persist:
            return
        conn = sqlite3.connect(self.config.db_path)
        conn.execute("""
            UPDATE queue SET status = ?, started_at = ?, completed_at = ?, 
                          retry_count = ?, error = ?, metadata = ?
            WHERE item_id = ?
        """, (
            item.status.value, item.started_at, item.completed_at,
            item.retry_count, item.error, json.dumps(item.metadata), item.item_id
        ))
        conn.commit()
        conn.close()

    async def dequeue(self, timeout: float = None) -> Optional[QueueItem]:
        try:
            if timeout:
                _, _, item = await asyncio.wait_for(self.memory_queue.get(), timeout=timeout)
            else:
                _, _, item = await self.memory_queue.get()
            
            async with self._lock:
                item.status = QueueStatus.PROCESSING
                item.started_at = time.time()
                self.processing[item.item_id] = item
                await self._update_item(item)
            
            self.stats["dequeued"] += 1
            return item
        except asyncio.TimeoutError:
            return None

    async def complete(self, item: QueueItem, result: Any = None):
        async with self._lock:
            item.status = QueueStatus.COMPLETED
            item.completed_at = time.time()
            if item.item_id in self.processing:
                del self.processing[item.item_id]
            await self._update_item(item)
        
        self.stats["completed"] += 1

    async def fail(self, item: QueueItem, error: str):
        async with self._lock:
            item.error = error
            item.retry_count += 1
            
            if item.retry_count >= item.max_retries:
                if self.config.dead_letter_after_retries:
                    item.status = QueueStatus.DEAD_LETTER
                    self.stats["dead_letter"] += 1
                else:
                    item.status = QueueStatus.FAILED
                    self.stats["failed"] += 1
            else:
                item.status = QueueStatus.RETRYING
                self.stats["retried"] += 1
            
            if item.item_id in self.processing:
                del self.processing[item.item_id]
            
            await self._update_item(item)
            
            if item.status == QueueStatus.RETRYING:
                await self._schedule_retry(item)

    async def _schedule_retry(self, item: QueueItem):
        delay = min(
            self.config.retry_delay * (self.config.retry_backoff ** (item.retry_count - 1)),
            self.config.max_retry_delay,
        )
        
        async def retry():
            await asyncio.sleep(delay)
            item.status = QueueStatus.PENDING
            item.started_at = None
            await self._update_item(item)
            await self.memory_queue.put((-item.priority.value, time.time(), item))
        
        asyncio.create_task(retry())

    async def start_worker(self, concurrency: int = 1):
        if not self._handler:
            raise ValueError("No handler registered")
        
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop(concurrency))

    async def stop_worker(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _worker_loop(self, concurrency: int):
        semaphore = asyncio.Semaphore(concurrency)
        
        async def process_item():
            async with semaphore:
                item = await self.dequeue()
                if not item:
                    return
                
                try:
                    if asyncio.iscoroutinefunction(self._handler):
                        await self._handler(item.payload)
                    else:
                        await asyncio.get_event_loop().run_in_executor(None, self._handler, item.payload)
                    await self.complete(item)
                except Exception as e:
                    await self.fail(item, str(e))
        
        while self._running:
            tasks = [asyncio.create_task(process_item()) for _ in range(concurrency)]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def get_item(self, item_id: str) -> Optional[QueueItem]:
        async with self._lock:
            if item_id in self.processing:
                return self.processing[item_id]
        
        if self.config.persist:
            conn = sqlite3.connect(self.config.db_path)
            cursor = conn.execute("SELECT * FROM queue WHERE item_id = ?", (item_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return self._row_to_item(row)
        return None

    def _row_to_item(self, row) -> QueueItem:
        return QueueItem(
            item_id=row[0],
            queue_name=row[1],
            payload=json.loads(row[2]),
            priority=Priority(row[3]),
            status=QueueStatus(row[4]),
            created_at=row[5],
            started_at=row[6],
            completed_at=row[7],
            retry_count=row[8],
            max_retries=row[9],
            error=row[10],
            metadata=json.loads(row[11]) if row[11] else {},
        )

    async def get_stats(self) -> Dict[str, Any]:
        async with self._lock:
            pending = self.memory_queue.qsize()
            return {
                "queue_name": self.name,
                "pending": pending,
                "processing": len(self.processing),
                **self.stats,
            }

    async def clear(self):
        async with self._lock:
            while not self.memory_queue.empty():
                try:
                    self.memory_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self.processing.clear()
        
        if self.config.persist:
            conn = sqlite3.connect(self.config.db_path)
            conn.execute("DELETE FROM queue")
            conn.commit()
            conn.close()

    async def replay_dead_letter(self) -> int:
        if not self.config.persist:
            return 0
        
        conn = sqlite3.connect(self.config.db_path)
        cursor = conn.execute("SELECT * FROM queue WHERE status = ?", (QueueStatus.DEAD_LETTER.value,))
        rows = cursor.fetchall()
        conn.close()
        
        count = 0
        for row in rows:
            item = self._row_to_item(row)
            item.status = QueueStatus.PENDING
            item.retry_count = 0
            item.error = None
            await self.memory_queue.put((-item.priority.value, time.time(), item))
            await self._update_item(item)
            count += 1
        
        return count


class BatchQueue(DeferredQueue):
    def __init__(self, name: str, batch_size: int = 100, config: QueueConfig = None):
        super().__init__(name, config)
        self.batch_size = batch_size
        self._batch: List[QueueItem] = []
        self._batch_lock = asyncio.Lock()

    async def enqueue(self, payload: Any, priority: Priority = Priority.NORMAL, **kwargs) -> str:
        item_id = await super().enqueue(payload, priority, **kwargs)
        
        async with self._batch_lock:
            self._batch.append(await self.get_item(item_id))
            if len(self._batch) >= self.batch_size:
                await self._flush_batch()
        
        return item_id

    async def _flush_batch(self):
        if not self._batch:
            return
        
        batch = self._batch[:]
        self._batch.clear()
        
        if self._handler and hasattr(self._handler, 'handle_batch'):
            try:
                if asyncio.iscoroutinefunction(self._handler.handle_batch):
                    await self._handler.handle_batch([item.payload for item in batch])
                else:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._handler.handle_batch, [item.payload for item in batch]
                    )
                for item in batch:
                    await self.complete(item)
            except Exception as e:
                for item in batch:
                    await self.fail(item, str(e))


class DelayedQueue(DeferredQueue):
    async def enqueue_delayed(
        self,
        payload: Any,
        delay: float,
        priority: Priority = Priority.NORMAL,
        **kwargs
    ) -> str:
        item_id = str(uuid.uuid4())
        item = QueueItem(
            item_id=item_id,
            queue_name=self.name,
            payload=payload,
            priority=priority,
            metadata=kwargs.get("metadata", {}),
        )
        
        async def delayed_enqueue():
            await asyncio.sleep(delay)
            await self.memory_queue.put((-priority.value, time.time(), item))
            if self.config.persist:
                await self._persist_item(item)
            self.stats["enqueued"] += 1
        
        asyncio.create_task(delayed_enqueue())
        return item_id