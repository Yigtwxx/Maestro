"""Forgot/reset password flow: enumeration resistance, session revocation."""

from __future__ import annotations

import re

EMAIL = "reset@example.com"
OLD_PASSWORD = "password123"
NEW_PASSWORD = "newpassword456"


def _extract_token(message) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", message.text)
    assert match is not None, "email should contain an action link"
    return match.group(1)


async def _register(client) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": OLD_PASSWORD}
    )


async def _request_reset_token(client, sent_emails) -> str:
    sent_emails.clear()  # drop the registration verification email
    resp = await client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    assert resp.status_code == 202
    return _extract_token(sent_emails[0])


async def test_forgot_password_unknown_email_returns_202_and_sends_nothing(
    client, sent_emails
) -> None:
    resp = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "ghost@example.com"}
    )
    assert resp.status_code == 202, "response must not reveal account existence"
    assert sent_emails == []


async def test_forgot_password_known_email_sends_reset_link(
    client, sent_emails
) -> None:
    await _register(client)
    token = await _request_reset_token(client, sent_emails)
    assert token
    assert "/reset-password?token=" in sent_emails[0].text


async def test_reset_password_valid_token_changes_the_password(
    client, sent_emails
) -> None:
    await _register(client)
    token = await _request_reset_token(client, sent_emails)

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 200

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD}
    )
    assert old_login.status_code == 401, "old password must stop working"
    new_login = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200


async def test_reset_password_revokes_existing_sessions(client, sent_emails) -> None:
    await _register(client)
    login = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD}
    )
    stolen_refresh = login.json()["refresh_token"]

    token = await _request_reset_token(client, sent_emails)
    await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": stolen_refresh}
    )
    assert resp.status_code == 401, "pre-reset sessions must be revoked"


async def test_reset_password_token_is_single_use(client, sent_emails) -> None:
    await _register(client)
    token = await _request_reset_token(client, sent_emails)
    await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    replay = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "anotherpass789"},
    )
    assert replay.status_code == 400


async def test_reset_password_invalid_token_returns_400(client) -> None:
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "bogus", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 400


async def test_reset_password_short_password_returns_422(client, sent_emails) -> None:
    await _register(client)
    token = await _request_reset_token(client, sent_emails)
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "short"},
    )
    assert resp.status_code == 422
