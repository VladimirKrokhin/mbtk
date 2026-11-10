# Echo bot example

A network-free example that feeds one raw MAX update into the dispatcher and
prints the bot's replies.

```sh
uv run python examples/echo_bot/main.py
```

## Webhook wiring

In production, pass the JSON body of the MAX webhook to `feed_update`:

```python
from fastapi import FastAPI, Request
from mbtk import Dispatcher
from mbtk.max.client import MaxApiClient

app = FastAPI()
bot = MaxApiClient(base_url, access_token, ca_bundle)
dispatcher = Dispatcher(bot=bot)
dispatcher.include_router(router)


@app.post("/webhook")
async def webhook(request: Request):
    update = await request.json()
    await dispatcher.feed_update(update)
    return {"ok": True}
```

Acknowledge the webhook only after `feed_update` returns if you need
at-least-once delivery: the handler is always awaited, so a queue or a
webhook can retry transient failures safely.
