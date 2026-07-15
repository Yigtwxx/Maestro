"""Extract login context (client IP, User-Agent) from a request.

Mirrors the rightmost-``X-Forwarded-For`` rule used by the rate limiter
(``utils.rate_limiter._client_ip``): a proxy appends the peer it actually saw,
so the last hop is the only value a client cannot forge. Kept as a separate,
Request-typed helper so the auth layer does not reach into limiter internals.
"""

from __future__ import annotations

from fastapi import Request

from app.core.config import settings

_UA_MAX_LEN = 400

# Substring -> label, most specific first (Edge/Brave ship "Chrome" in their UA).
_BROWSERS: tuple[tuple[str, str], ...] = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Brave", "Brave"),
    ("Firefox", "Firefox"),
    ("Chrome", "Chrome"),
    ("Safari", "Safari"),
)
_OSES: tuple[tuple[str, str], ...] = (
    ("Windows", "Windows"),
    ("Mac OS X", "macOS"),
    ("Macintosh", "macOS"),
    ("Android", "Android"),
    ("iPhone", "iOS"),
    ("iPad", "iPadOS"),
    ("Linux", "Linux"),
)


def client_ip(request: Request) -> str | None:
    """The caller's IP, honouring ``X-Forwarded-For`` only behind a trusted proxy."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else None


def user_agent(request: Request) -> str | None:
    """The raw User-Agent header, truncated to the stored column width."""
    ua = request.headers.get("user-agent")
    return ua[:_UA_MAX_LEN] if ua else None


def summarize_user_agent(ua: str | None) -> str:
    """A short, human-readable device label, e.g. ``"Chrome on Windows"``."""
    if not ua:
        return "Unknown device"
    browser = next((label for token, label in _BROWSERS if token in ua), None)
    os_name = next((label for token, label in _OSES if token in ua), None)
    if browser and os_name:
        return f"{browser} on {os_name}"
    return browser or os_name or "Unknown device"
