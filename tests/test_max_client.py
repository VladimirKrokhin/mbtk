"""Unit tests for the MAX client: send, edit, and answer a callback."""

import json
import unittest

import httpx

from mbtk.errors import RemoteServiceError
from mbtk.max.client import MaxApiClient


class MaxClientMessagesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.status = 200
        self.error_body = None
        self.answer_success = True
        transport = httpx.MockTransport(self._handler)
        self.session = httpx.AsyncClient(transport=transport)
        self.addAsyncCleanup(self.session.aclose)
        # Pass the session so the constructor can attach Authorization.
        self.client = MaxApiClient(
            self.base_url(),
            "bot-token",
            session=self.session,
            media_session=self.session,
        )

    def base_url(self):
        return "https://max.test"

    def _handler(self, request):
        self.requests.append(request)
        if self.status >= 400:
            return httpx.Response(
                self.status,
                json=self.error_body
                or {"code": "proto.payload", "message": "private body"},
            )
        if request.url.path.endswith("/answers"):
            return httpx.Response(
                self.status, json={"success": self.answer_success}
            )
        return httpx.Response(
            self.status, json={"message": {"body": {"mid": "m-1"}}}
        )

    async def test_send_message_uses_markdown_and_wraps_keyboard_in_list(self):
        keyboard = {"type": "inline_keyboard", "payload": {"buttons": []}}

        await self.client.send_message(42, "**Text**", keyboard)

        request = self.requests[-1]
        self.assertEqual(request.method, "POST")
        self.assertIn("/messages", request.url.path)
        self.assertEqual(request.url.params["chat_id"], "42")
        self.assertEqual(request.headers["authorization"], "bot-token")
        body = json.loads(request.content)
        self.assertEqual(body["format"], "markdown")
        self.assertEqual(body["text"], "**Text**")
        self.assertEqual(body["attachments"], [keyboard])

    async def test_send_message_without_attachments_has_no_field(self):
        await self.client.send_message(42, "Text")

        body = json.loads(self.requests[-1].content)
        self.assertNotIn("attachments", body)

    async def test_edit_message_puts_by_message_id(self):
        keyboard = {"type": "inline_keyboard", "payload": {"buttons": []}}

        await self.client.edit_message("mid-1", 42, "**New**", keyboard)

        request = self.requests[-1]
        self.assertEqual(request.method, "PUT")
        self.assertEqual(request.url.params["message_id"], "mid-1")
        self.assertEqual(request.url.params["chat_id"], "42")
        body = json.loads(request.content)
        self.assertEqual(body["text"], "**New**")
        self.assertEqual(body["attachments"], [keyboard])
        self.assertEqual(body["format"], "markdown")

    async def test_edit_message_with_none_keeps_attachments_and_list_clears(
        self,
    ):
        await self.client.edit_message("mid-1", 42, "no buttons", None)
        self.assertNotIn("attachments", json.loads(self.requests[-1].content))

        await self.client.edit_message("mid-1", 42, "remove buttons", [])
        self.assertEqual(
            json.loads(self.requests[-1].content)["attachments"], []
        )

    async def test_answer_callback_sends_one_time_notification(self):
        await self.client.answer_callback("cb-1", "Done ✅")

        request = self.requests[-1]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.params["callback_id"], "cb-1")
        # The MAX CallbackAnswer schema knows only message and notification:
        # the server rejects text/alert with a 400.
        self.assertEqual(
            json.loads(request.content), {"notification": "Done ✅"}
        )

    async def test_answer_callback_updates_the_pressed_message(self):
        keyboard = {"type": "inline_keyboard", "payload": {"buttons": []}}
        message = {
            "text": "**List**",
            "format": "markdown",
            "attachments": [keyboard],
        }

        await self.client.answer_callback("cb-1", "Done ✅", message=message)

        request = self.requests[-1]
        self.assertEqual(request.method, "POST")
        self.assertIn("/answers", request.url.path)
        self.assertEqual(request.url.params["callback_id"], "cb-1")
        self.assertEqual(
            json.loads(request.content),
            {"notification": "Done ✅", "message": message},
        )

    async def test_answer_callback_with_message_only_has_no_notification(self):
        await self.client.answer_callback(
            "cb-1", message={"text": "List", "attachments": []}
        )

        self.assertEqual(
            json.loads(self.requests[-1].content),
            {"message": {"text": "List", "attachments": []}},
        )

    async def test_answer_callback_success_false_is_an_error(self):
        self.answer_success = False

        with self.assertRaises(RemoteServiceError) as ctx:
            await self.client.answer_callback("cb-1", "Done ✅")

        self.assertEqual(ctx.exception.code, "success_false")

    async def test_answer_callback_without_text_makes_no_request(self):
        self.assertIsNone(await self.client.answer_callback("cb-1"))
        self.assertIsNone(await self.client.answer_callback("cb-1", ""))

        self.assertEqual(self.requests, [])

    async def test_http_error_keeps_max_error_code(self):
        self.status = 400
        self.error_body = {"code": "proto.payload", "message": "private"}

        with self.assertRaises(RemoteServiceError) as ctx:
            await self.client.send_message(42, "Text")

        self.assertEqual(ctx.exception.code, "proto.payload")
        self.assertNotIn("private", str(ctx.exception))

    async def test_http_error_becomes_remote_service_error(self):
        self.status = 400

        with self.assertRaises(RemoteServiceError) as ctx:
            await self.client.send_message(42, "Text")

        self.assertEqual(ctx.exception.service, "MAX")
        self.assertEqual(ctx.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
