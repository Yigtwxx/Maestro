"""Integration tests for refresh-token rotation + reuse-detection (SQLite)."""

from __future__ import annotations

import uuid

from app.core.security import create_token

_SUBJECT = "11111111-1111-1111-1111-111111111111"


async def _register(client, email: str = "u@ex.com") -> None:  # noqa: ANN001
    resp = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "supersecret"}
    )
    assert resp.status_code == 201, resp.text


async def _login(client, email: str = "u@ex.com") -> dict:  # noqa: ANN001
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _refresh(client, refresh_token: str):  # noqa: ANN001, ANN201
    return await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )


async def test_refresh_rotates_and_invalidates_old(client):
    await _register(client)
    old_refresh = (await _login(client))["refresh_token"]

    rotated = await _refresh(client, old_refresh)
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != old_refresh, "Token was not rotated"

    # The old token is single-use: replaying it is now rejected.
    assert (await _refresh(client, old_refresh)).status_code == 401


async def test_reuse_detection_revokes_family(client):
    await _register(client)
    old_refresh = (await _login(client))["refresh_token"]

    new_refresh = (await _refresh(client, old_refresh)).json()["refresh_token"]

    # Replaying the already-rotated token is treated as theft.
    assert (await _refresh(client, old_refresh)).status_code == 401

    # The whole family is burned: even the freshly-issued token is now dead.
    assert (await _refresh(client, new_refresh)).status_code == 401


async def test_logout_revokes_session(client):
    await _register(client)
    refresh_token = (await _login(client))["refresh_token"]

    out = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh_token}
    )
    assert out.status_code == 204

    assert (await _refresh(client, refresh_token)).status_code == 401


async def test_logout_is_idempotent_on_garbage(client):
    """Logout must never leak token validity — a junk token is a quiet no-op."""
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": "not-a-jwt"})
    assert out.status_code == 204


async def test_independent_sessions_isolated(client):
    await _register(client)
    session_one = await _login(client)
    session_two = await _login(client)

    out = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": session_one["refresh_token"]}
    )
    assert out.status_code == 204

    # Revoking one session leaves the other fully usable.
    assert (await _refresh(client, session_one["refresh_token"])).status_code == 401
    assert (await _refresh(client, session_two["refresh_token"])).status_code == 200


async def test_forged_or_unknown_jti_rejected(client):
    await _register(client)

    # A pre-rotation token (no jti claim) has no server-side record.
    no_jti = create_token(_SUBJECT, "refresh")
    assert (await _refresh(client, no_jti)).status_code == 401

    # A well-formed token whose jti was never issued is equally invalid.
    forged = create_token(
        _SUBJECT,
        "refresh",
        extra_claims={"jti": str(uuid.uuid4()), "fam": str(uuid.uuid4())},
    )
    assert (await _refresh(client, forged)).status_code == 401
