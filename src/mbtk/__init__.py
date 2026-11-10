"""A small async toolkit for MAX messenger bots.

The design follows aiogram 3: typed events, routers, composable filters,
middleware, dependency injection, and finite state machines. The core has
no runtime dependencies. Optional extras::

    pip install mbtk[max]    # HTTP client for the MAX Bot API
    pip install mbtk[redis]  # Redis-backed FSM storage
    pip install mbtk[all]
"""

from .di import inject
from .dispatcher import Dispatcher
from .errors import PermanentError, RemoteServiceError, SkipHandler
from .events import BotStarted, Callback, Event, Message
from .fsm import FSMContext, MemoryStorage, State, StatesGroup
from .max.updates import event_id_for, parse_update
from .middleware import BaseMiddleware
from .router import Router

__all__ = [
    "BaseMiddleware",
    "BotStarted",
    "Callback",
    "Dispatcher",
    "Event",
    "FSMContext",
    "MemoryStorage",
    "Message",
    "PermanentError",
    "RemoteServiceError",
    "Router",
    "SkipHandler",
    "State",
    "StatesGroup",
    "event_id_for",
    "inject",
    "parse_update",
]
