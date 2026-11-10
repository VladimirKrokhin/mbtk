"""Webhook validation and queue ingestion for MAX.

These helpers do not depend on a web framework. Use
:mod:`mbtk.webhook.fastapi` for the ready-made ASGI app.
"""

import hmac
import json
import logging

logger = logging.getLogger(__name__)

MAX_SECRET_HEADER = "X-Max-Bot-Api-Secret"
DEFAULT_MAX_BODY_BYTES = 1_048_576


def validate_webhook(
    headers,
    body: bytes,
    secret: str,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
):
    """Validate a webhook request.

    Returns ``(status, update_or_error_body)``.
    """
    if len(body) > max_body_bytes:
        return 413, b"request too large"

    supplied_secret = _header(headers, MAX_SECRET_HEADER)
    if not supplied_secret or not hmac.compare_digest(
        supplied_secret.encode("utf-8"), secret.encode("utf-8")
    ):
        return 401, b"unauthorized"

    try:
        update = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 400, b"invalid JSON"
    if not isinstance(update, dict):
        return 400, b"invalid update"
    return 200, update


async def accept_webhook(
    headers,
    body: bytes,
    queue,
    secret: str,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
):
    """Validate a webhook request and enqueue the update."""
    status, value = validate_webhook(headers, body, secret, max_body_bytes)
    if status != 200:
        return status, value
    try:
        await queue.enqueue(value)
    except Exception as error:
        logger.warning(
            "MAX webhook queue unavailable (%s)", type(error).__name__
        )
        return 503, b"queue unavailable"
    return 200, b"ok"


async def readiness(queue):
    """Return ``200`` when the queue is reachable, otherwise ``503``."""
    try:
        if await queue.is_ready():
            return 200, b"ok"
    except Exception:
        pass
    return 503, b"not ready"


def _header(headers, name: str) -> str:
    expected = name.lower()
    for key, value in headers.items():
        if str(key).lower() == expected:
            return str(value).strip()
    return ""
