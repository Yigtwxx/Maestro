"""Soft verification gate on task start and API-key creation."""

from __future__ import annotations

import re

GATE_DETAIL = "Verify your email address to use this feature."


def _extract_token(message) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", message.text)
    assert match is not None
    return match.group(1)


async def _register_and_login(client, email="gate@example.com"):
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _api_key_payload() -> dict:
    return {"provider": "openai", "label": "test", "key": "sk-test-123"}


async def test_gate_on_unverified_api_key_create_returns_403(
    client, email_gate, sent_emails
) -> None:
    headers = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/api-keys", json=_api_key_payload(), headers=headers
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == GATE_DETAIL


async def test_gate_on_unverified_task_start_returns_403(
    client, email_gate, sent_emails
) -> None:
    headers = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/tasks",
        json={"prompt": "hello", "provider": "ollama", "reviewer_enabled": False},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == GATE_DETAIL


async def test_gate_on_verified_user_passes_the_gate(
    client, email_gate, sent_emails
) -> None:
    headers = await _register_and_login(client)
    token = _extract_token(sent_emails[0])
    await client.post("/api/v1/auth/verify-email", json={"token": token})

    resp = await client.post(
        "/api/v1/api-keys", json=_api_key_payload(), headers=headers
    )
    assert resp.status_code == 201, "a verified account must pass the gate"


async def test_gate_off_unverified_user_is_not_blocked(client) -> None:
    # The autouse fixture disables the gate (EMAIL_VERIFICATION_REQUIRED=false).
    headers = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/api-keys", json=_api_key_payload(), headers=headers
    )
    assert resp.status_code == 201
