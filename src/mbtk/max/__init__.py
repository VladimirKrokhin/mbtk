"""MAX Bot API integration.

The client is optional and requires the ``max`` extra::

    pip install mbtk[max]
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import InvalidMediaUrlError, MaxApiClient

__all__ = ["InvalidMediaUrlError", "MaxApiClient"]


def __getattr__(name):
    if name in __all__:
        from . import client

        return getattr(client, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
