"""Contracts for moving updates between a webhook and a worker."""

from typing import NamedTuple, Protocol


class QueuedUpdate(NamedTuple):
    """A single update read from a queue.

    A named tuple keeps the ``(entry_id, event_id, update)`` unpacking that
    simple queue fakes and older integrations rely on.
    """

    entry_id: str
    event_id: str
    update: dict


class UpdateSink(Protocol):
    """What a webhook needs: accept an update and report readiness."""

    async def enqueue(self, update: dict) -> str: ...

    async def is_ready(self) -> bool: ...


class UpdateSource(Protocol):
    """What a worker needs: read and acknowledge updates."""

    async def ensure_group(self) -> None: ...

    async def read(
        self, consumer: str, count: int = 10
    ) -> list[QueuedUpdate]: ...

    async def acknowledge(self, entry_id: str) -> None: ...


class NotificationSink(Protocol):
    """Optional contract for services that enqueue notification events."""

    async def enqueue_notification(
        self, event_id: str, messages: list[dict]
    ) -> str: ...


class UpdateQueue(UpdateSink, UpdateSource, NotificationSink, Protocol):
    """Full update queue contract."""
