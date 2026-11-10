"""FastAPI adapter for the MAX webhook.

Requires the ``fastapi`` extra::

    pip install mbtk[fastapi]
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response

from . import DEFAULT_MAX_BODY_BYTES, accept_webhook, readiness


def create_app(
    queue,
    secret: str,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
):
    """Build an ASGI app with ``/webhook`` and ``/healthz`` routes."""

    @asynccontextmanager
    async def lifespan(_app):
        yield
        close = getattr(queue, "aclose", None)
        if close is not None:
            await close()

    app = FastAPI(
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/healthz")
    async def healthz():
        status, body = await readiness(queue)
        return _response(status, body)

    @app.post("/webhook")
    async def webhook(request: Request):
        content_length = request.headers.get("content-length")
        if content_length is None:
            return _response(411, b"content length required")
        try:
            length = int(content_length)
        except ValueError:
            return _response(400, b"invalid content length")
        if length < 0:
            return _response(411, b"content length required")
        if length > max_body_bytes:
            return _response(413, b"request too large")

        body = await request.body()
        status, payload = await accept_webhook(
            request.headers,
            body,
            queue,
            secret,
            max_body_bytes,
        )
        return _response(status, payload)

    return app


def serve(
    queue,
    *,
    secret: str,
    port: int,
    host: str = "0.0.0.0",
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
):
    """Run the webhook app with uvicorn."""
    import uvicorn

    app = create_app(queue, secret, max_body_bytes)
    uvicorn.run(app, host=host, port=port)


def _response(status: int, body: bytes):
    media_type = "text/plain; charset=utf-8"
    return Response(
        content=body,
        status_code=status,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )
