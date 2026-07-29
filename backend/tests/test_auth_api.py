"""Integration tests for auth + API-key endpoints (SQLite-backed)."""

from __future__ import annotations


async def _register_and_login(client) -> str:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": "a@b.com", "password": "supersecret", "display_name": "A"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "a@b.com", "password": "supersecret"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def test_register_login_flow(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@user.com", "password": "supersecret"},
    )
    assert resp.status_code == 202
    # The body describes the next step, never the account: it has to read the
    # same for an address that was already taken.
    assert resp.json()["detail"]
    assert "email" not in resp.json()


async def test_duplicate_email_is_indistinguishable_from_a_new_one(client, sent_emails):
    """A taken address must not be detectable from the response."""
    payload = {"email": "dup@user.com", "password": "supersecret"}
    first = await client.post("/api/v1/auth/register", json=payload)
    sent_emails.clear()
    second = await client.post("/api/v1/auth/register", json=payload)

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json(), "responses must be byte-identical"
    assert len(sent_emails) == 1, "the real owner is told instead"
    assert sent_emails[0].to == "dup@user.com"
    assert "token=" not in sent_emails[0].text, "the notice carries no action token"


async def test_login_wrong_password(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "x@y.com", "password": "supersecret"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "x@y.com", "password": "wrongpass"}
    )
    assert resp.status_code == 401


async def test_api_key_never_returns_secret(client):
    token = await _register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}
    create = await client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"provider": "openai", "label": "My key", "key": "sk-secret-value-1234"},
    )
    assert create.status_code == 201
    body = create.json()
    assert "sk-secret-value-1234" not in str(body)
    assert body["key_hint"] == "****1234"

    listed = await client.get("/api/v1/api-keys", headers=headers)
    assert listed.status_code == 200
    assert "encrypted_key" not in str(listed.json())


async def test_protected_route_requires_auth(client):
    # No bearer token → unauthenticated.
    assert (await client.get("/api/v1/api-keys")).status_code == 401
