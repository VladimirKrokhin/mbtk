"""FSM: dialogue states and data, in the spirit of aiogram 3."""

from typing import Protocol


class FSMStorage(Protocol):
    """Storage for dialogue state and data.

    The interface is synchronous: in a running bot these are local Redis
    operations without blocking reads.
    """

    def get_state(self, key): ...
    def set_state(self, key, state, ttl=None): ...
    def clear_state(self, key): ...
    def get_data(self, key): ...
    def update_data(self, key, values, ttl=None): ...
    def clear_data(self, key): ...
    def claim(self, key, token, ttl=None): ...
    def complete_claim(self, key, token): ...
    def clear(self, key): ...


class State(str):
    """A state value. Compares like a string."""

    def __new__(cls, value):
        return super().__new__(cls, str(value))


class StatesGroup:
    """A group of states: ``State`` attributes are collected automatically."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__states__ = {
            name: value
            for name, value in vars(cls).items()
            if isinstance(value, State)
        }


class FSMContext:
    """State and data for one user in one chat.

    ``key`` is a ``(chat_id, user_id)`` pair.
    """

    def __init__(self, storage: "FSMStorage | None", key):
        self.storage = storage
        self.key = key

    def get_state(self):
        if self.storage is None:
            return None
        return self.storage.get_state(self.key)

    def set_state(self, state, ttl=None):
        if self.storage is None:
            return
        self.storage.set_state(self.key, state, ttl=ttl)

    def clear_state(self):
        if self.storage is not None:
            self.storage.clear_state(self.key)

    def get_data(self):
        if self.storage is None:
            return {}
        return self.storage.get_data(self.key)

    def update_data(self, values=None, ttl=None, **kwargs):
        payload = dict(values or {})
        payload.update(kwargs)
        if self.storage is None:
            return payload
        return self.storage.update_data(self.key, payload, ttl=ttl)

    def clear_data(self):
        if self.storage is not None:
            self.storage.clear_data(self.key)

    def claim(self, token, ttl=None):
        """Atomically bind a one-shot action to this event."""
        if self.storage is None:
            return False
        return self.storage.claim(self.key, str(token), ttl=ttl)

    def complete(self, token):
        """Clear the state only when this event owns the claim."""
        if self.storage is None:
            return False
        return self.storage.complete_claim(self.key, str(token))

    def clear(self):
        """Drop both state and data."""
        if self.storage is not None:
            self.storage.clear(self.key)


class MemoryStorage:
    """In-memory storage for tests and local scenarios."""

    def __init__(self):
        self.records = {}

    def _record(self, key, create=False):
        record = self.records.get(key)
        if record is None and create:
            record = {"state": None, "claim": None, "data": {}}
            self.records[key] = record
        return record

    def get_state(self, key):
        record = self._record(key)
        return record["state"] if record else None

    def set_state(self, key, state, ttl=None):
        record = self._record(key, create=True)
        record["state"] = str(state)
        record["claim"] = None

    def clear_state(self, key):
        record = self._record(key)
        if record is not None:
            record["state"] = None
            record["claim"] = None

    def get_data(self, key):
        record = self._record(key)
        return dict(record["data"]) if record else {}

    def update_data(self, key, values, ttl=None):
        record = self._record(key, create=True)
        record["data"].update(values)
        return dict(record["data"])

    def clear_data(self, key):
        record = self._record(key)
        if record is not None:
            record["data"] = {}

    def claim(self, key, token, ttl=None):
        record = self._record(key)
        if not record or not record.get("state"):
            return False
        if not record.get("claim"):
            record["claim"] = str(token)
            return True
        return record["claim"] == str(token)

    def complete_claim(self, key, token):
        record = self._record(key)
        if not record or record.get("claim") != str(token):
            return False
        del self.records[key]
        return True

    def clear(self, key):
        self.records.pop(key, None)
