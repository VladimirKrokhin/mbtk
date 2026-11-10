"""Router: handlers, filters, and child routers."""

from dataclasses import dataclass, field

from .filters import normalize_all


@dataclass
class Handler:
    callback: object
    filters: tuple = field(default_factory=tuple)

    async def matches(self, event, data):
        for filter_ in self.filters:
            result = filter_(event, data)
            if hasattr(result, "__await__"):
                result = await result
            if not result:
                return False
        return True


class Observer:
    """Subscription point: ``router.message``, ``router.callback_query``, etc."""

    def __init__(self, name):
        self.name = name
        self.handlers = []
        self.middlewares = []

    def __call__(self, *filters):
        def decorator(callback):
            self.handlers.append(
                Handler(callback=callback, filters=normalize_all(filters))
            )
            return callback

        return decorator

    def middleware(self, middleware):
        self.middlewares.append(middleware)
        return middleware


class Router:
    def __init__(self, name=""):
        self.name = name
        self.message = Observer("message")
        self.callback_query = Observer("callback_query")
        self.bot_started = Observer("bot_started")
        self.error = Observer("error")
        self.routers = []
        self.middlewares = []

    def include_router(self, router):
        self.routers.append(router)
        return router

    def observers(self):
        return (self.message, self.callback_query, self.bot_started)

    def use(self, *middlewares):
        """Attach middleware to every observer of the router, in order."""
        for observer in self.observers():
            observer.middlewares.extend(middlewares)
        return self

    def middleware(self, middleware):
        """Middleware for every event of the router (outer for the subtree)."""
        self.middlewares.append(middleware)
        return middleware

    def walk(self):
        yield self
        for router in self.routers:
            yield from router.walk()

    def observer(self, name):
        return getattr(self, name)
