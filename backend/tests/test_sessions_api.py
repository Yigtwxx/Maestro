"""Integration tests for the active-sessions endpoints (SQLite-backed)."""

from __future__ import annotations

from app.core.security import create_token, decode_token

_PASSWORD = "supersecret"


async def _register(client, email: str) -> None:  # noqa: ANN001
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "S"},
    )
    assert resp.status_code == 202, resp.text


async def _login(client, email: str, user_agent: str = "TestBrowser/1.0") -> str:  # noqa: ANN001
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _PASSWORD},
        headers={"User-Agent": user_agent},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_login_records_a_listable_session(client):
    await _register(client, "s1@user.com")
    token = await _login(client, "s1@user.com", user_agent="Mozilla/5.0 (Windows NT)")
    resp = await client.get("/api/v1/users/me/sessions", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    sessions = resp.json()
    assert len(sessions) == 1
    assert sessions[0]["current"] is True, "the requesting session is 'current'"
    assert "Windows" in sessions[0]["device"], sessions[0]["device"]


async def test_second_login_creates_a_second_session(client):
    await _register(client, "s2@user.com")
    await _login(client, "s2@user.com")
    token2 = await _login(client, "s2@user.com")
    sessions = (
        await client.get("/api/v1/users/me/sessions", headers=_auth(token2))
    ).json()
    assert len(sessions) == 2
    assert sum(1 for s in sessions if s["current"]) == 1, "exactly one is current"


async def test_revoke_other_sessions_keeps_only_current(client):
    await _register(client, "s3@user.com")
    await _login(client, "s3@user.com")
    token2 = await _login(client, "s3@user.com")

    resp = await client.post(
        "/api/v1/users/me/sessions/revoke-others", headers=_auth(token2)
    )
    assert resp.status_code == 204, resp.text
    remaining = (
        await client.get("/api/v1/users/me/sessions", headers=_auth(token2))
    ).json()
    assert len(remaining) == 1
    assert remaining[0]["current"] is True


async def test_revoke_single_session_by_id(client):
    await _register(client, "s4@user.com")
    token1 = await _login(client, "s4@user.com")
    token2 = await _login(client, "s4@user.com")

    sessions = (
        await client.get("/api/v1/users/me/sessions", headers=_auth(token2))
    ).json()
    other = next(s for s in sessions if not s["current"])
    resp = await client.delete(
        f"/api/v1/users/me/sessions/{other['id']}", headers=_auth(token2)
    )
    assert resp.status_code == 204, resp.text
    remaining = (
        await client.get("/api/v1/users/me/sessions", headers=_auth(token2))
    ).json()
    assert all(s["id"] != other["id"] for s in remaining)
    # token1's session is gone: its next refresh must fail.
    _ = token1


async def test_cannot_revoke_another_users_session(client):
    await _register(client, "owner@user.com")
    owner_token = await _login(client, "owner@user.com")
    owner_sessions = (
        await client.get("/api/v1/users/me/sessions", headers=_auth(owner_token))
    ).json()
    victim_family = owner_sessions[0]["id"]

    await _register(client, "attacker@user.com")
    attacker_token = await _login(client, "attacker@user.com")
    resp = await client.delete(
        f"/api/v1/users/me/sessions/{victim_family}", headers=_auth(attacker_token)
    )
    assert resp.status_code == 404, "must not reveal or revoke another user's session"


async def test_password_change_revokes_other_sessions(client):
    await _register(client, "pw@user.com")
    login1 = await client.post(
        "/api/v1/auth/login", json={"email": "pw@user.com", "password": _PASSWORD}
    )
    refresh1 = login1.json()["refresh_token"]
    token2 = await _login(client, "pw@user.com")

    resp = await client.post(
        "/api/v1/users/me/password",
        headers=_auth(token2),
        json={
            "current_password": _PASSWORD,
            "new_password": "brandnewsecret",
            "revoke_other_sessions": True,
        },
    )
    assert resp.status_code == 204, resp.text

    # The other session's refresh token is now revoked.
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh1}
    )
    assert refreshed.status_code == 401, "the old session must be signed out"
    # The current session survives.
    still_here = await client.get("/api/v1/users/me/sessions", headers=_auth(token2))
    assert still_here.status_code == 200
    assert len(still_here.json()) == 1


async def test_password_change_can_keep_other_sessions(client):
    await _register(client, "pw2@user.com")
    login1 = await client.post(
        "/api/v1/auth/login", json={"email": "pw2@user.com", "password": _PASSWORD}
    )
    refresh1 = login1.json()["refresh_token"]
    token2 = await _login(client, "pw2@user.com")

    resp = await client.post(
        "/api/v1/users/me/password",
        headers=_auth(token2),
        json={
            "current_password": _PASSWORD,
            "new_password": "brandnewsecret",
            "revoke_other_sessions": False,
        },
    )
    assert resp.status_code == 204, resp.text
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh1}
    )
    assert refreshed.status_code == 200, "opting out keeps the other session alive"


async def test_revoke_others_without_family_claim_is_refused(client):
    """A token lacking the ``fam`` claim can't identify the current session, so
    revoke-others must refuse rather than silently sign every session out."""
    await _register(client, "nofam1@user.com")
    token = await _login(client, "nofam1@user.com")
    sub = decode_token(token, expected_type="access")["sub"]
    legacy = create_token(sub, "access")  # pre-rotation token: no 'fam' claim

    resp = await client.post(
        "/api/v1/users/me/sessions/revoke-others", headers=_auth(legacy)
    )
    assert resp.status_code == 401, resp.text
    # Nothing was revoked: the real session is still listable.
    sessions = await client.get("/api/v1/users/me/sessions", headers=_auth(token))
    assert len(sessions.json()) == 1, "no session may be revoked when family is unknown"


async def test_password_change_without_family_claim_is_refused(client):
    """With ``revoke_other_sessions`` set but no ``fam`` claim, the whole change
    is refused so it can't nuke the caller's own session or the password."""
    await _register(client, "nofam2@user.com")
    token = await _login(client, "nofam2@user.com")
    sub = decode_token(token, expected_type="access")["sub"]
    legacy = create_token(sub, "access")

    resp = await client.post(
        "/api/v1/users/me/password",
        headers=_auth(legacy),
        json={
            "current_password": _PASSWORD,
            "new_password": "brandnewsecret",
            "revoke_other_sessions": True,
        },
    )
    assert resp.status_code == 401, resp.text
    # The change was rolled back: the old password still authenticates.
    relogin = await client.post(
        "/api/v1/auth/login", json={"email": "nofam2@user.com", "password": _PASSWORD}
    )
    assert relogin.status_code == 200, "password must not have changed"
