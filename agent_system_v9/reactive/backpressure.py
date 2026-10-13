"""
Backpressure Controller - Flow control and backpressure management
"""
import asyncio
import time
import threading
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from collections.abc import AsyncIterator
from abc import ABC, abstractmethod


class BackpressureStrategy(Enum):
    BLOCK = "block"
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    BUFFER = "buffer"
    REJECT = "reject"


@dataclass
class BackpressureConfig:
    max_buffer_size: int = 1000
    high_watermark: float = 0.8
    low_watermark: float = 0.3
    strategy: BackpressureStrategy = BackpressureStrategy.BLOCK
    timeout: float = 30.0
    monitor_interval: float = 1.0


class BufferFullException(Exception):
    pass


class BackpressureSignal:
    def __init__(self):
        self._event = asyncio.Event()
        self._event.set()
        self._active = False

    def apply(self):
        self._active = True
        self._event.clear()

    def release(self):
        self._active = False
        self._event.set()

    async def wait(self):
        await self._event.wait()

    @property
    def is_active(self) -> bool:
        return self._active


@dataclass
class FlowMetrics:
    items_processed: int = 0
    items_dropped: int = 0
    items_blocked: int = 0
    current_buffer_size: int = 0
    max_buffer_size: int = 0
    backpressure_activations: int = 0
    avg_processing_time: float = 0.0
    throughput: float = 0.0


