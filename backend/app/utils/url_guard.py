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

DNS rebinding: :func:`check_public_url` validates the addresses a name resolves
to *now*, and cannot stop the name resolving elsewhere by the time a socket
opens. :func:`pin_public_url` closes that window for callers that can use it, by
handing back the validated literal address to connect to plus the original name
to present in ``Host`` and SNI — so the connection lands on the address that was
checked, while TLS still verifies against the real hostname.

Pinning is not free and not universal: it is used by the paths where the host is
*user-supplied* (custom API tools, MCP servers, plugin manifest imports). The
``data_fetch`` tool keeps the unpinned check because its engine drives libcurl,
which does its own SAFE-mode redirect refusal and never exposes a socket to pin.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Reasons are returned (not raised) so callers can shape them into their own
# error type (a tool notice, an HTTP 422, or an LLMError).
REASON_BAD_SCHEME = "only http(s) URLs are allowed"
REASON_CREDENTIALS = "URLs with embedded credentials are not allowed"
REASON_NO_HOST = "URL has no hostname"
REASON_NOT_PUBLIC = "host is not publicly routable"
# Separated from the above because they send a user to different places. A
# typo'd hostname reported as "not publicly routable" reads as a network policy
# problem, and someone will go looking for one; observed while testing a real
# MCP endpoint against a hostname that simply did not exist.
REASON_NO_DNS = "host could not be resolved"


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


def resolve_addresses(hostname: str) -> set[str] | None:
    """Every address a hostname resolves to, or None when it resolves to none.

    ``None`` and an empty set mean different things to a caller: the first is a
    name that does not exist, the second cannot happen here but would be a
    resolver returning nothing for a name that does.
    """
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return None
    return {info[4][0] for info in infos} or None


def resolve_is_public(hostname: str) -> bool:
    """True only if every resolved address is globally routable (anti-SSRF).

    Kept for callers that only need the boolean. A caller that wants to tell a
    user *why* should use :func:`resolution_failure`, which distinguishes a name
    that does not exist from one that points somewhere it should not.
    """
    addresses = resolve_addresses(hostname)
    if addresses is None:
        return False
    return all(ipaddress.ip_address(address).is_global for address in addresses)


def resolution_failure(hostname: str) -> str | None:
    """A rejection reason for a hostname's addresses, or None if it is safe.

    Layered on :func:`resolve_is_public` rather than replacing it: that function
    is the gate ``data_fetch_service`` imports and every SSRF test substitutes,
    and moving the decision out from under it would quietly stop those
    substitutions governing anything. The second lookup only runs on the failure
    path, where one extra resolve costs nothing and buys a message the user can
    act on.
    """
    if resolve_is_public(hostname):
        return None
    return REASON_NO_DNS if resolve_addresses(hostname) is None else REASON_NOT_PUBLIC


async def check_public_url(url: str) -> str | None:
    """Full async SSRF check: URL shape + resolved-address routability.

    Returns a rejection reason, or None if the URL is safe to reach. DNS
    resolution runs in a worker thread so the event loop is not blocked.
    """
    reason = validate_url_shape(url)
    if reason is not None:
        return reason
    hostname = urlsplit(url).hostname or ""
    return await asyncio.to_thread(resolution_failure, hostname)


@dataclass(frozen=True, slots=True)
class PinnedTarget:
    """Where to connect, and whose name to present once connected.

    ``url`` carries the validated literal address in place of the hostname, so
    the socket cannot land anywhere else. ``host_header`` and ``sni_hostname``
    carry the original name, so virtual hosting still routes and TLS still
    verifies the certificate against the name the user typed — pinning the
    address must not become "skip certificate checking".
    """

    url: str
    host_header: str
    sni_hostname: str


def _pin(url: str) -> tuple[PinnedTarget | None, str | None]:
    """Resolve, validate, and rewrite. Synchronous half of :func:`pin_public_url`."""
    reason = validate_url_shape(url)
    if reason is not None:
        return None, reason
    parts = urlsplit(url)
    hostname = parts.hostname or ""

    addresses = resolve_addresses(hostname)
    if addresses is None:
        return None, REASON_NO_DNS
    if not all(ipaddress.ip_address(address).is_global for address in addresses):
        # Every address, not just the chosen one: a name answering with one
        # public and one private address is exactly the rebinding setup, and
        # picking the public one would make it work.
        return None, REASON_NOT_PUBLIC

    # Sorted rather than arbitrary, so a multi-address host is reached the same
    # way on every call and a failure is reproducible. Only the first is tried:
    # falling back through the rest would need the whole list re-validated per
    # attempt, and a host whose primary address is down reads as unreachable,
    # which is a true statement.
    address = sorted(addresses)[0]
    literal = f"[{address}]" if ipaddress.ip_address(address).version == 6 else address
    netloc = f"{literal}:{parts.port}" if parts.port else literal
    return (
        PinnedTarget(
            url=urlunsplit(
                (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
            ),
            host_header=parts.netloc,
            sni_hostname=hostname,
        ),
        None,
    )


async def pin_public_url(url: str) -> tuple[PinnedTarget | None, str | None]:
    """Validate a URL and pin it to the address that was validated.

    Returns ``(target, None)`` or ``(None, reason)``. Supersedes
    :func:`check_public_url` for callers that connect through it: the check and
    the connection now use the same address, so there is no window between them
    for the name to move.

    DNS runs in a worker thread so the event loop is not blocked, exactly as in
    :func:`check_public_url`.
    """
    return await asyncio.to_thread(_pin, url)
