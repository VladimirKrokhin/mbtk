"""Redis Streams transport for webhook updates.

Requires the ``redis`` extra::

    pip install mbtk[redis]
"""

import hashlib
import json
import logging

from ..max.updates import event_id_for
from . import QueuedUpdate

logger = logging.getLogger(__name__)


class RedisStreamQueue:
    """At-least-once update queue on Redis Streams.

    The queue deduplicates updates by event ID, acknowledges an entry only
    after successful processing, and keeps a short-lived failure counter
    for poisoned events.
    """

    DEDUPE_TTL_SECONDS = 30 * 24 * 60 * 60
    ATTEMPTS_TTL_SECONDS = 60 * 60
    ADD_UPDATE_SCRIPT = """
    if redis.call('EXISTS', KEYS[1]) == 1 then return false end
    local entry_id = redis.call('XADD', KEYS[2], '*', 'event_id', ARGV[1], 'body', ARGV[2])
    redis.call('SET', KEYS[1], '1', 'EX', ARGV[3])
    return entry_id
    """
    ACK_DELETE_SCRIPT = """
    local acknowledged = redis.call('XACK', KEYS[1], ARGV[1], ARGV[2])
    if acknowledged > 0 then redis.call('XDEL', KEYS[1], ARGV[2]) end
    return acknowledged
    """

    def __init__(
        self,
        client,
        stream="maxbot:updates",
        group="maxbot-workers",
        dedupe_ttl=DEDUPE_TTL_SECONDS,
        attempts_ttl=ATTEMPTS_TTL_SECONDS,
    ):
        self.client = client
        self.stream = stream
        self.group = group
        self.dedupe_ttl = dedupe_ttl
        self.attempts_ttl = attempts_ttl

    @classmethod
    def from_url(cls, url, **kwargs):
        import redis.asyncio as redis_async

        client = redis_async.Redis.from_url(url, decode_responses=True)
        return cls(client, **kwargs)

    async def enqueue(self, update):
        event_id = event_id_for(update)
        serialized = json.dumps(
            update, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        dedupe_key = (
            f"{self.stream}:dedupe:"
            f"{hashlib.sha256(event_id.encode()).hexdigest()}"
        )
        result = await self.client.eval(
            self.ADD_UPDATE_SCRIPT,
            2,
            dedupe_key,
            self.stream,
            event_id,
            serialized,
            self.dedupe_ttl,
        )
        if result is None or result is False:
            logger.info("MAX stream duplicate ignored")
        return event_id

    async def is_ready(self):
        return bool(await self.client.ping())

    async def ensure_group(self):
        try:
            await self.client.xgroup_create(
                self.stream, self.group, id="0", mkstream=True
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def read(
        self,
        consumer,
        count=10,
        block_ms=1000,
        min_idle_ms=30_000,
    ):
        claimed = await self.client.xautoclaim(
            self.stream,
            self.group,
            consumer,
            min_idle_time=min_idle_ms,
            start_id="0-0",
            count=count,
        )
        entries = claimed[1] if claimed and len(claimed) > 1 else []
        if not entries:
            batches = await self.client.xreadgroup(
                self.group,
                consumer,
                {self.stream: ">"},
                count=count,
                block=block_ms,
            )
            entries = batches[0][1] if batches else []
        return [self._decode(entry_id, fields) for entry_id, fields in entries]

    async def acknowledge(self, entry_id):
        await self.client.eval(
            self.ACK_DELETE_SCRIPT, 1, self.stream, self.group, entry_id
        )

    async def record_failure(self, entry_id):
        """Increment the transient failure counter for an entry."""
        key = f"{self.stream}:attempts:{entry_id}"
        count = await self.client.incr(key)
        await self.client.expire(key, self.attempts_ttl)
        return count

    async def clear_failure(self, entry_id):
        await self.client.delete(f"{self.stream}:attempts:{entry_id}")

    async def aclose(self):
        await self.client.aclose()

    @staticmethod
    def _decode(entry_id, fields):
        return QueuedUpdate(
            entry_id, fields["event_id"], json.loads(fields["body"])
        )
