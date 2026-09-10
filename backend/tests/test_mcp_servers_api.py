"""MCP server CRUD over HTTP: the switch, ownership, and the secret boundary.

The load-bearing assertions are the negative ones, and they check the *raw
response body* rather than the parsed model — a field that slipped past
``McpServerPublic`` would still be caught.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.constants import MCP_SERVERS_PER_AGENT_MAX
from app.schemas.mcp_server import McpDiscoverResult
from app.services import mcp_service

_PASSWORD = "supersecret"
_SECRET = "sk-live-super-secret-value-9f3a"

_BASE = {
    "slug": "acme",
    "name": "Acme Tools",
    "description": "Acme's internal MCP server.",
    "url": "https://mcp.example.com/mcp",
}


@pytest.fixture(autouse=True)
def _no_ssrf_guard(monkeypatch):
    """These tests are about CRUD, not the guard.

    ``mcp.example.com`` does not resolve, so leaving it on would 422 every
    registration for the wrong reason. ``test_mcp_ssrf.py`` owns that behaviour.
    """
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)


@pytest.fixture
def _mcp_on(monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", True)


def _payload(**overrides) -> dict:
    return {**_BASE, **overrides}


async def _register_and_login(client, email: str) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Owner"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# --- the operator switch ----------------------------------------------------


async def test_registration_is_refused_while_the_feature_is_off(client, mcp_db):
    """Registering a server that could never be called is a worse experience
    than being told the deployment does not allow it."""
    auth = await _register_and_login(client, "mcp-off@example.com")
    resp = await client.post("/api/v1/mcp-servers", json=_payload(), headers=auth)
    assert resp.status_code == 403, resp.text
    assert "disabled" in resp.json()["detail"]


async def test_listing_still_works_while_the_feature_is_off(client, mcp_db):
    """Reads stay open so a user can see and remove what they registered."""
    auth = await _register_and_login(client, "mcp-off-read@example.com")
    assert (await client.get("/api/v1/mcp-servers", headers=auth)).status_code == 200


# --- CRUD and the secret boundary -------------------------------------------


async def test_create_never_returns_the_secret(client, mcp_db, _mcp_on):
    auth = await _register_and_login(client, "mcp-crud@example.com")
    resp = await client.post(
        "/api/v1/mcp-servers",
        json=_payload(auth_mode="bearer", secret=_SECRET),
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert _SECRET not in resp.text
    assert "encrypted_secret" not in resp.text
    assert resp.json()["secret_hint"].endswith("9f3a")


async def test_reads_never_carry_the_secret(client, mcp_db, _mcp_on):
    auth = await _register_and_login(client, "mcp-read@example.com")
    created = await client.post(
        "/api/v1/mcp-servers",
        json=_payload(auth_mode="bearer", secret=_SECRET),
        headers=auth,
    )
    server_id = created.json()["id"]
    for resp in (
        await client.get("/api/v1/mcp-servers", headers=auth),
        await client.get(f"/api/v1/mcp-servers/{server_id}", headers=auth),
    ):
        assert _SECRET not in resp.text
        assert "encrypted_secret" not in resp.text
        assert "user_id" not in resp.text


async def test_patch_without_a_secret_preserves_the_stored_one(client, mcp_db, _mcp_on):
    auth = await _register_and_login(client, "mcp-patch@example.com")
    created = await client.post(
        "/api/v1/mcp-servers",
        json=_payload(auth_mode="bearer", secret=_SECRET),
        headers=auth,
    )
    before = mcp_db.docs[0]["encrypted_secret"]
    resp = await client.patch(
        f"/api/v1/mcp-servers/{created.json()['id']}",
        json={"name": "Renamed"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert mcp_db.docs[0]["encrypted_secret"] == before


async def test_patch_with_a_secret_rotates_it(client, mcp_db, _mcp_on):
    auth = await _register_and_login(client, "mcp-rotate@example.com")
    created = await client.post(
        "/api/v1/mcp-servers",
        json=_payload(auth_mode="bearer", secret=_SECRET),
        headers=auth,
    )
    before = mcp_db.docs[0]["encrypted_secret"]
    await client.patch(
        f"/api/v1/mcp-servers/{created.json()['id']}",
        json={"secret": "sk-live-rotated-0001"},
        headers=auth,
    )
    assert mcp_db.docs[0]["encrypted_secret"] != before


async def test_another_users_server_is_a_404_not_a_403(client, mcp_db, _mcp_on):
    owner = await _register_and_login(client, "mcp-a@example.com")
    created = await client.post("/api/v1/mcp-servers", json=_payload(), headers=owner)
    server_id = created.json()["id"]

    stranger = await _register_and_login(client, "mcp-b@example.com")
    assert (
        await client.get(f"/api/v1/mcp-servers/{server_id}", headers=stranger)
    ).status_code == 404
    assert (await client.get("/api/v1/mcp-servers", headers=stranger)).json() == []


async def test_the_routes_require_authentication(client, mcp_db):
    assert (await client.get("/api/v1/mcp-servers")).status_code == 401
    assert (
        await client.post("/api/v1/mcp-servers", json=_payload())
    ).status_code == 401


async def test_an_unknown_field_is_refused_rather_than_ignored(client, mcp_db, _mcp_on):
    auth = await _register_and_login(client, "mcp-strict@example.com")
    resp = await client.post(
        "/api/v1/mcp-servers", json=_payload(plugin_id="smuggled"), headers=auth
    )
    assert resp.status_code == 422, resp.text


async def test_delete_removes_it_and_is_idempotently_404(client, mcp_db, _mcp_on):
    auth = await _register_and_login(client, "mcp-delete@example.com")
    created = await client.post("/api/v1/mcp-servers", json=_payload(), headers=auth)
    server_id = created.json()["id"]
    assert (
        await client.delete(f"/api/v1/mcp-servers/{server_id}", headers=auth)
    ).status_code == 204
    assert (
        await client.delete(f"/api/v1/mcp-servers/{server_id}", headers=auth)
    ).status_code == 404


# --- discovery --------------------------------------------------------------


async def test_discovery_reports_a_failure_in_the_body(
    client, mcp_db, _mcp_on, monkeypatch
):
    """Pointing at a server that is down is an ordinary thing to do."""
    auth = await _register_and_login(client, "mcp-discover@example.com")
    created = await client.post("/api/v1/mcp-servers", json=_payload(), headers=auth)

    async def fake_discover(_user_id, _server_id):
        return McpDiscoverResult(ok=False, error="the server could not be reached")

    monkeypatch.setattr(mcp_service, "discover", fake_discover)
    resp = await client.post(
        f"/api/v1/mcp-servers/{created.json()['id']}/discover", headers=auth
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


async def test_discovery_on_a_foreign_server_is_a_404(client, mcp_db, _mcp_on):
    owner = await _register_and_login(client, "mcp-d-a@example.com")
    created = await client.post("/api/v1/mcp-servers", json=_payload(), headers=owner)
    stranger = await _register_and_login(client, "mcp-d-b@example.com")
    resp = await client.post(
        f"/api/v1/mcp-servers/{created.json()['id']}/discover", headers=stranger
    )
    assert resp.status_code == 404


# --- attachment to an agent -------------------------------------------------


async def test_an_agent_can_attach_its_owners_servers(
    client, mcp_db, agents_db, _mcp_on
):
    auth = await _register_and_login(client, "mcp-attach@example.com")
    created = await client.post("/api/v1/mcp-servers", json=_payload(), headers=auth)

    agent = await client.post(
        "/api/v1/agents",
        json={
            "name": "Analyst",
            "domain": "general",
            "system_prompt": "p",
            "mcp_server_ids": [created.json()["id"]],
        },
        headers=auth,
    )
    assert agent.status_code == 201, agent.text
    assert agent.json()["mcp_server_ids"] == [created.json()["id"]]


async def test_attaching_someone_elses_server_is_refused(
    client, mcp_db, agents_db, _mcp_on
):
    owner = await _register_and_login(client, "mcp-att-a@example.com")
    created = await client.post("/api/v1/mcp-servers", json=_payload(), headers=owner)

    stranger = await _register_and_login(client, "mcp-att-b@example.com")
    resp = await client.post(
        "/api/v1/agents",
        json={
            "name": "Thief",
            "domain": "general",
            "system_prompt": "p",
            "mcp_server_ids": [created.json()["id"]],
        },
        headers=stranger,
    )
    assert resp.status_code == 400, resp.text
    assert "Unknown MCP servers" in resp.json()["detail"]


async def test_more_servers_than_the_per_agent_cap_is_a_422(
    client, mcp_db, agents_db, _mcp_on
):
    auth = await _register_and_login(client, "mcp-cap@example.com")
    ids = []
    for index in range(MCP_SERVERS_PER_AGENT_MAX + 1):
        resp = await client.post(
            "/api/v1/mcp-servers", json=_payload(slug=f"srv_{index}"), headers=auth
        )
        ids.append(resp.json()["id"])

    resp = await client.post(
        "/api/v1/agents",
        json={
            "name": "Greedy",
            "domain": "general",
            "system_prompt": "p",
            "mcp_server_ids": ids,
        },
        headers=auth,
    )
    assert resp.status_code == 422, resp.text


async def test_attaching_servers_offering_too_many_tools_is_refused(
    client, mcp_db, agents_db, _mcp_on
):
    """The server count does not bound the *tool* count, and the tool count is
    what spends the member's prompt budget."""
    auth = await _register_and_login(client, "mcp-tools-cap@example.com")
    created = await client.post("/api/v1/mcp-servers", json=_payload(), headers=auth)
    mcp_db.docs[0]["tools"] = [
        {
            "action": f"mcp__acme__t{i}",
            "remote_name": f"t{i}",
            "enabled": True,
        }
        for i in range(30)
    ]

    resp = await client.post(
        "/api/v1/agents",
        json={
            "name": "Greedy",
            "domain": "general",
            "system_prompt": "p",
            "mcp_server_ids": [created.json()["id"]],
        },
        headers=auth,
    )
    assert resp.status_code == 400, resp.text
    assert "tools together" in resp.json()["detail"]
