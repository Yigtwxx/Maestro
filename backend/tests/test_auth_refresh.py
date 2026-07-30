"""Integration tests for refresh-token rotation + reuse-detection (SQLite).

Every test drives the refresh token through the httpOnly cookie, because that
is now its only transport (CLAUDE.md §9 rule 14). The value is captured per
response and pinned back with the ``send_refresh_cookie`` fixture rather than
left to the client's jar: ``conftest``'s ``client`` is one ``AsyncClient`` with
one shared jar, so a second login in the same test would silently overwrite the
first, and a replay test is inexpressible once rotation has evicted the old
value.
"""

from __future__ import annotations

import uuid

from app.core.cookies import REFRESH_COOKIE_NAME
from app.core.security import create_token

_SUBJECT = "11111111-1111-1111-1111-111111111111"


async def _register(client, email: str = "u@ex.com") -> None:  # noqa: ANN001
    resp = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "supersecret"}
    )
    assert resp.status_code == 202, resp.text


async def _login(client, email: str = "u@ex.com") -> str:  # noqa: ANN001
    """Log in and return the refresh token the response set as a cookie."""
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret"}
    )
    assert resp.status_code == 200, resp.text
    return resp.cookies[REFRESH_COOKIE_NAME]


async def _refresh(client, send_refresh_cookie, token: str):  # noqa: ANN001, ANN201
    send_refresh_cookie(token)
    return await client.post("/api/v1/auth/refresh")


async def _logout(client, send_refresh_cookie, token: str):  # noqa: ANN001, ANN201
    send_refresh_cookie(token)
    return await client.post("/api/v1/auth/logout")


async def test_refresh_rotates_and_invalidates_old(client, send_refresh_cookie):
    await _register(client)
    old_refresh = await _login(client)

    rotated = await _refresh(client, send_refresh_cookie, old_refresh)
    assert rotated.status_code == 200, rotated.text
    assert rotated.cookies[REFRESH_COOKIE_NAME] != old_refresh, "Token was not rotated"

    # The old token is single-use: replaying it is now rejected.
    assert (await _refresh(client, send_refresh_cookie, old_refresh)).status_code == 401


async def test_reuse_detection_revokes_family(client, send_refresh_cookie):
    await _register(client)
    old_refresh = await _login(client)

    new_refresh = (await _refresh(client, send_refresh_cookie, old_refresh)).cookies[
        REFRESH_COOKIE_NAME
    ]

    # Replaying the already-rotated token is treated as theft.
    assert (await _refresh(client, send_refresh_cookie, old_refresh)).status_code == 401

    # The whole family is burned: even the freshly-issued token is now dead.
    assert (await _refresh(client, send_refresh_cookie, new_refresh)).status_code == 401


async def test_logout_revokes_session(client, send_refresh_cookie):
    await _register(client)
    refresh_token = await _login(client)

    out = await _logout(client, send_refresh_cookie, refresh_token)
    assert out.status_code == 204

    assert (
        await _refresh(client, send_refresh_cookie, refresh_token)
    ).status_code == 401


async def test_logout_is_idempotent_on_garbage(client, send_refresh_cookie):
    """Logout must never leak token validity — a junk token is a quiet no-op."""
    out = await _logout(client, send_refresh_cookie, "not-a-jwt")
    assert out.status_code == 204


async def test_independent_sessions_isolated(client, send_refresh_cookie):
    await _register(client)
    session_one = await _login(client)
    session_two = await _login(client)
    assert session_one != session_two, "Second login reused the first session's token"

    out = await _logout(client, send_refresh_cookie, session_one)
    assert out.status_code == 204

    # Revoking one session leaves the other fully usable.
    assert (await _refresh(client, send_refresh_cookie, session_one)).status_code == 401
    assert (await _refresh(client, send_refresh_cookie, session_two)).status_code == 200


async def test_forged_or_unknown_jti_rejected(client, send_refresh_cookie):
    await _register(client)

    # A pre-rotation token (no jti claim) has no server-side record.
    no_jti = create_token(_SUBJECT, "refresh")
    assert (await _refresh(client, send_refresh_cookie, no_jti)).status_code == 401

    # A well-formed token whose jti was never issued is equally invalid.
    forged = create_token(
        _SUBJECT,
        "refresh",
        extra_claims={"jti": str(uuid.uuid4()), "fam": str(uuid.uuid4())},
    )
    assert (await _refresh(client, send_refresh_cookie, forged)).status_code == 401
