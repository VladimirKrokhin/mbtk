"""Exceptions raised by the toolkit."""


class FrameworkError(Exception):
    """Base error for the toolkit."""


class SkipHandler(FrameworkError):
    """The handler does not apply: pass the event to the next one."""


class PermanentError(FrameworkError):
    """An error the user must see; retrying is pointless."""

    def __init__(self, text, alert=False):
        super().__init__(text)
        self.text = text
        self.alert = alert


class RemoteServiceError(Exception):
    """A remote API failure with a status and a safe user-facing text."""

    def __init__(
        self, message, status=None, service=None, code=None, text=None
    ):
        super().__init__(message)
        self.status = status
        self.service = service
        # Short API error code (``proto.payload`` for MAX), useful for log
        # analysis. The response body itself is never stored.
        self.code = code
        # Human-readable business error text from the remote service. It is
        # safe to show to the user; the rest of the response is not.
        self.text = text
