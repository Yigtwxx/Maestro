"""Deletion request/cancel confirmation emails."""

from __future__ import annotations

EMAIL = "leaver@example.com"
PASSWORD = "password123"


async def _register_and_login(client):
    await client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_request_deletion_sends_confirmation_email(client, sent_emails) -> None:
    headers = await _register_and_login(client)
    sent_emails.clear()  # drop the registration verification email

    resp = await client.request(
        "DELETE", "/api/v1/users/me", json={"password": PASSWORD}, headers=headers
    )
    assert resp.status_code == 200
    assert len(sent_emails) == 1
    assert "deletion" in sent_emails[0].subject.lower()
    # The purge date from the response must appear in the email body.
    assert resp.json()["purge_after"][:10] in sent_emails[0].text


async def test_request_deletion_repeat_does_not_resend_email(
    client, sent_emails
) -> None:
    headers = await _register_and_login(client)
    sent_emails.clear()
    for _ in range(2):
        await client.request(
            "DELETE",
            "/api/v1/users/me",
            json={"password": PASSWORD},
            headers=headers,
        )
    assert len(sent_emails) == 1, "idempotent re-request must not spam"


async def test_cancel_deletion_sends_restored_email(client, sent_emails) -> None:
    headers = await _register_and_login(client)
    await client.request(
        "DELETE", "/api/v1/users/me", json={"password": PASSWORD}, headers=headers
    )
    sent_emails.clear()

    resp = await client.post("/api/v1/users/me/deletion/cancel", headers=headers)
    assert resp.status_code == 200
    assert len(sent_emails) == 1
    assert "restored" in sent_emails[0].subject.lower()


async def test_cancel_deletion_when_not_locked_sends_nothing(
    client, sent_emails
) -> None:
    headers = await _register_and_login(client)
    sent_emails.clear()
    await client.post("/api/v1/users/me/deletion/cancel", headers=headers)
    assert sent_emails == [], "idempotent cancel on an unlocked account is silent"
