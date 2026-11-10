# mbtk — MAX Bot Toolkit

[![CI](https://github.com/VladimirKrokhin/mbtk/actions/workflows/ci.yml/badge.svg)](https://github.com/VladimirKrokhin/mbtk/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mbtk.svg)](https://pypi.org/project/mbtk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A small async toolkit for bots in the **MAX** messenger. Inspired by
[aiogram 3](https://github.com/aiogram/aiogram): typed events, routers,
composable filters, middleware, dependency injection by argument name, and
finite state machines.

The core has no runtime dependencies. The MAX HTTP client and the Redis FSM
storage are available as extras.

> This project is unofficial and is not affiliated with VK or the MAX team.

[Русская версия](README.md)

## Features

- `Dispatcher.feed_update()` turns a raw update into a typed event.
- Router trees: the first matching handler wins, and `SkipHandler` passes
  the event to the next one.
- Filters compose with `&`, `|`, and `~`: `Command`, `Payload`, `StateIs`,
  `HasPhoto`, `TextRegexp`, and more.
- Middleware at the dispatcher, router, and observer levels.
- DI: a handler receives only the arguments it declares.
- FSM: `State`, `StatesGroup`, `FSMContext`, an in-memory storage, and the
  `FSMStorage` protocol.
- Atomic `claim` for one-shot actions (for example, "process this photo
  once").
- Handlers are always awaited, so a queue can acknowledge an event only
  after success.

## Install

```sh
pip install mbtk             # core
pip install "mbtk[max]"      # + MaxApiClient
pip install "mbtk[redis]"    # + RedisFSMStorage
pip install "mbtk[all]"      # everything
```

Python 3.10+ is required.

## Quick start

```python
from mbtk import Dispatcher, Router
from mbtk.filters import Command

router = Router("main")


@router.message(Command("start"))
async def start(event):
    await event.answer("Hello! Send /echo <text>.")


@router.message(Command("echo"))
async def echo(event):
    await event.answer(event.arguments or "Nothing to echo")


dispatcher = Dispatcher(bot=bot)  # bot = MaxApiClient(...)
dispatcher.include_router(router)


async def handle_update(update):
    return await dispatcher.feed_update(update)
```

`update` is the JSON body of a MAX webhook. `bot` is any object that
implements `mbtk.bot.Bot`: `MaxApiClient` in production, a fake in tests.

## MAX API client

```python
import os

from mbtk.max.client import MaxApiClient

bot = MaxApiClient(
    "https://platform-api2.max.ru",
    access_token=os.environ["MAX_ACCESS_TOKEN"],
    ca_bundle=os.environ.get("MAX_CA_BUNDLE"),  # None uses system CAs
)

await bot.send_message(chat_id, "**Hello**")
```

The client can send and edit messages, answer callbacks, and download images
with host, scheme, size, and redirect checks.

Keyboard and attachment builders:

```python
from mbtk.max.keyboards import button, keyboard, location_attachment

board = keyboard([[button("Menu", {"a": "menu"})]])
attachment = location_attachment(55.7558, 37.6173)
```

## Redis FSM

```python
import os

from redis import Redis

from mbtk import Dispatcher
from mbtk.storage.redis import RedisFSMStorage

storage = RedisFSMStorage(
    Redis.from_url(os.environ["REDIS_URL"]),
    prefix="myapp:fsm:",
    ttl=24 * 3600,
)
dispatcher = Dispatcher(bot=bot, storage=storage)
```

The storage is synchronous on purpose: these are local Redis calls without
blocking reads. Use `redis.Redis`, not `redis.asyncio`.

To plug in another backend, implement the `mbtk.fsm.FSMStorage` protocol.

## Concepts

| Concept | Module | Purpose |
| --- | --- | --- |
| `Dispatcher` | `mbtk` | Root router and the `feed_update` entry point. |
| `Router` | `mbtk` | A group of handlers and child routers. |
| `Observer` | `mbtk.router` | `router.message`, `router.callback_query`, `router.bot_started`, `router.error`. |
| Filters | `mbtk.filters` | Conditions that select a handler. |
| `BaseMiddleware` | `mbtk` | A wrapper around a handler. |
| `FSMContext` | `mbtk` | Dialogue state and data. |
| `MemoryStorage` | `mbtk` | In-memory FSM storage for tests. |

## Status

Version `0.1.x`: the API may change before `1.0`. Breaking changes are
listed in [CHANGELOG](CHANGELOG.md).

## Development

```sh
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

A network-free example lives in `examples/echo_bot/main.py`.

## License

MIT. See [LICENSE](LICENSE).
