"""Classify remote API errors for retries and user-facing messages."""

from .errors import RemoteServiceError

RETRYABLE_STATUSES = frozenset({401, 408, 429})


def is_transient(error):
    """Whether retrying the same operation may succeed."""
    status = getattr(error, "status", None)
    service = getattr(error, "service", None)
    if service == "MAX" and status == 401:
        return True
    return status is None or status in (408, 429) or status >= 500


def is_permanent(error):
    """A client rejection: retrying the same event will not help."""
    status = getattr(error, "status", None)
    return (
        isinstance(error, RemoteServiceError)
        and status is not None
        and 400 <= status < 500
        and status not in RETRYABLE_STATUSES
    )


def is_permanent_max(error):
    """A permanent rejection from the MAX API."""
    return is_permanent(error) and getattr(error, "service", None) == "MAX"
