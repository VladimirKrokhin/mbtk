"""Asynchronous client for the MAX Bot API.

Requires the ``max`` extra::

    pip install mbtk[max]
"""

import ssl
from urllib.parse import quote, urlsplit

import httpx

from ..errors import RemoteServiceError

MAX_IMAGE_BYTES = 10 * 1024 * 1024


class InvalidMediaUrlError(ValueError):
    """MAX returned an unsafe media URL or an unsupported image response."""


class MaxApiClient:
    """Small asynchronous client for the MAX Bot API.

    ``access_token`` is used as the ``Authorization`` header value. When
    ``ca_bundle`` is set, TLS verification uses that CA bundle; otherwise
    the system default trust store is used.
    """

    MAX_IMAGE_BYTES = MAX_IMAGE_BYTES

    def __init__(
        self,
        base_url,
        access_token,
        ca_bundle=None,
        session=None,
        media_hosts=None,
        media_session=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_host = urlsplit(self.base_url).hostname
        self.ca_bundle = ca_bundle
        self.access_token = access_token
        self.media_hosts = {self.api_host} | {
            str(host).strip().lower().rstrip(".")
            for host in media_hosts or ()
            if str(host).strip()
        }
        verify = (
            ssl.create_default_context(cafile=ca_bundle) if ca_bundle else True
        )
        self.session = session or httpx.AsyncClient(timeout=15, verify=verify)
        self.media_session = media_session or httpx.AsyncClient(
            timeout=15, verify=verify
        )
        self.session.headers.update(
            {"Authorization": access_token, "Accept": "application/json"}
        )

    async def send_message(self, chat_id, text, attachments=None):
        body = {"text": text}
        # MAX only understands markdown when the flag is present; without
        # it, ``**...**`` and links stay raw in the message text.
        body["format"] = "markdown"
        if attachments:
            # Attachments are always a list: MAX rejects a single object
            # (for example, a keyboard) with a 400 "Can't deserialize body".
            body["attachments"] = (
                [attachments]
                if isinstance(attachments, dict)
                else list(attachments)
            )
        return await self._request(
            "POST", "/messages", params={"chat_id": chat_id}, json=body
        )

    async def edit_message(self, message_id, chat_id, text, attachments=None):
        """Edit a message sent by the bot (for in-place screen updates)."""
        body = {"text": text, "format": "markdown"}
        if attachments is not None:
            body["attachments"] = (
                [attachments]
                if isinstance(attachments, dict)
                else list(attachments)
            )
        data = await self._request(
            "PUT",
            "/messages",
            params={"message_id": message_id, "chat_id": chat_id},
            json=body,
        )
        # MAX returns 200 even when the edit was not applied. Without this
        # check the bot believes the screen is updated while the user still
        # sees the old message.
        if isinstance(data, dict) and data.get("success") is False:
            raise RemoteServiceError(
                "MAX rejected the message edit",
                400,
                service="MAX",
                code="success_false",
            )
        return data

    async def answer_callback(
        self, callback_id, text=None, alert=False, message=None
    ):
        """Answer a button press: a notification and/or a message update.

        MAX applies ``message`` to the message whose button was pressed, so
        no ``mid`` is needed and a list can be updated for the whole shift.
        The ``CallbackAnswer`` schema knows only ``message`` and
        ``notification``; the server rejects ``text``/``alert`` with a 400.
        An empty body is rejected as well, so no request is sent when both
        arguments are missing.
        """
        body = {}
        if text:
            body["notification"] = text
        if message:
            body["message"] = message
        if not body:
            return None
        data = await self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json=body,
        )
        # MAX returns 200 even when the answer was not applied.
        if isinstance(data, dict) and data.get("success") is False:
            raise RemoteServiceError(
                "MAX rejected the callback answer",
                400,
                service="MAX",
                code="success_false",
            )
        return data

    async def get_message(self, message_id):
        return await self._request(
            "GET", f"/messages/{quote(str(message_id), safe='')}"
        )

    async def download_image(self, url, max_bytes=MAX_IMAGE_BYTES):
        parsed = self._validate_media_url(url)
        headers = {"Accept": "image/*"}
        if parsed.hostname.lower().rstrip(".") == self.api_host:
            headers["Authorization"] = self.access_token

        try:
            async with self.media_session.stream(
                "GET", url, headers=headers, follow_redirects=False
            ) as response:
                if 300 <= response.status_code < 400:
                    raise InvalidMediaUrlError("Redirects are not allowed")
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if content_type and not content_type.lower().startswith(
                    "image/"
                ):
                    raise InvalidMediaUrlError(
                        "MAX media URL did not return an image"
                    )
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_bytes:
                    raise InvalidMediaUrlError(
                        "MAX image exceeds the size limit"
                    )

                chunks = []
                total = 0
                async for chunk in response.aiter_bytes(64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise InvalidMediaUrlError(
                            "MAX image exceeds the size limit"
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
        except InvalidMediaUrlError:
            raise
        except (TypeError, ValueError):
            raise InvalidMediaUrlError("Invalid MAX image response") from None
        except httpx.HTTPError as error:
            status = _error_status(error)
            raise RemoteServiceError(
                "Failed to download the MAX image", status, service="MAX"
            ) from None

    def _validate_media_url(self, url):
        if not isinstance(url, str) or len(url) > 4096:
            raise InvalidMediaUrlError("Invalid MAX media URL")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            raise InvalidMediaUrlError("Invalid MAX media URL") from None

        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.fragment
            or port not in (None, 443)
            or host not in self.media_hosts
        ):
            raise InvalidMediaUrlError("Untrusted MAX media URL")
        return parsed

    async def _request(self, method, path, **kwargs):
        try:
            response = await self.session.request(
                method,
                f"{self.base_url}{path}",
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            raise RemoteServiceError(
                "MAX API request failed",
                error.response.status_code,
                service="MAX",
                code=_error_code(error.response),
            ) from None
        except httpx.HTTPError as error:
            raise RemoteServiceError(
                "MAX API request failed",
                _error_status(error),
                service="MAX",
            ) from None
        except ValueError:
            raise RemoteServiceError(
                "MAX API returned invalid JSON", service="MAX"
            ) from None

    async def aclose(self):
        """Close HTTP sessions, without closing a shared one twice."""
        sessions = {
            id(self.session): self.session,
            id(self.media_session): self.media_session,
        }
        for session in sessions.values():
            await session.aclose()


def _error_status(error):
    response = getattr(error, "response", None)
    return response.status_code if response is not None else None


def _error_code(response):
    """Short error code from the MAX response body, without its text."""
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    code = data.get("code")
    return str(code)[:64] if code is not None else None
