"""End-to-end pipeline test: webhook -> queue -> worker -> dispatcher -> MAX.

The fake MAX server is a real HTTP server, so the MAX client exercises the
same network path as in production. The webhook is called through the ASGI
app, and the queue is in memory.
"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx

from mbtk import Dispatcher, Router
from mbtk.filters import Command, Payload
from mbtk.max.client import MaxApiClient
from mbtk.max.updates import event_id_for
from mbtk.transport import QueuedUpdate
from mbtk.webhook.fastapi import create_app
from mbtk.worker import process_once

SECRET = "e2e-secret"


class FakeMax:
    """A real HTTP server that records outgoing MAX API calls."""

    def __init__(self):
        self.sent = []
        self.answers = []
        self.failures = []
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), self._handler_class()
        )
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True
        )
        self.base_url = ""

    def start(self):
        self.thread.start()
        host, port = self.httpd.server_address
        self.base_url = f"http://{host}:{port}"
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def fail(self, method, path, status=500, times=1):
        for _ in range(times):
            self.failures.append((method, path, status))

    def _take_error(self, method, path):
        for index, (want_method, want_path, status) in enumerate(self.failures):
            if want_method == method and want_path == path:
                self.failures.pop(index)
                return status
        return None

    def _handler_class(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                path = urlsplit(self.path).path
                query = parse_qs(urlsplit(self.path).query)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw or b"{}")
                status = fake._take_error("POST", path)
                if status is not None:
                    fake._reply(self, status, {"code": "test_error"})
                    return
                if path == "/messages":
                    fake.sent.append((query, body))
                    fake._reply(
                        self,
                        200,
                        {"message": {"body": {"mid": f"mid-{len(fake.sent)}"}}},
                    )
                    return
                if path == "/answers":
                    fake.answers.append((query, body))
                    fake._reply(self, 200, {"success": True})
                    return
                fake._reply(self, 404, {"code": "not_found"})

            def log_message(self, *args):
                pass

        return Handler

    @staticmethod
    def _reply(handler, status, payload):
        data = json.dumps(payload).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)


class MemoryQueue:
    """At-least-once queue with redelivery of unacknowledged entries."""

    def __init__(self):
        self.new = []
        self.in_flight = {}
        self.acknowledged = []
        self.failures = {}
        self.counter = 0

    async def enqueue(self, update):
        self.counter += 1
        record = QueuedUpdate(
            f"entry-{self.counter}", event_id_for(update), update
        )
        self.new.append(record)
        return record.event_id

    async def is_ready(self):
        return True

    async def ensure_group(self):
        return None

    async def read(self, consumer, count=10):
        records = list(self.in_flight.values())
        if len(records) < count:
            added = self.new[: count - len(records)]
            self.new = self.new[len(added) :]
            for record in added:
                self.in_flight[record.entry_id] = record
            records.extend(added)
        return records[:count]

    async def acknowledge(self, entry_id):
        self.acknowledged.append(entry_id)
        self.in_flight.pop(entry_id, None)

    async def record_failure(self, entry_id):
        self.failures[entry_id] = self.failures.get(entry_id, 0) + 1
        return self.failures[entry_id]

    async def clear_failure(self, entry_id):
        self.failures.pop(entry_id, None)


class DispatcherProcessor:
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    async def process(self, update):
        return await self.dispatcher.feed_update(update)


def message_update(text="/ping", chat_id="10", user_id="20"):
    return {
        "update_id": "u-1",
        "update_type": "message_created",
        "message": {
            "body": {"mid": "m-1", "text": text},
            "recipient": {"chat_id": chat_id, "chat_type": "dialog"},
            "sender": {"user_id": user_id},
        },
    }


def callback_update():
    return {
        "update_id": "u-2",
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb-1",
            "payload": {"a": "ping"},
            "chat_id": "10",
            "chat_type": "dialog",
            "user": {"user_id": "20"},
            "message": {
                "body": {"mid": "m-1"},
                "recipient": {"chat_id": "10", "chat_type": "dialog"},
            },
        },
    }


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake_max = FakeMax().start()
        self.addCleanup(self.fake_max.stop)

        self.queue = MemoryQueue()
        self.max_api = MaxApiClient(self.fake_max.base_url, "bot-token")
        self.addAsyncCleanup(self.max_api.aclose)

        self.router = Router("echo")

        @self.router.message(Command("ping"))
        async def ping(event):
            await event.answer("pong")

        @self.router.callback_query(Payload("ping"))
        async def callback(event):
            await event.answer("pong")

        self.dispatcher = Dispatcher(bot=self.max_api)
        self.dispatcher.include_router(self.router)
        self.processor = DispatcherProcessor(self.dispatcher)

        self.app = create_app(self.queue, SECRET)
        self.webhook = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://test",
        )
        self.addAsyncCleanup(self.webhook.aclose)

    async def post(self, update, secret=SECRET):
        return await self.webhook.post(
            "/webhook",
            content=json.dumps(update),
            headers={"X-Max-Bot-Api-Secret": secret},
        )

    async def test_message_flows_from_webhook_to_max(self):
        response = await self.post(message_update())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.queue.new), 1)

        processed = await process_once(self.queue, self.processor, "worker-1")

        self.assertEqual(processed, 1)
        self.assertEqual(self.queue.acknowledged, ["entry-1"])
        query, body = self.fake_max.sent[0]
        self.assertEqual(query["chat_id"], ["10"])
        self.assertEqual(body["text"], "pong")
        self.assertEqual(body["format"], "markdown")
        self.assertNotIn("attachments", body)

    async def test_callback_is_answered_with_a_notification(self):
        response = await self.post(callback_update())

        self.assertEqual(response.status_code, 200)
        await process_once(self.queue, self.processor, "worker-1")

        query, body = self.fake_max.answers[0]
        self.assertEqual(query["callback_id"], ["cb-1"])
        self.assertEqual(body, {"notification": "pong"})
        self.assertEqual(self.queue.acknowledged, ["entry-1"])

    async def test_transient_error_keeps_update_for_retry(self):
        self.fake_max.fail("POST", "/messages", status=503)
        await self.post(message_update())

        await process_once(self.queue, self.processor, "worker-1")

        self.assertEqual(self.queue.acknowledged, [])
        self.assertEqual(self.queue.failures["entry-1"], 1)
        self.assertEqual(self.fake_max.sent, [])

        await process_once(self.queue, self.processor, "worker-1")

        self.assertEqual(self.queue.acknowledged, ["entry-1"])
        self.assertEqual(len(self.fake_max.sent), 1)

    async def test_permanent_error_is_acknowledged_and_dropped(self):
        self.fake_max.fail("POST", "/messages", status=403)
        await self.post(message_update())

        await process_once(self.queue, self.processor, "worker-1")

        self.assertEqual(self.queue.acknowledged, ["entry-1"])
        self.assertNotIn("entry-1", self.queue.failures)
        self.assertEqual(self.fake_max.sent, [])

    async def test_bad_webhook_secret_is_rejected(self):
        response = await self.post(message_update(), secret="wrong")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.queue.new, [])


if __name__ == "__main__":
    unittest.main()
