"""Error handling: retry, silence, or a user-facing message."""

import logging
from typing import Protocol

from ..errors import PermanentError
from ..retry import is_permanent_max, is_transient
from . import BaseMiddleware


class ErrorPolicy(Protocol):
    """Application-specific decisions about a failed operation."""

    def is_transient(self, error: Exception) -> bool: ...

    def is_silent(self, error: Exception) -> bool: ...

    def user_message(self, error: Exception) -> str | None: ...

    def callback_alert(self, error: Exception) -> str | None: ...


class DefaultErrorPolicy:
    """Generic policy for MAX API errors."""

    def is_transient(self, error):
        return is_transient(error)

    def is_silent(self, error):
        return is_permanent_max(error)

    def user_message(self, error):
        return getattr(error, "text", None) or (
            "The action could not be completed."
        )

    def callback_alert(self, error):
        return "Action rejected."


class ErrorMiddleware(BaseMiddleware):
    """Turn a failed handler into a retry, a silent drop, or a message."""

    def __init__(self, policy=None, logger=None):
        self.policy = policy or DefaultErrorPolicy()
        self.logger = logger or logging.getLogger(__name__)

    async def __call__(self, event, data, next_handler):
        try:
            return await next_handler()
        except PermanentError as error:
            data["error_handled"] = True
            await data["bot"].send_message(event.chat_id, error.text)
            return True
        except Exception as error:
            if self.policy.is_transient(error):
                raise
            data["error_handled"] = True
            status = getattr(error, "status", None) or "unknown"
            code = getattr(error, "code", None) or "unknown"
            if self.policy.is_silent(error):
                self.logger.error(
                    "MAX API permanently rejected event status=%s code=%s",
                    status,
                    code,
                )
                return True
            message = self.policy.user_message(error)
            if message:
                await data["bot"].send_message(event.chat_id, message)
            alert = self.policy.callback_alert(error)
            if alert and getattr(event, "callback_id", ""):
                await event.answer(alert, alert=True)
            self.logger.warning(
                "MAX request rejected status=%s code=%s", status, code
            )
            return True
