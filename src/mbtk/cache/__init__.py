"""Small async cache primitives."""

from typing import Protocol

from ..clock import SystemClock


class AsyncCache(Protocol):
    async def get(self, key): ...

    async def set(self, key, value, ttl=None): ...

    async def delete(self, key): ...


class NullCache:
    """Disabled cache: always a miss."""

    async def get(self, key):
        return None

    async def set(self, key, value, ttl=None):
        return None

    async def delete(self, key):
        return None


class MemoryCache:
    """In-memory cache with TTL for tests and local scenarios."""

    def __init__(self, ttl=30, clock=None):
        self.ttl = ttl
        self.clock = clock or SystemClock()
        self.values = {}

    async def get(self, key):
        item = self.values.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= self.clock.now():
            self.values.pop(key, None)
            return None
        return value

    async def set(self, key, value, ttl=None):
        ttl = self.ttl if ttl is None else ttl
        self.values[key] = (self.clock.now() + ttl, value)

    async def delete(self, key):
        self.values.pop(key, None)