class AsyncBuffer:
    def __init__(self, max_size: int, strategy: BackpressureStrategy = BackpressureStrategy.BLOCK):
        self.max_size = max_size
        self.strategy = strategy
        self._buffer: deque = deque()
        self._lock = asyncio.Lock()
        self._not_full = asyncio.Event()
        self._not_empty = asyncio.Event()
        self._not_empty.set()
        self._closed = False
        self.metrics = FlowMetrics()
        self.metrics.max_buffer_size = max_size

    async def put(self, item: Any, timeout: float = None) -> bool:
        async with self._lock:
            if self._closed:
                return False

            while len(self._buffer) >= self.max_size:
                self.metrics.items_blocked += 1
                if self.strategy == BackpressureStrategy.DROP_OLDEST:
                    self._buffer.popleft()
                    self.metrics.items_dropped += 1
                    break
                elif self.strategy == BackpressureStrategy.DROP_NEWEST:
                    self.metrics.items_dropped += 1
                    return False
                elif self.strategy == BackpressureStrategy.REJECT:
                    raise BufferFullException("Buffer full")
                elif self.strategy == BackpressureStrategy.BLOCK:
                    self._not_full.clear()
                    try:
                        await asyncio.wait_for(self._not_full.wait(), timeout=timeout)
                    except asyncio.TimeoutError:
                        return False
                else:
                    return False

            self._buffer.append(item)
            self.metrics.current_buffer_size = len(self._buffer)
            self._not_empty.set()
            return True

    async def get(self, timeout: float = None) -> Optional[Any]:
        async with self._lock:
            while not self._buffer and not self._closed:
                self._not_empty.clear()
                try:
                    await asyncio.wait_for(self._not_empty.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    return None

            if not self._buffer and self._closed:
                return None

            item = self._buffer.popleft()
            self.metrics.current_buffer_size = len(self._buffer)
            self.metrics.items_processed += 1
            self._not_full.set()
            return item

    def try_put(self, item: Any) -> bool:
        if len(self._buffer) >= self.max_size:
            return False
        self._buffer.append(item)
        self.metrics.current_buffer_size = len(self._buffer)
        self._not_empty.set()
        return True

    def try_get(self) -> Optional[Any]:
        if not self._buffer:
            return None
        item = self._buffer.popleft()
        self.metrics.current_buffer_size = len(self._buffer)
        self.metrics.items_processed += 1
        self._not_full.set()
        return item

    def close(self):
        self._closed = True
        self._not_empty.set()
        self._not_full.set()

    @property
    def is_full(self) -> bool:
        return len(self._buffer) >= self.max_size

    @property
    def is_empty(self) -> bool:
        return len(self._buffer) == 0

    def __len__(self) -> int:
        return len(self._buffer)


class TokenBucket:
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def wait_for_tokens(self, tokens: int = 1, timeout: float = None) -> bool:
        start = time.monotonic()
        while True:
            if self.consume(tokens):
                return True
            if timeout and time.monotonic() - start >= timeout:
                return False
            await asyncio.sleep(0.01)


class LeakyBucket:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.level = 0
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def add(self, amount: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.level = max(0, self.level - elapsed * self.rate)
            self.last_update = now
            
            if self.level + amount <= self.capacity:
                self.level += amount
                return True
            return False


class BackpressureController:
    def __init__(self, config: BackpressureConfig = None):
        self.config = config or BackpressureConfig()
        self.signal = BackpressureSignal()
        self.buffer = AsyncBuffer(self.config.max_buffer_size, self.config.strategy)
        self.token_bucket: Optional[TokenBucket] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self._callbacks: List[Callable] = []

    def set_rate_limit(self, rate: float, burst: int = None):
        self.token_bucket = TokenBucket(rate, burst or int(rate * 2))

    async def start(self):
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        self.buffer.close()

    async def _monitor_loop(self):
        while self._running:
            await asyncio.sleep(self.config.monitor_interval)
            await self._check_watermarks()

    async def _check_watermarks(self):
        usage = self.buffer.metrics.current_buffer_size / self.config.max_buffer_size
        
        if usage >= self.config.high_watermark and not self.signal.is_active:
            self.signal.apply()
            self.buffer.metrics.backpressure_activations += 1
            await self._notify_callbacks("high_watermark", usage)
        elif usage <= self.config.low_watermark and self.signal.is_active:
            self.signal.release()
            await self._notify_callbacks("low_watermark", usage)

    async def _notify_callbacks(self, event: str, usage: float):
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event, usage)
                else:
                    callback(event, usage)
            except Exception:
                pass

    def on_watermark(self, callback: Callable):
        self._callbacks.append(callback)

    async def submit(self, item: Any, timeout: float = None) -> bool:
        if self.token_bucket and not self.token_bucket.consume():
            if not await self.token_bucket.wait_for_tokens(timeout=timeout):
                return False
        
        return await self.buffer.put(item, timeout=timeout)

    async def receive(self, timeout: float = None) -> Optional[Any]:
        await self.signal.wait()
        return await self.buffer.get(timeout=timeout)

    def get_metrics(self) -> FlowMetrics:
        return self.buffer.metrics


class ReactiveStream(AsyncIterator):
    def __init__(self, controller: BackpressureController):
        self.controller = controller

    async def __anext__(self) -> Any:
        item = await self.controller.receive()
        if item is None:
            raise StopAsyncIteration
        return item

    def map(self, func: Callable) -> 'ReactiveStream':
        async def mapped_gen():
            async for item in self:
                yield func(item)
        return ReactiveStream(self.controller)

    def filter(self, predicate: Callable) -> 'ReactiveStream':
        async def filtered_gen():
            async for item in self:
                if predicate(item):
                    yield item
        return ReactiveStream(self.controller)

    def flat_map(self, func: Callable) -> 'ReactiveStream':
        async def flat_gen():
            async for item in self:
                result = func(item)
                if asyncio.iscoroutinefunction(func):
                    result = await result
                if hasattr(result, '__aiter__'):
                    async for sub_item in result:
                        yield sub_item
                elif hasattr(result, '__iter__'):
                    for sub_item in result:
                        yield sub_item
        return ReactiveStream(self.controller)


class FlowController:
    def __init__(self):
        self.controllers: Dict[str, BackpressureController] = {}
        self._lock = threading.RLock()

    def create_controller(self, name: str, config: BackpressureConfig = None) -> BackpressureController:
        with self._lock:
            controller = BackpressureController(config)
            self.controllers[name] = controller
            return controller

    def get_controller(self, name: str) -> Optional[BackpressureController]:
        with self._lock:
            return self.controllers.get(name)

    def remove_controller(self, name: str) -> bool:
        with self._lock:
            if name in self.controllers:
                del self.controllers[name]
                return True
        return False

    async def start_all(self):
        for controller in self.controllers.values():
            await controller.start()

    async def stop_all(self):
        for controller in self.controllers.values():
            await controller.stop()

    def get_all_metrics(self) -> Dict[str, FlowMetrics]:
        return {name: ctrl.get_metrics() for name, ctrl in self.controllers.items()}