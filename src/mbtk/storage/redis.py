"""Redis-backed FSM storage.

Requires the ``redis`` extra::

    pip install mbtk[redis]

The storage is synchronous on purpose: in a running bot these are local
Redis calls without blocking reads. Use a synchronous client
(``redis.Redis``), not ``redis.asyncio``.
"""

import json


class RedisFSMStorage:
    """Store FSM state, data, and one-shot claims in Redis.

    ``prefix`` is prepended to ``(chat_id, user_id)`` keys and is used as
    is, so it should end with a colon. ``ttl`` is applied when a record is
    created without an explicit TTL.
    """

    FSM_TTL_SECONDS = 24 * 3600

    FSM_CLAIM_SCRIPT = """
    local raw = redis.call('GET', KEYS[1])
    if not raw then return false end
    local record = cjson.decode(raw)
    if not record['state'] then return false end
    if record['claim'] then
        return record['claim'] == ARGV[1]
    end
    record['claim'] = ARGV[1]
    redis.call('SET', KEYS[1], cjson.encode(record), 'KEEPTTL')
    return true
    """
    FSM_COMPLETE_SCRIPT = """
    local raw = redis.call('GET', KEYS[1])
    if not raw then return false end
    local record = cjson.decode(raw)
    if record['claim'] ~= ARGV[1] then return false end
    return redis.call('DEL', KEYS[1])
    """

    def __init__(self, client, prefix="maxbot:fsm:", ttl=FSM_TTL_SECONDS):
        self.client = client
        self.prefix = prefix
        self.ttl = ttl

    def get_state(self, key):
        record = self._fsm_record(key)
        return record.get("state") if record else None

    def set_state(self, key, state, ttl=None):
        record = self._fsm_record(key) or {"data": {}}
        record["state"] = str(state)
        record["claim"] = None
        self._save_fsm_record(key, record, ttl)

    def clear_state(self, key):
        record = self._fsm_record(key)
        if not record:
            return
        record["state"] = None
        record["claim"] = None
        self._save_fsm_record(key, record, None)

    def get_data(self, key):
        record = self._fsm_record(key)
        data = record.get("data") if record else None
        return dict(data) if isinstance(data, dict) else {}

    def update_data(self, key, values, ttl=None):
        record = self._fsm_record(key) or {"state": None, "claim": None}
        data = record.get("data")
        if not isinstance(data, dict):
            data = {}
        data.update(values)
        record["data"] = data
        self._save_fsm_record(key, record, ttl)
        return dict(data)

    def clear_data(self, key):
        record = self._fsm_record(key)
        if not record:
            return
        record["data"] = {}
        self._save_fsm_record(key, record, None)

    def claim(self, key, token, ttl=None):
        """Atomically bind a one-shot action to this event."""
        return bool(
            self.client.eval(
                self.FSM_CLAIM_SCRIPT,
                1,
                self._fsm_key(key),
                str(token),
            )
        )

    def complete_claim(self, key, token):
        """Clear the state only when this event owns the claim."""
        return bool(
            self.client.eval(
                self.FSM_COMPLETE_SCRIPT,
                1,
                self._fsm_key(key),
                str(token),
            )
        )

    def clear(self, key):
        return bool(self.client.delete(self._fsm_key(key)))

    def _fsm_record(self, key):
        raw = self.client.get(self._fsm_key(key))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            record = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return record if isinstance(record, dict) else None

    def _save_fsm_record(self, key, record, ttl):
        payload = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
        redis_key = self._fsm_key(key)
        if ttl is not None:
            self.client.set(redis_key, payload, ex=ttl)
        elif self.client.get(redis_key):
            self.client.set(redis_key, payload, keepttl=True)
        else:
            self.client.set(redis_key, payload, ex=self.ttl)

    def _fsm_key(self, key):
        chat_id, user_id = key
        return f"{self.prefix}{chat_id}:{user_id}"
