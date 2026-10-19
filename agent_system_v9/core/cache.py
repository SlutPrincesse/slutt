"""Simple in-memory LRU cache for sync/async callables."""
from __future__ import annotations

import asyncio
import functools
import time
from collections import OrderedDict
from typing import Any, Callable


class LRUCache:
    def __init__(self, maxsize: int = 128, ttl: float = 0):
        self.maxsize = maxsize
        self.ttl = ttl
        self._store: OrderedDict = OrderedDict()

    def get(self, key):
        if key in self._store:
            val, ts = self._store[key]
            if self.ttl and (time.time() - ts) > self.ttl:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return val
        return None

    def set(self, key, val):
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (val, time.time())
        if len(self._store) > self.maxsize:
            self._store.popitem(last=False)

    def clear(self):
        self._store.clear()


def memoize(maxsize: int = 128, ttl: float = 0):
    cache = LRUCache(maxsize=maxsize, ttl=ttl)

    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                key = (args, tuple(sorted(kwargs.items())))
                cached = cache.get(key)
                if cached is not None:
                    return cached
                result = await func(*args, **kwargs)
                cache.set(key, result)
                return result
            wrapper.cache = cache
            return wrapper
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                key = (args, tuple(sorted(kwargs.items())))
                cached = cache.get(key)
                if cached is not None:
                    return cached
                result = func(*args, **kwargs)
                cache.set(key, result)
                return result
            wrapper.cache = cache
            return wrapper
    return decorator
