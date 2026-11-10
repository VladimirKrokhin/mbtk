"""Typed MAX events."""

from dataclasses import dataclass, field

from .bot import Bot


@dataclass
class Event:
    """Common fields of any dialogue event."""

    event_id: str
    chat_id: str
    user_id: str
    chat_type: str
    raw: dict = field(repr=False)
    bot: Bot | None = field(default=None, repr=False)


@dataclass
class Message(Event):
    """An incoming message."""

    text: str = ""
    message_id: str = ""
    body: dict = field(default_factory=dict, repr=False)
    message: dict = field(default_factory=dict, repr=False)

    @property
    def attachments(self) -> list:
        value = self.body.get("attachments")
        return value if isinstance(value, list) else []

    @property
    def command(self) -> str:
        """First command token without ``@bot``, lowercased."""
        if not self.text:
            return ""
        token = self.text.split(maxsplit=1)[0]
        return token.split("@", 1)[0].lower()

    @property
    def arguments(self) -> str:
        """Everything after the command token, case preserved."""
        parts = self.text.split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    async def answer(self, text, attachments=None):
        if self.bot is None:
            raise RuntimeError("The event has no attached bot")
        return await self.bot.send_message(self.chat_id, text, attachments)


@dataclass
class Callback(Event):
    """An inline button press."""

    callback_id: str = ""
    payload: dict = field(default_factory=dict)
    message_id: str = ""
    answered: bool = field(default=False, repr=False)

    async def answer(self, text=None, alert=False, message=None):
        if self.bot is None or not self.callback_id:
            return None
        result = await self.bot.answer_callback(
            self.callback_id, text, alert, message
        )
        self.answered = True
        return result


@dataclass
class BotStarted(Event):
    """The user pressed Start in the bot dialogue."""

    user: dict = field(default_factory=dict, repr=False)

    async def answer(self, text, attachments=None):
        if self.bot is None:
            raise RuntimeError("The event has no attached bot")
        return await self.bot.send_message(self.chat_id, text, attachments)
