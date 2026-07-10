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
    assert resp.status_code == 201
    assert resp.json()["email"] == "new@user.com"
    assert "hashed_password" not in resp.json()


async def test_duplicate_email_rejected(client):
    payload = {"email": "dup@user.com", "password": "supersecret"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 409


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
