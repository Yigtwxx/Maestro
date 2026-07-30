"""The refresh-token cookie: one place that owns its attributes.

The refresh token is the durable half of a session, so it is carried in an
httpOnly cookie rather than a response body: JavaScript on the origin cannot
read it, and an XSS foothold is therefore limited to spending the current
30-minute access token rather than walking off with a 7-day session
(CLAUDE.md §8, "Token storage").

Every attribute lives here rather than at the three call sites, because a
``delete_cookie`` whose path/domain/secure/samesite do not match the original
``set_cookie`` is silently ignored by the browser -- the sign-out would look
successful and leave the cookie in place. The attribute test in
``tests/test_auth_cookie.py`` reads these same constants.
"""

from __future__ import annotations

from fastapi import Response

from app.core.config import settings

# Not `__Host-maestro_refresh`: that prefix mandates `Path=/`, which would send
# the cookie on every API call, every WebSocket handshake and every Next
# document request. The path scoping below is worth more than the prefix's
# protection against a hostile sibling subdomain shadowing the cookie, which
# `refresh_cookie_domain` defaulting to host-only already rules out.
REFRESH_COOKIE_NAME = "maestro_refresh"

# Only /api/v1/auth/refresh and /api/v1/auth/logout ever read it.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _cookie_domain() -> str | None:
    """The Domain attribute, or None for a host-only cookie (the default)."""
    return settings.refresh_cookie_domain or None


def set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the rotated refresh token to ``response`` as an httpOnly cookie.

    ``max_age`` is derived from the JWT's own lifetime rather than configured
    separately, so the cookie can never outlive the token it carries (or be
    evicted while the token is still valid, which would sign the user out
    early with no server-side reason).
    """
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        domain=_cookie_domain(),
        secure=settings.refresh_cookie_is_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def clear_refresh_cookie(response: Response) -> None:
    """Expire the refresh cookie. Must mirror ``set_refresh_cookie``'s scope."""
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        domain=_cookie_domain(),
        secure=settings.refresh_cookie_is_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def clearing_cookie_header() -> dict[str, str]:
    """The expiring ``Set-Cookie`` as a header dict, for attaching to a 401.

    ``HTTPException`` takes headers but not a ``Response``, and a failed
    refresh must still clear the cookie: a burned session family otherwise
    leaves a dead credential in the browser that 401s on every attempt for the
    remaining seven days.
    """
    carrier = Response()
    clear_refresh_cookie(carrier)
    return {"set-cookie": carrier.headers["set-cookie"]}
