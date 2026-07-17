"""Register-time verification email, verify/resend endpoints, rotation."""

from __future__ import annotations

import re


def _extract_token(message) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", message.text)
    assert match is not None, "email should contain an action link"
    return match.group(1)


async def _register_and_login(
    client, email="verify@example.com", password="password123"
):
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_register_sends_verification_email_with_link(client, sent_emails) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
    assert resp.json()["email_verified"] is False
    assert len(sent_emails) == 1
    assert sent_emails[0].to == "new@example.com"
    assert "/verify-email?token=" in sent_emails[0].text


async def test_register_email_provider_failure_still_returns_201(
    client, monkeypatch
) -> None:
    from app.services import email_service

    class ExplodingProvider:
        name = "exploding"

        async def send(self, message) -> None:  # noqa: ANN001
            raise RuntimeError("provider down")

    monkeypatch.setattr(
        email_service, "get_email_provider", lambda: ExplodingProvider()
    )
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "unlucky@example.com", "password": "password123"},
    )
    assert resp.status_code == 201, "email outage must not block registration"


async def test_verify_email_valid_token_marks_user_verified(
    client, sent_emails
) -> None:
    headers = await _register_and_login(client)
    token = _extract_token(sent_emails[0])

    resp = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 200

    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.json()["email_verified"] is True


async def test_verify_email_invalid_token_returns_400(client) -> None:
    resp = await client.post(
        "/api/v1/auth/verify-email", json={"token": "not-a-real-token"}
    )
    assert resp.status_code == 400


async def test_verify_email_token_is_single_use(client, sent_emails) -> None:
    await _register_and_login(client)
    token = _extract_token(sent_emails[0])
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": token})
    ).status_code == 200
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": token})
    ).status_code == 400


async def test_resend_verification_rotates_the_token(client, sent_emails) -> None:
    headers = await _register_and_login(client)
    old_token = _extract_token(sent_emails[0])

    resp = await client.post("/api/v1/auth/resend-verification", headers=headers)
    assert resp.status_code == 202
    assert len(sent_emails) == 2
    new_token = _extract_token(sent_emails[1])

    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": old_token})
    ).status_code == 400, "old link must die on resend"
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": new_token})
    ).status_code == 200


async def test_resend_verification_when_already_verified_sends_nothing(
    client, sent_emails
) -> None:
    headers = await _register_and_login(client)
    token = _extract_token(sent_emails[0])
    await client.post("/api/v1/auth/verify-email", json={"token": token})

    resp = await client.post("/api/v1/auth/resend-verification", headers=headers)
    assert resp.status_code == 202, "response must not leak verification state"
    assert len(sent_emails) == 1, "no second email for a verified account"


async def test_resend_verification_requires_auth(client) -> None:
    resp = await client.post("/api/v1/auth/resend-verification")
    assert resp.status_code in (401, 403)
