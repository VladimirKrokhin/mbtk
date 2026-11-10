# mbtk — MAX Bot Toolkit

[![CI](https://github.com/VladimirKrokhin/mbtk/actions/workflows/ci.yml/badge.svg)](https://github.com/VladimirKrokhin/mbtk/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mbtk.svg)](https://pypi.org/project/mbtk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Небольшой асинхронный тулкит для ботов в мессенджере **MAX**. Вдохновлён
[aiogram 3](https://github.com/aiogram/aiogram): типизированные события,
роутеры, композируемые фильтры, middleware, внедрение зависимостей по именам
аргументов и FSM.

Ядро не имеет runtime-зависимостей. HTTP-клиент MAX и Redis-хранилище FSM
подключаются как extras.

> Проект неофициальный и не связан с VK или командой MAX.

[English version](README.en.md)

## Возможности

- `Dispatcher.feed_update()` превращает raw update в типизированное событие.
- Роутеры-деревья: первый подходящий обработчик выигрывает, `SkipHandler`
  передаёт событие следующему.
- Фильтры собираются через `&`, `|` и `~`: `Command`, `Payload`, `StateIs`,
  `HasPhoto`, `TextRegexp` и другие.
- Middleware на уровне диспетчера, роутера и конкретного observer'а.
- DI: обработчик получает только те аргументы, которые объявил.
- FSM: `State`, `StatesGroup`, `FSMContext`, in-memory хранилище и контракт
  `FSMStorage`.
- Атомарный `claim` для одноразовых действий (например, «фото обработано
  один раз»).
- Обработчик всегда дожидается завершения: очередь может подтвердить событие
  только после успеха.

## Установка

```sh
pip install mbtk               # ядро
pip install "mbtk[max]"        # + MaxApiClient
pip install "mbtk[redis]"      # + RedisFSMStorage и RedisStreamQueue
pip install "mbtk[fastapi]"    # + ASGI-webhook
pip install "mbtk[all]"        # всё сразу
```

Нужен Python 3.10+.

## Быстрый старт

```python
import asyncio

from mbtk import Dispatcher, Router
from mbtk.filters import Command

router = Router("main")


@router.message(Command("start"))
async def start(event):
    await event.answer("Привет! Отправь /echo <текст>.")


@router.message(Command("echo"))
async def echo(event):
    await event.answer(event.arguments or "Нечего повторять")


dispatcher = Dispatcher(bot=bot)  # bot = MaxApiClient(...)
dispatcher.include_router(router)


async def handle_update(update):
    return await dispatcher.feed_update(update)
```

`update` — это JSON-тело вебхука MAX. `bot` — объект с методами из
`mbtk.bot.Bot`; в продакшене это `MaxApiClient`, в тестах — заглушка.

## Клиент MAX API

```python
import os

from mbtk.max.client import MaxApiClient

bot = MaxApiClient(
    "https://platform-api2.max.ru",
    access_token=os.environ["MAX_ACCESS_TOKEN"],
    ca_bundle=os.environ.get("MAX_CA_BUNDLE"),  # None — системные CA
)

await bot.send_message(chat_id, "**Привет**")
```

Клиент умеет отправлять и править сообщения, отвечать на callback и
скачивать изображения с проверкой хоста, схемы, размера и редиректов.

Строители клавиатур и вложений:

```python
from mbtk.max.keyboards import button, keyboard, location_attachment

board = keyboard([[button("Меню", {"a": "menu"})]])
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

Хранилище синхронное намеренно: это локальные вызовы Redis без блокирующих
чтений. Используйте `redis.Redis`, а не `redis.asyncio`.

Своё хранилище можно подключить, реализовав протокол `mbtk.fsm.FSMStorage`.

## Очередь, webhook и worker

`mbtk.transport` описывает контракты очереди, `mbtk.transport.redis_stream`
содержит реализацию на Redis Streams:

```python
from mbtk.transport.redis_stream import RedisStreamQueue

queue = RedisStreamQueue.from_url(os.environ["REDIS_URL"])
await queue.ensure_group()
```

Проверка webhook без привязки к фреймворку:

```python
from mbtk.webhook import accept_webhook, validate_webhook
```

Готовый ASGI-адаптер (extra `[fastapi]`):

```python
from mbtk.webhook.fastapi import create_app

app = create_app(queue, secret=os.environ["MAX_WEBHOOK_SECRET"])
```

Worker обрабатывает батчи через протокол `Processor`:

```python
from mbtk.worker import process_once, termination_signals


class MyProcessor:
    async def process(self, update): ...


with termination_signals(stop_event):
    await process_once(queue, MyProcessor(), "worker-1")
```

Worker не знает про доменные события: всё, что нужно приложению, живёт
в `Processor.process`.

## Кэш

```python
from mbtk.cache.redis import RedisCache

cache = RedisCache(redis, prefix="myapp:ctx", ttl=30)
await cache.set(("chat", "user"), {"role": "courier"})
```

`MemoryCache` и `NullCache` доступны из `mbtk.cache`.

## Обработка ошибок

```python
from mbtk.middleware.errors import DefaultErrorPolicy, ErrorMiddleware

middleware = ErrorMiddleware(DefaultErrorPolicy())
```

Своя политика реализует `ErrorPolicy`: transient → повтор, silent → без
сообщения, остальное → текст пользователю и callback alert.

## Основные понятия

| Понятие | Модуль | Назначение |
| --- | --- | --- |
| `Dispatcher` | `mbtk` | Корневой роутер и точка входа `feed_update`. |
| `Router` | `mbtk` | Группа обработчиков и дочерних роутеров. |
| `Observer` | `mbtk.router` | `router.message`, `router.callback_query`, `router.bot_started`, `router.error`. |
| Фильтры | `mbtk.filters` | Условия выбора обработчика. |
| `BaseMiddleware` | `mbtk` | Обёртка вокруг обработчика. |
| `FSMContext` | `mbtk` | Состояние и данные диалога. |
| `MemoryStorage` | `mbtk` | Хранилище FSM в памяти для тестов. |

## Статус

Версия `0.2.x`: API может меняться до `1.0`. Ломающие изменения
фиксируются в [CHANGELOG](CHANGELOG.md).

## Разработка

```sh
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Пример без сети — `examples/echo_bot/main.py`.

## Лицензия

MIT. См. [LICENSE](LICENSE).
