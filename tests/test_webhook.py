"""Webhook validation and FastAPI adapter tests."""

import json
import unittest

import httpx

from mbtk.webhook import accept_webhook, readiness, validate_webhook
from mbtk.webhook.fastapi import create_app

SECRET = "top-secret"
HEADERS = {"X-Max-Bot-Api-Secret": SECRET}
UPDATE = {"update_id": "u-1", "update_type": "message_created"}


class FakeQueue:
    def __init__(self, ready=True, fail=False):
        self.ready = ready
        self.fail = fail
        self.updates = []
        self.closed = False

    async def enqueue(self, update):
        if self.fail:
            raise RuntimeError("redis is down")
        self.updates.append(update)
        return str(update.get("update_id") or "event")

    async def is_ready(self):
        return self.ready

    async def aclose(self):
        self.closed = True


class ValidateWebhookTests(unittest.TestCase):
    def test_valid_request(self):
        status, update = validate_webhook(
            HEADERS, json.dumps(UPDATE).encode(), SECRET
        )
        self.assertEqual(status, 200)
        self.assertEqual(update, UPDATE)

    def test_bad_secret(self):
        status, body = validate_webhook(
            {"X-Max-Bot-Api-Secret": "wrong"},
            json.dumps(UPDATE).encode(),
            SECRET,
        )
        self.assertEqual((status, body), (401, b"unauthorized"))

    def test_missing_secret(self):
        status, body = validate_webhook({}, json.dumps(UPDATE).encode(), SECRET)
        self.assertEqual((status, body), (401, b"unauthorized"))

    def test_body_too_large(self):
        status, body = validate_webhook(
            HEADERS, b"x" * 10, SECRET, max_body_bytes=5
        )
        self.assertEqual((status, body), (413, b"request too large"))

    def test_invalid_json(self):
        status, body = validate_webhook(HEADERS, b"{", SECRET)
        self.assertEqual((status, body), (400, b"invalid JSON"))

    def test_non_object_update(self):
        status, body = validate_webhook(HEADERS, b"[]", SECRET)
        self.assertEqual((status, body), (400, b"invalid update"))

    def test_header_lookup_is_case_insensitive(self):
        status, _ = validate_webhook(
            {"x-max-bot-api-secret": SECRET},
            json.dumps(UPDATE).encode(),
            SECRET,
        )
        self.assertEqual(status, 200)


class AcceptWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def test_enqueues_valid_update(self):
        queue = FakeQueue()
        status, body = await accept_webhook(
            HEADERS, json.dumps(UPDATE).encode(), queue, SECRET
        )

        self.assertEqual((status, body), (200, b"ok"))
        self.assertEqual(queue.updates, [UPDATE])

    async def test_queue_failure_returns_503(self):
        queue = FakeQueue(fail=True)
        status, body = await accept_webhook(
            HEADERS, json.dumps(UPDATE).encode(), queue, SECRET
        )

        self.assertEqual((status, body), (503, b"queue unavailable"))

    async def test_readiness(self):
        self.assertEqual(await readiness(FakeQueue()), (200, b"ok"))
        self.assertEqual(
            await readiness(FakeQueue(ready=False)), (503, b"not ready")
        )


class FastAPIAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.queue = FakeQueue()
        self.app = create_app(self.queue, SECRET)
        self.transport = httpx.ASGITransport(app=self.app)
        self.client = httpx.AsyncClient(
            transport=self.transport, base_url="http://test"
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_healthz(self):
        response = await self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "ok")

    async def test_webhook_enqueues(self):
        response = await self.client.post(
            "/webhook", content=json.dumps(UPDATE), headers=HEADERS
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "ok")
        self.assertEqual(self.queue.updates, [UPDATE])

    async def test_webhook_rejects_bad_secret(self):
        response = await self.client.post(
            "/webhook",
            content=json.dumps(UPDATE),
            headers={"X-Max-Bot-Api-Secret": "wrong"},
        )

        self.assertEqual(response.status_code, 401)

    async def test_webhook_rejects_large_body(self):
        app = create_app(self.queue, SECRET, max_body_bytes=5)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook", content=b"x" * 10, headers=HEADERS
            )

        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
