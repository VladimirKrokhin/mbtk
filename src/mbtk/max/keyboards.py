"""Builders for MAX inline keyboards and attachments."""

import json
from typing import Any

MAX_BUTTONS_PER_KEYBOARD = 30


def button(text: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build an inline callback button."""
    return {
        "type": "callback",
        "text": str(text),
        "payload": json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ),
    }


def keyboard(
    rows: list[list[dict[str, Any]]],
    limit: int = MAX_BUTTONS_PER_KEYBOARD,
) -> dict[str, Any]:
    """Build an inline keyboard from rows of buttons."""
    return {"type": "inline_keyboard", "payload": {"buttons": rows[:limit]}}


def location_attachment(latitude, longitude) -> dict[str, Any]:
    """Build a location attachment."""
    return {
        "type": "location",
        "latitude": latitude,
        "longitude": longitude,
    }
