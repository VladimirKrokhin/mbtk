"""Process queued updates with retries and acknowledgements."""

import asyncio
import logging
import signal
import time
from contextlib import contextmanager
from threading import current_thread, main_thread
from typing import Protocol

from .retry import is_permanent

MAX_TRANSIENT_ATTEMPTS = 5

logger = logging.getLogger(__name__)


class Processor(Protocol):
    """A single entry point for every queued update."""

    async def process(self, update: dict) -> None: ...


async def process_once(
    queue,
    processor: Processor,
    consumer,
    batch_size=10,
    stop_event=None,
    *,
    max_attempts=MAX_TRANSIENT_ATTEMPTS,
    is_permanent_error=is_permanent,
    logger=None,
):
    """Read and process one batch of updates.

    Returns the number of records read. A record is acknowledged only after
    ``processor.process`` succeeds. Permanent errors are acknowledged and
    dropped; transient errors stay in the pending list until ``max_attempts``
    is reached.
    """
    log = logger or globals()["logger"]
    records = await queue.read(consumer, count=batch_size)
    processed = 0
    failed = 0
    now_ms = time.time_ns() // 1_000_000
    oldest_lag_ms = 0
    for entry_id, _event_id, update in records:
        if stop_event is not None and stop_event.is_set():
            break
        if lag_ms := _entry_lag_ms(entry_id, now_ms):
            oldest_lag_ms = max(oldest_lag_ms, lag_ms)
        try:
            await processor.process(update)
        except Exception as error:
            failed += 1
            # Never log event bodies, API responses, or credentials.
            log.error("MAX event processing failed (%s)", type(error).__name__)
            if is_permanent_error(error):
                # A retry cannot help. Without an acknowledgement the event
                # would stay in the pending list forever and resend already
                # delivered messages.
                await queue.acknowledge(entry_id)
                await _clear_failure(queue, entry_id)
                log.warning(
                    "MAX event dropped after permanent rejection "
                    "status=%s code=%s",
                    getattr(error, "status", None) or "unknown",
                    getattr(error, "code", None) or "unknown",
                )
                continue
            attempts = await _record_failure(queue, entry_id)
            if attempts >= max_attempts:
                # A transient error can be poisoned (for example, a handler
                # bug behind a 500). Drop it after a bounded number of tries.
                await queue.acknowledge(entry_id)
                await _clear_failure(queue, entry_id)
                log.error(
                    "MAX event dropped after %d transient errors (%s)",
                    attempts,
                    type(error).__name__,
                )
            continue
        await queue.acknowledge(entry_id)
        await _clear_failure(queue, entry_id)
        processed += 1
    if records:
        log.info(
            "MAX stream batch read=%d processed=%d failed=%d oldest_lag_ms=%d",
            len(records),
            processed,
            failed,
            oldest_lag_ms,
        )
    return len(records)


async def _record_failure(queue, entry_id):
    """Increment the transient failure counter when the queue supports it."""
    record = getattr(queue, "record_failure", None)
    if record is None:
        return 1
    return await record(entry_id)


async def _clear_failure(queue, entry_id):
    clear = getattr(queue, "clear_failure", None)
    if clear is not None:
        await clear(entry_id)


def _entry_lag_ms(entry_id, now_ms):
    try:
        created_ms = int(str(entry_id).split("-", 1)[0])
    except (TypeError, ValueError):
        return 0
    return max(0, now_ms - created_ms)


async def run_poll_loop(step, stop_event, *, idle_seconds=2.0, logger=None):
    """Run ``step`` until ``stop_event`` is set, backing off on failure."""
    log = logger or globals()["logger"]
    while not stop_event.is_set():
        try:
            await step()
        except Exception as error:
            log.error("MAX queue read failed (%s)", type(error).__name__)
            await asyncio.to_thread(stop_event.wait, idle_seconds)


@contextmanager
def termination_signals(stop_event):
    """Set ``stop_event`` on SIGTERM/SIGINT and restore old handlers."""
    if current_thread() is not main_thread():
        yield
        return

    previous_handlers = {}

    def request_stop(_signum, _frame):
        stop_event.set()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, request_stop)
        yield
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
