"""Built-in middleware tests."""

import unittest
from unittest.mock import Mock

from mbtk.errors import PermanentError, RemoteServiceError
from mbtk.middleware.errors import (
    DefaultErrorPolicy,
    ErrorMiddleware,
)
from mbtk.middleware.logging import LoggingMiddleware


class FakeEvent:
    def __init__(self, chat_id="1", callback_id=""):
        self.chat_id = chat_id
        self.callback_id = callback_id
        self.answers = []

    async def answer(self, text=None, alert=False):
        self.answers.append((text, alert))


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))


def data_with_bot(bot):
    return {"bot": bot}


class LoggingMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_logs_success(self):
        logger = Mock()
        middleware = LoggingMiddleware(logger=logger)

        async def handler():
            return True

        handled = await middleware(FakeEvent(), {}, handler)

        self.assertTrue(handled)
        self.assertEqual(logger.info.call_args.args[1:3], ("fakeevent", "ok"))

    async def test_logs_error_and_reraises(self):
        logger = Mock()
        middleware = LoggingMiddleware(logger=logger)

        async def handler():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            await middleware(FakeEvent(), {}, handler)

        self.assertEqual(
            logger.info.call_args.args[1:3], ("fakeevent", "error")
        )
        self.assertEqual(logger.info.call_args.args[4], "RuntimeError")


class ErrorMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_permanent_error_is_shown_to_user(self):
        bot = FakeBot()
        middleware = ErrorMiddleware()

        async def handler():
            raise PermanentError("Access denied")

        data = data_with_bot(bot)
        handled = await middleware(FakeEvent(), data, handler)

        self.assertTrue(handled)
        self.assertTrue(data["error_handled"])
        self.assertEqual(bot.messages, [("1", "Access denied")])

    async def test_transient_error_is_reraised(self):
        middleware = ErrorMiddleware()

        async def handler():
            raise RemoteServiceError("unavailable", 503, service="MAX")

        with self.assertRaises(RemoteServiceError):
            await middleware(FakeEvent(), data_with_bot(FakeBot()), handler)

    async def test_silent_error_is_dropped_without_message(self):
        bot = FakeBot()
        logger = Mock()
        middleware = ErrorMiddleware(logger=logger)

        async def handler():
            raise RemoteServiceError("forbidden", 403, service="MAX")

        data = data_with_bot(bot)
        handled = await middleware(FakeEvent(), data, handler)

        self.assertTrue(handled)
        self.assertEqual(bot.messages, [])
        logger.error.assert_called_once()

    async def test_user_message_and_callback_alert(self):
        bot = FakeBot()
        event = FakeEvent(callback_id="cb-1")
        middleware = ErrorMiddleware()

        async def handler():
            raise RemoteServiceError(
                "bad request", 400, service="Bakery", text="Order is not ready"
            )

        handled = await middleware(event, data_with_bot(bot), handler)

        self.assertTrue(handled)
        self.assertEqual(bot.messages, [("1", "Order is not ready")])
        self.assertEqual(event.answers, [("Action rejected.", True)])

    async def test_unexpected_error_is_treated_as_transient(self):
        middleware = ErrorMiddleware()

        async def handler():
            raise RuntimeError("bug")

        with self.assertRaises(RuntimeError):
            await middleware(FakeEvent(), data_with_bot(FakeBot()), handler)

    async def test_custom_policy(self):
        class Policy:
            def is_transient(self, error):
                return False

            def is_silent(self, error):
                return False

            def user_message(self, error):
                return "Custom text"

            def callback_alert(self, error):
                return "Custom alert"

        bot = FakeBot()
        event = FakeEvent(callback_id="cb-1")
        middleware = ErrorMiddleware(policy=Policy())

        async def handler():
            raise RemoteServiceError("bad", 400, service="X")

        await middleware(event, data_with_bot(bot), handler)

        self.assertEqual(bot.messages, [("1", "Custom text")])
        self.assertEqual(event.answers, [("Custom alert", True)])

    async def test_default_policy_fallback_message(self):
        policy = DefaultErrorPolicy()

        self.assertEqual(
            policy.user_message(RemoteServiceError("bad", 400)),
            "The action could not be completed.",
        )


if __name__ == "__main__":
    unittest.main()
