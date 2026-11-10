"""Parse raw MAX updates into typed events."""

import hashlib
import json

from ..events import BotStarted, Callback, Message

SUPPORTED_UPDATES = frozenset(
    {"message_created", "message_callback", "bot_started"}
)


def event_id_for(update):
    """Stable event ID: ``update_id`` or a hash of the canonical JSON."""
    supplied_id = update.get("update_id")
    if supplied_id is not None and str(supplied_id).strip():
        return str(supplied_id)
    canonical = json.dumps(
        update, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_update(update, bot=None):
    """Turn a MAX update into an event, or return None.

    Group chats and unknown update types are ignored.
    """
    if not isinstance(update, dict):
        return None
    update_type = update.get("update_type")
    if update_type not in SUPPORTED_UPDATES:
        return None

    payload = _payload(update)
    chat_id, user_id, chat_type = _identity(update_type, payload)
    if not chat_id or not user_id or chat_type != "dialog":
        return None

    identity = {
        "event_id": event_id_for(update),
        "chat_id": chat_id,
        "user_id": user_id,
        "chat_type": chat_type,
        "raw": update,
        "bot": bot,
    }

    if update_type == "message_created":
        message = _mapping(payload.get("message"))
        body = _mapping(message.get("body"))
        text = str(body.get("text") or "").strip()
        return Message(
            text=text,
            message_id=str(body.get("mid") or message.get("mid") or ""),
            body=body,
            message=message,
            **identity,
        )

    if update_type == "message_callback":
        callback = _mapping(payload.get("callback") or update.get("callback"))
        callback_message = _mapping(callback.get("message"))
        callback_body = _mapping(callback_message.get("body"))
        callback_id = str(callback.get("callback_id") or "")
        if callback_id:
            identity["event_id"] = callback_id
        return Callback(
            callback_id=callback_id,
            payload=_parse_callback_payload(callback.get("payload")),
            message_id=str(
                callback_body.get("mid") or callback_message.get("mid") or ""
            ),
            **identity,
        )

    return BotStarted(
        user=_mapping(payload.get("user")),
        **identity,
    )


def _payload(update):
    nested = update.get("payload")
    return nested if isinstance(nested, dict) else update


def _identity(update_type, payload):
    message = _mapping(payload.get("message"))
    recipient = _mapping(message.get("recipient"))
    sender = _mapping(message.get("sender"))
    callback = _mapping(payload.get("callback"))
    callback_message = _mapping(callback.get("message")) or message
    callback_recipient = (
        _mapping(callback_message.get("recipient")) or recipient
    )
    callback_user = _mapping(callback.get("user")) or _mapping(
        callback.get("sender")
    )

    if update_type == "message_created":
        chat_id = recipient.get("chat_id")
        max_user_id = sender.get("user_id")
        chat_type = recipient.get("chat_type")
    elif update_type == "message_callback":
        chat_id = (
            callback.get("chat_id")
            or callback_recipient.get("chat_id")
            or recipient.get("chat_id")
        )
        max_user_id = callback_user.get("user_id") or sender.get("user_id")
        chat_type = callback_recipient.get("chat_type")
    elif update_type == "bot_started":
        user = _mapping(payload.get("user"))
        chat_id = payload.get("chat_id") or recipient.get("chat_id")
        max_user_id = user.get("user_id") or sender.get("user_id")
        chat_type = recipient.get("chat_type") or payload.get("chat_type")
    else:
        return None, None, None

    return _numeric_id(chat_id), _numeric_id(max_user_id), chat_type


def _numeric_id(value):
    text = str(value or "")
    return text if text.isdigit() and len(text) <= 32 else None


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _parse_callback_payload(raw):
    """Parse a button payload.

    MAX sends the payload as a string. Messages sent by the built-in bot
    0.9.x arrive with double encoding (a JSON string inside a JSON string),
    so unwrap up to two levels. Otherwise buttons in old messages silently
    stop working.
    """
    data = raw
    for _ in range(2):
        if not isinstance(data, str):
            break
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}
