"""Redis-backed async cache.

Requires the ``redis`` extra::

    pip install mbtk[redis]
"""

import json


def json_encode(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def json_decode(raw):
    if isinstance(raw, bytes):
        raw = raw.decode()
    return json.loads(raw)


class RedisCache:
    """JSON cache over an async Redis client.

    ``prefix`` is normalized to end with a colon. ``key`` may be a string
    or a tuple; tuple parts are joined with colons.
    """

    def __init__(
        self,
        redis,
        *,
        prefix,
        ttl=30,
        encode=json_encode,
        decode=json_decode,
    ):
        self.redis = redis
        self.prefix = prefix.rstrip(":") + ":"
        self.ttl = ttl
        self.encode = encode
        self.decode = decode

    @classmethod
    def from_url(cls, url, **kwargs):
        import redis.asyncio as redis_async

        client = redis_async.Redis.from_url(url, decode_responses=True)
        return cls(client, **kwargs)

    async def get(self, key):
        raw = await self.redis.get(self._key(key))
        if raw is None:
            return None
        try:
            return self.decode(raw)
        except (TypeError, ValueError):
            return None

    async def set(self, key, value, ttl=None):
        await self.redis.set(
            self._key(key),
            self.encode(value),
            ex=self.ttl if ttl is None else ttl,
        )

    async def delete(self, key):
        await self.redis.delete(self._key(key))

    async def aclose(self):
        close = getattr(self.redis, "aclose", None)
        if close is not None:
            await close()

    def _key(self, key):
        parts = key if isinstance(key, tuple) else (key,)
        return self.prefix + ":".join(str(part) for part in parts)
