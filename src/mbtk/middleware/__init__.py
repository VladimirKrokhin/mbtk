"""Base middleware: ``await next_handler()``, or stop the chain."""


class BaseMiddleware:
    async def __call__(self, event, data, next_handler):
        return await next_handler()
