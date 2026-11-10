"""Unit tests for the core: events, filters, routers, middleware, and FSM."""

import unittest

from mbtk import (
    BotStarted,
    Callback,
    Dispatcher,
    FSMContext,
    MemoryStorage,
    Message,
    PermanentError,
    Router,
    SkipHandler,
    State,
    StatesGroup,
    parse_update,
)
from mbtk.filters import AllOf, Command, HasPhoto, Payload, StateIs
from mbtk.middleware import BaseMiddleware

MESSAGE_UPDATE = {
    "update_type": "message_created",
    "message": {
        "body": {"mid": "mid-1", "text": "/menu"},
        "recipient": {"chat_id": 10, "chat_type": "dialog"},
        "sender": {"user_id": 20},
    },
}

CALLBACK_UPDATE = {
    "update_type": "message_callback",
    "callback": {
        "callback_id": "cb-1",
        "payload": {"a": "deliveries_page", "b": "deliveries:flat"},
        "chat_id": 10,
        "chat_type": "dialog",
        "user": {"user_id": 20},
        "message": {
            "body": {"mid": "mid-1"},
            "recipient": {"chat_id": 10, "chat_type": "dialog"},
        },
    },
}

WELCOME_STATES = StatesGroup()
WELCOME_STATES.waiting = State("waiting")


class FakeBot:
    def __init__(self):
        self.messages = []
        self.edits = []
        self.answers = []
        self.downloads = {}

    async def send_message(self, chat_id, text, attachments=None):
        self.messages.append((chat_id, text, attachments))
        return {"message": {"body": {"mid": f"mid-{len(self.messages)}"}}}

    async def edit_message(self, message_id, chat_id, text, attachments=None):
        self.edits.append((message_id, chat_id, text, attachments))
        return {"success": True}

    async def answer_callback(
        self, callback_id, text=None, alert=False, message=None
    ):
        self.answers.append((callback_id, text, alert, message))
        return {"success": True}

    async def get_message(self, message_id):
        return {}

    async def download_image(self, url):
        return self.downloads[url]


class ParseUpdateTests(unittest.TestCase):
    def test_group_chats_and_unknown_types_are_ignored(self):
        group = {
            "update_type": "message_created",
            "message": {
                "body": {"text": "/menu"},
                "recipient": {"chat_id": 10, "chat_type": "chat"},
                "sender": {"user_id": 20},
            },
        }
        self.assertIsNone(parse_update(group))
        self.assertIsNone(parse_update({"update_type": "bot_added"}))

    def test_message_carries_identity_command_and_arguments(self):
        update = {
            "update_id": "u-1",
            "update_type": "message_created",
            "message": {
                "body": {"mid": "mid-1", "text": "/link Код-42"},
                "recipient": {"chat_id": "10", "chat_type": "dialog"},
                "sender": {"user_id": "20"},
            },
        }
        event = parse_update(update)

        self.assertIsInstance(event, Message)
        self.assertEqual(event.event_id, "u-1")
        self.assertEqual((event.chat_id, event.user_id), ("10", "20"))
        self.assertEqual(event.command, "/link")
        self.assertEqual(event.arguments, "Код-42")

    def test_command_suffix_mention_is_stripped(self):
        update = {
            "update_type": "message_created",
            "message": {
                "body": {"text": "/Menu@my_bot"},
                "recipient": {"chat_id": "10", "chat_type": "dialog"},
                "sender": {"user_id": "20"},
            },
        }
        self.assertEqual(parse_update(update).command, "/menu")

    def test_callback_event_id_is_callback_id_and_payload_is_object(self):
        event = parse_update(CALLBACK_UPDATE)

        self.assertIsInstance(event, Callback)
        self.assertEqual(event.event_id, "cb-1")
        self.assertEqual(event.payload["a"], "deliveries_page")
        self.assertEqual(event.message_id, "mid-1")

    def test_double_encoded_payload_from_embedded_bot_is_unwrapped(self):
        # The built-in bot 0.9.x sends the button payload as a JSON string
        # inside another JSON string (a real production dump).
        update = {
            **CALLBACK_UPDATE,
            "callback": {
                **CALLBACK_UPDATE["callback"],
                "payload": '"{\\"a\\":\\"summary\\"}"',
            },
        }

        event = parse_update(update)

        self.assertEqual(event.payload, {"a": "summary"})

    def test_bot_started_is_supported(self):
        update = {
            "update_type": "bot_started",
            "chat_id": "10",
            "user": {"user_id": "20"},
            "chat_type": "dialog",
        }
        self.assertIsInstance(parse_update(update), BotStarted)


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.message = parse_update(MESSAGE_UPDATE)
        self.callback = parse_update(CALLBACK_UPDATE)

    def test_command_matches_alias_and_ignores_case(self):
        event = parse_update(
            {
                "update_type": "message_created",
                "message": {
                    "body": {"text": "/МЕНЮ"},
                    "recipient": {"chat_id": "10", "chat_type": "dialog"},
                    "sender": {"user_id": "20"},
                },
            }
        )
        self.assertTrue(Command("menu", "меню")(event, {}))
        self.assertFalse(Command("link")(event, {}))

    def test_payload_and_combination(self):
        self.assertTrue(Payload("deliveries_page")(self.callback, {}))
        self.assertTrue(Payload(action="deliveries_page")(self.callback, {}))
        self.assertFalse(Payload("tickets_page")(self.callback, {}))
        self.assertFalse(Payload("deliveries_page")(self.message, {}))
        self.assertTrue(
            AllOf(
                Payload("deliveries_page"),
                lambda event: event.payload["b"].startswith("deliveries"),
            )(self.callback, {})
        )

    def test_state_and_photo_filters(self):
        storage = MemoryStorage()
        state = FSMContext(storage, ("10", "20"))
        state.set_state(WELCOME_STATES.waiting)

        photo = parse_update(
            {
                "update_type": "message_created",
                "message": {
                    "body": {"attachments": [{"type": "image", "payload": {}}]},
                    "recipient": {"chat_id": "10", "chat_type": "dialog"},
                    "sender": {"user_id": "20"},
                },
            }
        )

        self.assertTrue(StateIs("waiting")(photo, {"state": state}))
        self.assertTrue(HasPhoto()(photo, {}))
        self.assertFalse(HasPhoto()(self.message, {}))
        self.assertFalse(StateIs("other")(photo, {"state": state}))


