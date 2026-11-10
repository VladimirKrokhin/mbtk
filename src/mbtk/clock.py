"""Clock abstraction for TTL caches and tests without real delays."""

import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    """Monotonic clock used by runtime caches."""

    def now(self) -> float:
        return time.monotonic()
