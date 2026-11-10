"""Run the echo bot against a raw update, without network access.

uv run python examples/echo_bot/main.py
"""

import asyncio

from mbtk import Dispatcher, Router
from mbtk.filters import Command

router = Router("echo")


class PrintingBot:
    """Minimal bot that prints outgoing messages instead of calling MAX."""

    async def send_message(self, chat_id, text, attachments=None):
        print(f"[chat {chat_id}] {text}")
        return {"message": {"body": {"mid": "demo"}}}

    async def edit_message(self, message_id, chat_id, text, attachments=None):
        print(f"[chat {chat_id}] edit {message_id}: {text}")
        return {"success": True}

    async def answer_callback(
        self, callback_id, text=None, alert=False, message=None
    ):
        print(f"[callback {callback_id}] {text or '<message update>'}")
        return {"success": True}

    async def get_message(self, message_id):
        return {}

    async def download_image(self, url):
        return b""


@router.message(Command("start"))
async def start(event):
    await event.answer("Hello! Send /echo <text>.")


@router.message(Command("echo"))
async def echo(event):
    await event.answer(event.arguments or "Nothing to echo")


async def main():
    dispatcher = Dispatcher(bot=PrintingBot())
    dispatcher.include_router(router)
    await dispatcher.feed_update(
        {
            "update_id": "demo-1",
            "update_type": "message_created",
            "message": {
                "body": {"mid": "m-1", "text": "/echo hello"},
                "recipient": {"chat_id": 1, "chat_type": "dialog"},
                "sender": {"user_id": 2},
            },
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