class RouterUseTests(unittest.TestCase):
    def test_use_applies_middlewares_to_all_observers_in_order(self):
        router = Router("secured")
        first, second = object(), object()

        router.use(first, second)

        for observer in router.observers():
            self.assertEqual(observer.middlewares, [first, second])


class DispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = FakeBot()
        self.dispatcher = Dispatcher(bot=self.bot)

    async def test_first_matching_router_wins_and_handler_is_awaited(self):
        first = Router("first")
        second = Router("second")
        calls = []

        @first.message(Command("menu"))
        async def first_handler(event):
            calls.append("first")

        @second.message()
        async def second_handler(event):
            calls.append("second")

        self.dispatcher.include_router(first)
        self.dispatcher.include_router(second)

        handled = await self.dispatcher.feed_update(MESSAGE_UPDATE)

        self.assertTrue(handled)
        self.assertEqual(calls, ["first"])

    async def test_skip_handler_passes_event_to_next_handler(self):
        router = Router("skip")
        calls = []

        @router.message(Command("menu"))
        async def skip(event):
            raise SkipHandler()

        @router.message()
        async def fallback(event):
            calls.append("fallback")

        self.dispatcher.include_router(router)
        await self.dispatcher.feed_update(MESSAGE_UPDATE)

        self.assertEqual(calls, ["fallback"])

    async def test_dependencies_are_injected_by_argument_name(self):
        router = Router("di")
        seen = {}

        @router.message(Command("menu"))
        async def handler(event, bot, courier, state):
            seen.update(bot=bot, courier=courier, state=state)

        self.dispatcher.include_router(router)
        self.dispatcher.context["courier"] = "COURIER"
        await self.dispatcher.feed_update(MESSAGE_UPDATE)

        self.assertIs(seen["bot"], self.bot)
        self.assertEqual(seen["courier"], "COURIER")
        self.assertIsInstance(seen["state"], FSMContext)

    async def test_middleware_runs_around_handler_and_can_short_circuit(self):
        router = Router("middleware")
        order = []

        class Outer(BaseMiddleware):
            async def __call__(self, event, data, next_handler):
                order.append("outer-in")
                result = await next_handler()
                order.append("outer-out")
                return result

        class Inner(BaseMiddleware):
            async def __call__(self, event, data, next_handler):
                order.append("inner")
                data["courier"] = "MIDDLEWARE"
                return await next_handler()

        @router.message(Command("menu"))
        async def handler(event, courier):
            order.append(f"handler:{courier}")

        router.message.middleware(Inner())
        self.dispatcher.outer(Outer())
        self.dispatcher.include_router(router)

        await self.dispatcher.feed_update(MESSAGE_UPDATE)

        self.assertEqual(
            order,
            ["outer-in", "inner", "handler:MIDDLEWARE", "outer-out"],
        )

    async def test_unhandled_callback_is_answered_without_text(self):
        await self.dispatcher.feed_update(CALLBACK_UPDATE)

        self.assertEqual(self.bot.answers, [("cb-1", None, False, None)])

    async def test_permanent_error_is_reported_and_callback_answered(self):
        router = Router("error")

        @router.callback_query(Payload("deliveries_page"))
        async def handler(event):
            raise PermanentError("Access denied")

        self.dispatcher.include_router(router)
        await self.dispatcher.feed_update(CALLBACK_UPDATE)

        self.assertEqual(
            self.bot.answers, [("cb-1", "Access denied", False, None)]
        )

    async def test_handler_is_not_spawned_in_background(self):
        router = Router("await")
        completed = []

        @router.message(Command("menu"))
        async def handler(event):
            completed.append(True)

        self.dispatcher.include_router(router)
        await self.dispatcher.feed_update(MESSAGE_UPDATE)

        self.assertEqual(completed, [True])


class FSMTests(unittest.TestCase):
    def setUp(self):
        self.storage = MemoryStorage()
        self.state = FSMContext(self.storage, ("10", "20"))

    def test_state_data_and_clear(self):
        self.state.set_state(WELCOME_STATES.waiting)
        self.state.update_data(step=1)

        self.assertEqual(self.state.get_state(), "waiting")
        self.assertEqual(self.state.get_data(), {"step": 1})

        self.state.clear()
        self.assertIsNone(self.state.get_state())
        self.assertEqual(self.state.get_data(), {})

    def test_claim_is_exclusive_and_retryable(self):
        self.assertFalse(self.state.claim("mid-1"))

        self.state.set_state(WELCOME_STATES.waiting)
        self.assertTrue(self.state.claim("mid-1"))
        self.assertTrue(self.state.claim("mid-1"))
        self.assertFalse(self.state.claim("mid-2"))
        self.assertFalse(self.state.complete("mid-2"))
        self.assertTrue(self.state.complete("mid-1"))
        self.assertIsNone(self.state.get_state())


if __name__ == "__main__":
    unittest.main()
