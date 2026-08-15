"""Authenticated HTTP transport that never follows a redirect.

Python's default redirect handler copies request headers to the target. That behavior is convenient
for ordinary GETs and unsafe for API keys or bearer tokens. HawEdit's authenticated cloud calls use
this boundary so a provider/proxy redirect becomes an HTTP 3xx refusal at the original origin.
"""

from __future__ import annotations

from typing import Any, Final
from urllib.request import HTTPRedirectHandler, Request, build_opener

__all__ = ["open_without_redirects"]


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


_NO_REDIRECT_OPENER: Final = build_opener(_RejectRedirects())


def open_without_redirects(request: Request, *, timeout: float) -> Any:
    """Open `request` without ever contacting a redirect target."""
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)
