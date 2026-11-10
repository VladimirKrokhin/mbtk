"""Redis Streams transport tests."""

import unittest

from mbtk.transport import QueuedUpdate
from mbtk.transport.redis_stream import RedisStreamQueue


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.streams = {}
        self.acked = []
        self.failures = {}
        self.expiries = {}
        self.next_ms = 1_700_000_000_000
        self.closed = False
        self.group_created = False
        self.busy_group = False

    async def eval(self, script, numkeys, *args):
        if script == RedisStreamQueue.ADD_UPDATE_SCRIPT:
            dedupe_key, stream, event_id, body, ttl = args
            if dedupe_key in self.values:
                return False
            self.next_ms += 1
            entry_id = f"{self.next_ms}-0"
            self.streams.setdefault(stream, []).append(
                (entry_id, {"event_id": event_id, "body": body})
            )
            self.values[dedupe_key] = "1"
            self.expiries[dedupe_key] = ttl
            return entry_id
        if script == RedisStreamQueue.ACK_DELETE_SCRIPT:
            stream, group, entry_id = args
            self.acked.append((stream, group, entry_id))
            return 1
        raise AssertionError("unexpected script")

    async def ping(self):
        return True

    async def xgroup_create(self, stream, group, id, mkstream):
        if self.busy_group:
            raise RuntimeError("BUSYGROUP consumer group exists")
        self.group_created = True

    async def xautoclaim(self, *args, **kwargs):
        return (0, [], [])

    async def xreadgroup(self, group, consumer, streams, count, block):
        stream = next(iter(streams))
        entries = self.streams.get(stream, [])
        return [(stream, entries)] if entries else []

    async def incr(self, key):
        self.failures[key] = self.failures.get(key, 0) + 1
        return self.failures[key]

    async def expire(self, key, ttl):
        self.expiries[key] = ttl

    async def delete(self, key):
        self.failures.pop(key, None)
        return 1

    async def aclose(self):
        self.closed = True


class RedisStreamQueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.queue = RedisStreamQueue(self.redis)

    async def test_enqueue_deduplicates_by_event_id(self):
        update = {"update_id": "u-1", "update_type": "message_created"}

        first = await self.queue.enqueue(update)
        second = await self.queue.enqueue(update)

        self.assertEqual(first, "u-1")
        self.assertEqual(second, "u-1")
        self.assertEqual(len(self.redis.streams["maxbot:updates"]), 1)
        self.assertEqual(
            self.redis.expiries[next(iter(self.redis.values))], 30 * 86400
        )

    async def test_read_returns_queued_updates(self):
        update = {"update_id": "u-1", "update_type": "message_created"}
        await self.queue.enqueue(update)

        records = await self.queue.read("worker-1")

        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], QueuedUpdate)
        entry_id, event_id, decoded = records[0]
        self.assertEqual(event_id, "u-1")
        self.assertEqual(decoded, update)
        self.assertTrue(entry_id.endswith("-0"))

    async def test_acknowledge_uses_stream_group_and_entry(self):
        await self.queue.acknowledge("1-0")

        self.assertEqual(
            self.redis.acked,
            [("maxbot:updates", "maxbot-workers", "1-0")],
        )

    async def test_failure_counter_is_incremented_and_cleared(self):
        self.assertEqual(await self.queue.record_failure("1-0"), 1)
        self.assertEqual(await self.queue.record_failure("1-0"), 2)
        self.assertEqual(
            self.redis.expiries["maxbot:updates:attempts:1-0"], 3600
        )

        await self.queue.clear_failure("1-0")
        self.assertNotIn("maxbot:updates:attempts:1-0", self.redis.failures)

    async def test_ensure_group_ignores_busy_group(self):
        self.redis.busy_group = True
        await self.queue.ensure_group()

        self.redis.busy_group = False
        await self.queue.ensure_group()
        self.assertTrue(self.redis.group_created)

    async def test_custom_stream_group_and_ttls(self):
        queue = RedisStreamQueue(
            self.redis,
            stream="app:updates",
            group="app-workers",
            dedupe_ttl=60,
            attempts_ttl=30,
        )

        await queue.enqueue({"update_id": "u-1"})
        await queue.acknowledge("1-0")

        self.assertIn("app:updates", self.redis.streams)
        self.assertEqual(self.redis.expiries[next(iter(self.redis.values))], 60)
        self.assertEqual(
            self.redis.acked, [("app:updates", "app-workers", "1-0")]
        )

    async def test_is_ready_and_close(self):
        self.assertTrue(await self.queue.is_ready())
        await self.queue.aclose()
        self.assertTrue(self.redis.closed)


if __name__ == "__main__":
    unittest.main()
