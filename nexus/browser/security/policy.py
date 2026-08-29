from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from nexus.browser.errors.types import BrowserError, ErrorType, BrowserException

_METADATA_HOSTS = {"169.254.169.254", "169.254.170.2", "metadata.google.internal"}


def _canonical_ipv4(host: str) -> str | None:
    try:
        return socket.inet_ntoa(socket.inet_aton(host))
    except (OSError, UnicodeError):
        return None


class NavigationPolicy:
    def __init__(
        self,
        allow_private: bool = False,
        allow_file: bool = False,
        allow_popups: bool = False,
    ) -> None:
        self._allow_private = allow_private
        self._allow_file = allow_file
        self._allow_popups = allow_popups

    @property
    def allow_private(self) -> bool:
        return self._allow_private

    @property
    def allow_popups(self) -> bool:
        return self._allow_popups

    def check(self, url: str) -> str | None:
        if url.strip().lower() == "about:blank":
            return None
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            if parsed.scheme == "file" and self._allow_file:
                return None
            return f"scheme {parsed.scheme!r} is not allowed (http/https only)"
        host = parsed.hostname or ""
        check_host = _canonical_ipv4(host) or host
        if check_host in _METADATA_HOSTS:
            return f"{host} is a cloud metadata endpoint"
        if host == "localhost" or host.endswith(".localhost"):
            if not self._allow_private:
                return "localhost is not allowed (pass allow_private=True to permit)"
            return None
        try:
            addr = ipaddress.ip_address(check_host)
        except ValueError:
            return None
        if (addr.is_private or addr.is_loopback or addr.is_link_local) and not self._allow_private:
            return f"{host} is a private or internal address"
        return None


def enforce(policy: NavigationPolicy, url: str) -> None:
    if reason := policy.check(url):
        raise BrowserException(BrowserError(
            type=ErrorType.NAVIGATION_REFUSED,
            message=f"navigation refused: {reason}",
            confidence=1.0,
            recovery=[],
        ))
