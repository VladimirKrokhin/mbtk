"""Dispatcher: accepts an update and routes it through routers."""

import logging

from .di import inject
from .errors import PermanentError, SkipHandler
from .events import BotStarted, Callback, Message
from .fsm import FSMContext
from .max.updates import parse_update
from .router import Router

logger = logging.getLogger(__name__)

EVENT_OBSERVERS = {
    Message: "message",
    Callback: "callback_query",
    BotStarted: "bot_started",
}


class Dispatcher(Router):
    """Root router and the ``feed_update`` entry point.

    A handler is always awaited, so a queue can acknowledge the event only
    after the handler succeeds.
    """

    def __init__(self, bot=None, storage=None, context=None):
        super().__init__("dispatcher")
        self.bot = bot
        self.storage = storage
        self.context = dict(context or {})
        self.outer_middlewares = []

    def outer(self, middleware):
        self.outer_middlewares.append(middleware)
        return middleware

    async def feed_update(self, update):
        event = parse_update(update, bot=self.bot)
        if event is None:
            return False

        data = dict(self.context)
        data.update(
            event=event,
            bot=self.bot,
            dispatcher=self,
            storage=self.storage,
        )
        data["state"] = FSMContext(self.storage, (event.chat_id, event.user_id))
        observer_name = EVENT_OBSERVERS[type(event)]

        try:
            handled = await self._run_outer(
                event,
                data,
                lambda: self._propagate(self, event, data, observer_name, []),
            )
        except PermanentError as error:
            data["error_handled"] = True
            await self._notify(event, error.text, alert=error.alert)
            handled = True
        except Exception as error:
            if not await self._propagate_error(event, error, data):
                raise
            data["error_handled"] = True
            handled = True

        if (
            isinstance(event, Callback)
            and not event.answered
            and not data.get("error_handled")
        ):
            await self._answer(event)
        return handled

    async def _run_outer(self, event, data, final):
        async def step(index):
            if index >= len(self.outer_middlewares):
                return await final()
            middleware = self.outer_middlewares[index]
            return await middleware(event, data, lambda: step(index + 1))

        return await step(0)

    async def _propagate(self, router, event, data, name, chain):
        observer = router.observer(name)
        local = list(chain)
        local.extend(router.middlewares)
        local.extend(observer.middlewares)

        for handler in observer.handlers:
            if not await handler.matches(event, data):
                continue
            try:
                await self._call_handler(handler, local, event, data)
                return True
            except SkipHandler:
                continue

        for child in router.routers:
            if await self._propagate(child, event, data, name, local):
                return True
        return False

    async def _call_handler(self, handler, middlewares, event, data):
        async def final():
            kwargs = inject(handler.callback, data, skip=1)
            return await handler.callback(event, **kwargs)

        async def step(index):
            if index >= len(middlewares):
                return await final()
            middleware = middlewares[index]
            return await middleware(event, data, lambda: step(index + 1))

        return await step(0)

    async def _propagate_error(self, event, error, data):
        return await self._walk_error(self, event, error, data)

    async def _walk_error(self, router, event, error, data):
        for handler in router.error.handlers:
            try:
                await handler.callback(
                    event,
                    error,
                    **inject(handler.callback, data, skip=2),
                )
                return True
            except SkipHandler:
                continue
        for child in router.routers:
            if await self._walk_error(child, event, error, data):
                return True
        return False

    async def _notify(self, event, text, alert=False):
        if not text:
            return
        if isinstance(event, Callback):
            await self._answer(event, text, alert)
            return
        if self.bot is None:
            return
        await self.bot.send_message(event.chat_id, text)

    async def _answer(self, event, text=None, alert=False):
        """Close the button spinner without breaking the handler.

        The handler has already sent its messages, and a queue
        acknowledges the event only after success. Raising here would leave
        the event in the queue, and a retry would send the same screens
        again, looping the bot.
        """
        try:
            await event.answer(text, alert=alert)
        except Exception as error:
            # Status and code are enough for debugging: 400 with
            # ``proto.payload`` means a bad request body, 403 means the bot
            # lost access to the chat. Never log the response body or chat ID.
            logger.warning(
                "MAX callback answer failed (%s status=%s code=%s)",
                type(error).__name__,
                getattr(error, "status", None) or "unknown",
                getattr(error, "code", None) or "unknown",
            )
