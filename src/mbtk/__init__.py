"""A small async toolkit for MAX messenger bots.

The design follows aiogram 3: typed events, routers, composable filters,
middleware, dependency injection, and finite state machines. The core has
no runtime dependencies. Optional extras::

    pip install mbtk[max]      # HTTP client for the MAX Bot API
    pip install mbtk[redis]    # Redis FSM storage and update stream
    pip install mbtk[fastapi]  # ASGI webhook adapter
    pip install mbtk[all]
"""

from .cache import MemoryCache, NullCache
from .di import inject
from .dispatcher import Dispatcher
from .errors import PermanentError, RemoteServiceError, SkipHandler
from .events import BotStarted, Callback, Event, Message
from .fsm import FSMContext, MemoryStorage, State, StatesGroup
from .max.updates import event_id_for, parse_update
from .middleware import BaseMiddleware
from .middleware.errors import (
    DefaultErrorPolicy,
    ErrorMiddleware,
    ErrorPolicy,
)
from .middleware.logging import LoggingMiddleware
from .retry import is_permanent, is_permanent_max, is_transient
from .router import Router
from .transport import QueuedUpdate, UpdateSink, UpdateSource
from .worker import (
    Processor,
    process_once,
    run_poll_loop,
    termination_signals,
)

__version__ = "0.2.0"

__all__ = [
    "BaseMiddleware",
    "BotStarted",
    "Callback",
    "DefaultErrorPolicy",
    "Dispatcher",
    "ErrorMiddleware",
    "ErrorPolicy",
    "Event",
    "FSMContext",
    "LoggingMiddleware",
    "MemoryCache",
    "MemoryStorage",
    "Message",
    "NullCache",
    "PermanentError",
    "Processor",
    "QueuedUpdate",
    "RemoteServiceError",
    "Router",
    "SkipHandler",
    "State",
    "StatesGroup",
    "UpdateSink",
    "UpdateSource",
    "event_id_for",
    "inject",
    "is_permanent",
    "is_permanent_max",
    "is_transient",
    "parse_update",
    "process_once",
    "run_poll_loop",
    "termination_signals",
]
