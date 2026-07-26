"""Shared SSRF guard for outbound, user-supplied URLs.

Any server-side fetch to a URL a user controls must pass through here: only
http(s), no embedded credentials, and every address the hostname resolves to
must be globally routable. Reused by the ``data_fetch`` tool and the custom
OpenAI-compatible LLM endpoint (CLAUDE.md §9.3/§9.4).

This module only validates the URL it is handed; it does not follow redirects,
so a caller that follows them must re-check each hop or the final URL itself.
The ``data_fetch`` tool's scrapling engine gets that for free from libcurl's
SAFE redirect mode (which refuses hops to internal addresses outright) and
re-validates the landed URL on top; the custom LLM endpoint does not follow
redirects at all.

Residual risk: a DNS-rebinding window between the resolve check and the actual
connection is not closed at this tier (the resolved IP is not pinned to the
socket). Documented and accepted.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Reasons are returned (not raised) so callers can shape them into their own
# error type (a tool notice, an HTTP 422, or an LLMError).
REASON_BAD_SCHEME = "only http(s) URLs are allowed"
REASON_CREDENTIALS = "URLs with embedded credentials are not allowed"
REASON_NO_HOST = "URL has no hostname"
REASON_NOT_PUBLIC = "host is not publicly routable"


def validate_url_shape(url: str) -> str | None:
    """Return a rejection reason for a structurally-unsafe URL, or None.

    Cheap and synchronous (no DNS) — safe to call from request/schema
    validation where blocking network I/O is not acceptable.
    """
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        return REASON_BAD_SCHEME
    if parts.username or parts.password:
        return REASON_CREDENTIALS
    if not parts.hostname:
        return REASON_NO_HOST
    return None


def resolve_is_public(hostname: str) -> bool:
    """True only if every resolved address is globally routable (anti-SSRF)."""
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return False
    return all(ipaddress.ip_address(address).is_global for address in addresses)


async def check_public_url(url: str) -> str | None:
    """Full async SSRF check: URL shape + resolved-address routability.

    Returns a rejection reason, or None if the URL is safe to reach. DNS
    resolution runs in a worker thread so the event loop is not blocked.
    """
    reason = validate_url_shape(url)
    if reason is not None:
        return reason
    hostname = urlsplit(url).hostname or ""
    if not await asyncio.to_thread(resolve_is_public, hostname):
        return REASON_NOT_PUBLIC
    return None
