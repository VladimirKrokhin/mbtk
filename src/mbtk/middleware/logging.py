"""Event logging without message text or user identifiers."""

import logging
import time

from . import BaseMiddleware


class LoggingMiddleware(BaseMiddleware):
    """Log the event type, outcome, duration, and error class."""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    async def __call__(self, event, data, next_handler):
        started = time.monotonic()
        try:
            handled = await next_handler()
        except Exception as error:
            self._log(event, started, "error", type(error).__name__)
            raise
        self._log(event, started, "ok" if handled else "unhandled")
        return handled

    def _log(self, event, started, outcome, error_name=""):
        elapsed_ms = int((time.monotonic() - started) * 1000)
        self.logger.info(
            "MAX event type=%s outcome=%s duration_ms=%d error=%s",
            type(event).__name__.lower(),
            outcome,
            elapsed_ms,
            error_name,
        )
