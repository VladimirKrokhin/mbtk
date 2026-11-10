"""The MAX client protocol seen by events and handlers.

Method names match :class:`mbtk.max.client.MaxApiClient` and test fakes,
so any object with the same methods can be used as a bot.
"""

from typing import Any, Protocol


class Bot(Protocol):
    """Minimal interface the dispatcher needs from a MAX client."""

    async def send_message(
        self,
        chat_id: str,
        text: str,
        attachments: Any = None,
    ) -> dict: ...

    async def edit_message(
        self,
        message_id: str,
        chat_id: str,
        text: str,
        attachments: Any = None,
    ) -> dict: ...

    async def answer_callback(
        self,
        callback_id: str,
        text: str | None = None,
        alert: bool = False,
        message: dict | None = None,
    ) -> dict: ...

    async def get_message(self, message_id: str) -> dict: ...

    async def download_image(self, url: str) -> bytes: ...
