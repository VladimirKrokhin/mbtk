"""Worker batch processing tests."""

import signal
import time
import unittest
from threading import Event
from unittest.mock import Mock, patch

from mbtk.errors import RemoteServiceError
from mbtk.transport import QueuedUpdate
from mbtk.worker import process_once, run_poll_loop, termination_signals


class FakeQueue:
    def __init__(self, records, failures=None):
        self.records = records
        self.failures = dict(failures or {})
        self.acked = []
        self.cleared = []
        self.consumer = None
        self.count = None

    async def read(self, consumer, count=10):
        self.consumer = consumer
        self.count = count
        return self.records

    async def acknowledge(self, entry_id):
        self.acked.append(entry_id)

    async def record_failure(self, entry_id):
        self.failures[entry_id] = self.failures.get(entry_id, 0) + 1
        return self.failures[entry_id]

    async def clear_failure(self, entry_id):
        self.cleared.append(entry_id)


class Processor:
    def __init__(self, error=None):
        self.error = error
        self.seen = []

    async def process(self, update):
        self.seen.append(update)
        if self.error is not None:
            raise self.error


def record(entry_id="1000-0", event_id="e-1", update=None):
    return QueuedUpdate(entry_id, event_id, update or {"update_id": event_id})


class ProcessOnceTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_acknowledges_and_counts(self):
        queue = FakeQueue([record(), record("1001-0", "e-2")])
        processor = Processor()
        logger = Mock()

        processed = await process_once(
            queue, processor, "worker-1", logger=logger
        )

        self.assertEqual(processed, 2)
        self.assertEqual(queue.acked, ["1000-0", "1001-0"])
        self.assertEqual(queue.cleared, ["1000-0", "1001-0"])
        self.assertEqual(len(processor.seen), 2)
        self.assertEqual(logger.info.call_args.args[1:4], (2, 2, 0))

    async def test_permanent_error_is_acknowledged_and_dropped(self):
        queue = FakeQueue([record()])
        processor = Processor(
            RemoteServiceError("forbidden", 403, service="MAX")
        )

        await process_once(queue, processor, "worker-1")

        self.assertEqual(queue.acked, ["1000-0"])
        self.assertEqual(queue.cleared, ["1000-0"])
        self.assertNotIn("1000-0", queue.failures)

    async def test_transient_error_remains_pending(self):
        queue = FakeQueue([record()])
        processor = Processor(
            RemoteServiceError("unavailable", 503, service="MAX")
        )

        await process_once(queue, processor, "worker-1")

        self.assertEqual(queue.acked, [])
        self.assertEqual(queue.failures["1000-0"], 1)

    async def test_transient_error_is_dropped_after_max_attempts(self):
        queue = FakeQueue([record()], failures={"1000-0": 4})
        processor = Processor(
            RemoteServiceError("unavailable", 503, service="MAX")
        )

        await process_once(queue, processor, "worker-1", max_attempts=5)

        self.assertEqual(queue.acked, ["1000-0"])
        self.assertEqual(queue.cleared, ["1000-0"])

    async def test_stop_event_leaves_unprocessed_records_pending(self):
        stop = Event()
        queue = FakeQueue([record(), record("1001-0", "e-2")])

        class Stops(Processor):
            async def process(self, update):
                stop.set()
                await super().process(update)

        processed = await process_once(
            queue, Stops(), "worker-1", stop_event=stop
        )

        self.assertEqual(processed, 2)
        self.assertEqual(queue.acked, ["1000-0"])

    async def test_batch_log_contains_lag_without_event_data(self):
        now_ms = int(time.time() * 1000)
        queue = FakeQueue(
            [record(f"{now_ms - 1000}-0", "private-id", {"secret": "private"})]
        )
        logger = Mock()

        await process_once(queue, Processor(), "worker-1", logger=logger)

        args = logger.info.call_args.args
        self.assertEqual(args[1:4], (1, 1, 0))
        self.assertGreaterEqual(args[4], 800)
        self.assertNotIn("private", str(args))


class LoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_poll_loop_stops_after_failure(self):
        stop = Event()
        logger = Mock()

        async def step():
            stop.set()
            raise RuntimeError("boom")

        await run_poll_loop(step, stop, idle_seconds=0, logger=logger)

        logger.error.assert_called_once()

    async def test_termination_signals_set_stop_and_restore_handlers(self):
        stop = Event()
        installed = {}
        previous = object()

        def fake_signal(signum, handler):
            old_handler = installed.get(signum, previous)
            installed[signum] = handler
            return old_handler

        with patch("mbtk.worker.signal.signal", side_effect=fake_signal):
            with termination_signals(stop):
                installed[signal.SIGTERM](signal.SIGTERM, None)
                self.assertTrue(stop.is_set())

        self.assertIs(installed[signal.SIGTERM], previous)
        self.assertIs(installed[signal.SIGINT], previous)


if __name__ == "__main__":
    unittest.main()
