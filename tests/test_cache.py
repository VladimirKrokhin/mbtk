"""Cache tests."""

import unittest

from mbtk.cache import MemoryCache, NullCache
from mbtk.cache.redis import RedisCache


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def now(self):
        return self.value


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expiries = {}
        self.closed = False

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.expiries[key] = ex

    async def delete(self, key):
        self.values.pop(key, None)
        return 1

    async def aclose(self):
        self.closed = True


class MemoryCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_ttl(self):
        clock = FakeClock()
        cache = MemoryCache(ttl=30, clock=clock)
        await cache.set("key", "value")

        clock.value += 29
        self.assertEqual(await cache.get("key"), "value")
        clock.value += 1
        self.assertIsNone(await cache.get("key"))

    async def test_per_call_ttl_and_delete(self):
        clock = FakeClock()
        cache = MemoryCache(ttl=30, clock=clock)
        await cache.set("key", "value", ttl=5)
        clock.value += 5
        self.assertIsNone(await cache.get("key"))

        await cache.set("key", "value")
        await cache.delete("key")
        self.assertIsNone(await cache.get("key"))

    async def test_null_cache(self):
        cache = NullCache()
        await cache.set("key", "value")
        self.assertIsNone(await cache.get("key"))
        await cache.delete("key")


class RedisCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()
        self.cache = RedisCache(self.redis, prefix="app:ctx", ttl=30)

    async def test_prefix_is_normalized_and_tuple_keys_are_joined(self):
        await self.cache.set(("10", "20"), {"role": "courier"})

        self.assertIn("app:ctx:10:20", self.redis.values)
        self.assertEqual(self.redis.expiries["app:ctx:10:20"], 30)
        self.assertEqual(
            await self.cache.get(("10", "20")), {"role": "courier"}
        )

    async def test_per_call_ttl(self):
        await self.cache.set("key", 1, ttl=5)
        self.assertEqual(self.redis.expiries["app:ctx:key"], 5)

    async def test_custom_codec(self):
        cache = RedisCache(
            self.redis,
            prefix="app",
            encode=lambda value: str(value),
            decode=lambda raw: int(raw),
        )
        await cache.set("key", 42)

        self.assertEqual(await cache.get("key"), 42)

    async def test_corrupted_value_is_a_miss(self):
        self.redis.values["app:ctx:key"] = "not-json"

        self.assertIsNone(await self.cache.get("key"))

    async def test_delete_and_close(self):
        await self.cache.set("key", 1)
        await self.cache.delete("key")
        self.assertNotIn("app:ctx:key", self.redis.values)

        await self.cache.aclose()
        self.assertTrue(self.redis.closed)


if __name__ == "__main__":
    unittest.main()
