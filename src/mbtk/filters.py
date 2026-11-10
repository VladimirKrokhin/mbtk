"""Event filters that compose into trees with ``&`` and ``|``."""

import inspect
import re

from .events import BotStarted, Callback, Message


class Filter:
    """Base filter. Returns True when the event matches."""

    def __call__(self, event, data):
        raise NotImplementedError

    def __and__(self, other):
        return AllOf(self, other)

    def __or__(self, other):
        return AnyOf(self, other)

    def __invert__(self):
        return Not(self)


class FuncFilter(Filter):
    def __init__(self, func):
        self.func = func

    def __call__(self, event, data):
        return self.func(event, data)


class AllOf(Filter):
    def __init__(self, *filters):
        self.filters = normalize_all(filters)

    def __call__(self, event, data):
        return all(item(event, data) for item in self.filters)


class AnyOf(Filter):
    def __init__(self, *filters):
        self.filters = normalize_all(filters)

    def __call__(self, event, data):
        return any(item(event, data) for item in self.filters)


class Not(Filter):
    def __init__(self, filter_):
        self.filter = normalize(filter_)

    def __call__(self, event, data):
        return not self.filter(event, data)


class Command(Filter):
    """A message command: ``/link``, ``/menu``, or ``/start@bot``."""

    def __init__(self, *names, ignore_case=True):
        self.ignore_case = ignore_case
        self.names = {
            self._normalize(name) for name in names if str(name).strip()
        }

    def _normalize(self, name):
        value = "/" + str(name).strip().lstrip("/")
        return value.lower() if self.ignore_case else value

    def __call__(self, event, data):
        if not isinstance(event, Message) or not event.command:
            return False
        command = event.command.lower() if self.ignore_case else event.command
        return command in self.names


class CommandStart(Filter):
    """``/start``, the equivalent of aiogram's ``CommandStart``."""

    def __call__(self, event, data):
        return (
            isinstance(event, Message)
            and event.command.split("@", 1)[0] == "/start"
        )


class TextEquals(Filter):
    def __init__(self, *texts):
        self.texts = {str(text) for text in texts}

    def __call__(self, event, data):
        return isinstance(event, Message) and event.text in self.texts


class TextStartswith(Filter):
    def __init__(self, *prefixes):
        self.prefixes = tuple(str(prefix) for prefix in prefixes)

    def __call__(self, event, data):
        return isinstance(event, Message) and event.text.startswith(
            self.prefixes
        )


class TextRegexp(Filter):
    def __init__(self, pattern):
        self.pattern = re.compile(pattern)

    def __call__(self, event, data):
        return isinstance(event, Message) and bool(
            self.pattern.fullmatch(event.text)
        )


class HasPhoto(Filter):
    """The message contains an image attachment."""

    def __call__(self, event, data):
        if not isinstance(event, Message):
            return False
        return any(
            isinstance(item, dict) and item.get("type") == "image"
            for item in event.attachments
        )


class Payload(Filter):
    """A callback payload field: ``a`` (action) or any custom key."""

    def __init__(self, action=None, **fields):
        self.fields = dict(fields)
        if action is not None:
            self.fields["a"] = action

    def __call__(self, event, data):
        if not isinstance(event, Callback):
            return False
        return all(
            event.payload.get(key) == value
            for key, value in self.fields.items()
        )


class StateIs(Filter):
    """The user's current FSM state is one of the listed states."""

    def __init__(self, *states):
        self.states = {str(state) for state in states}

    def __call__(self, event, data):
        state = data.get("state")
        return state is not None and state.get_state() in self.states


class ChatType(Filter):
    def __init__(self, *types):
        self.types = {str(value) for value in types}

    def __call__(self, event, data):
        return event.chat_type in self.types


class IsMessage(Filter):
    def __call__(self, event, data):
        return isinstance(event, Message)


class IsCallback(Filter):
    def __call__(self, event, data):
        return isinstance(event, Callback)


class IsBotStarted(Filter):
    def __call__(self, event, data):
        return isinstance(event, BotStarted)


class Always(Filter):
    def __call__(self, event, data):
        return True


def normalize(filter_):
    if isinstance(filter_, Filter):
        return filter_
    if isinstance(filter_, bool):
        return FuncFilter(lambda _event, _data: filter_)
    if callable(filter_):
        return FuncFilter(_with_data(filter_))
    raise TypeError(f"Unsupported filter: {type(filter_)!r}")


def normalize_all(filters):
    return tuple(normalize(item) for item in filters)


def _with_data(func):
    """Allow short filters such as ``lambda event: ...``."""
    try:
        params = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        return func
    positional = [
        param
        for param in params
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) <= 1:
        return lambda event, _data: func(event)
    return func
