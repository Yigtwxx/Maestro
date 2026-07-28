"""``GET /agents/tools``: the catalog the agent wizard renders.

The endpoint used to return bare ``{id, label}`` pairs, which left the UI unable
to tell a tool with a real runtime from one the model merely performs natively,
or a tool the user can use today from one waiting on a BYOK key. These tests pin
the annotations that distinguish them — and that no key material is decrypted or
returned to build them.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.constants import (
    CODE_EXECUTION_ACTION,
    COMMUNITY_READ_ACTION,
    DECLARATIVE_TOOL_IDS,
    EXECUTABLE_TOOL_IDS,
    REPO_INTEL_ACTION,
    SOCIAL_SEARCH_ACTION,
    TOOL_IDS,
    LLMProvider,
)

_EMAIL = "catalog@user.com"
_PASSWORD = "supersecret"
_SECRET = "sk-super-secret-github-token-value"


async def _register_and_login(client, email: str = _EMAIL) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Cat"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _catalog(client, headers: dict[str, str]) -> dict[str, dict]:  # noqa: ANN001
    resp = await client.get("/api/v1/agents/tools", headers=headers)
    assert resp.status_code == 200, resp.text
    return {entry["id"]: entry for entry in resp.json()}


async def test_catalog_covers_every_declarable_tool(client) -> None:  # noqa: ANN001
    """Every id in TOOL_IDS appears exactly once, with prose attached."""
    headers = await _register_and_login(client)
    entries = await _catalog(client, headers)
    assert set(entries) == TOOL_IDS, set(entries) ^ TOOL_IDS
    missing_prose = [k for k, v in entries.items() if not v["description"]]
    assert not missing_prose, f"tools with no description: {missing_prose}"


async def test_kind_splits_executable_from_declarative(client) -> None:  # noqa: ANN001
    """``kind`` mirrors EXECUTABLE_TOOL_IDS — the split the UI must show."""
    headers = await _register_and_login(client)
    entries = await _catalog(client, headers)
    executable = {k for k, v in entries.items() if v["kind"] == "executable"}
    declarative = {k for k, v in entries.items() if v["kind"] == "declarative"}
    assert executable == EXECUTABLE_TOOL_IDS, executable ^ EXECUTABLE_TOOL_IDS
    assert declarative == DECLARATIVE_TOOL_IDS, declarative ^ DECLARATIVE_TOOL_IDS


async def test_repo_intel_is_keyless_and_usable_without_a_key(client) -> None:  # noqa: ANN001
    """GitHub serves anonymous reads, so repo_intel works with no credential."""
    headers = await _register_and_login(client)
    entries = await _catalog(client, headers)
    assert entries[REPO_INTEL_ACTION]["keyless"] is True
    assert entries[REPO_INTEL_ACTION]["providers"] == [LLMProvider.GITHUB.value]


async def test_connected_is_false_until_the_user_adds_the_key(client) -> None:  # noqa: ANN001
    """social_search needs an X key; the catalog says so before one exists."""
    headers = await _register_and_login(client)
    entries = await _catalog(client, headers)
    assert entries[SOCIAL_SEARCH_ACTION]["connected"] is False, entries[
        SOCIAL_SEARCH_ACTION
    ]

    resp = await client.post(
        "/api/v1/api-keys",
        json={"provider": LLMProvider.X.value, "key": _SECRET, "label": "X"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text

    entries = await _catalog(client, headers)
    assert entries[SOCIAL_SEARCH_ACTION]["connected"] is True, entries[
        SOCIAL_SEARCH_ACTION
    ]


async def test_community_read_lists_all_three_platforms(client) -> None:  # noqa: ANN001
    """No single provider: any one connected platform makes the tool usable."""
    headers = await _register_and_login(client)
    entries = await _catalog(client, headers)
    entry = entries[COMMUNITY_READ_ACTION]
    assert entry["providers"] == ["discord", "slack", "telegram"], entry["providers"]
    assert entry["connected"] is False

    resp = await client.post(
        "/api/v1/api-keys",
        json={"provider": LLMProvider.SLACK.value, "key": _SECRET, "label": "S"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text

    entries = await _catalog(client, headers)
    assert entries[COMMUNITY_READ_ACTION]["connected"] is True


async def test_keyless_tools_never_report_a_missing_key(client) -> None:  # noqa: ANN001
    """A tool with nothing to connect reports connected, not 'missing a key'."""
    headers = await _register_and_login(client)
    entries = await _catalog(client, headers)
    for tool_id, entry in entries.items():
        if not entry["providers"]:
            assert entry["connected"] is True, f"{tool_id} claims a missing key"


async def test_available_follows_the_operator_switch(client, monkeypatch) -> None:  # noqa: ANN001
    """``available`` is the operator's lever, separate from the user's key."""
    headers = await _register_and_login(client)
    entries = await _catalog(client, headers)
    # code_execution defaults off in this deployment (CLAUDE.md §11).
    assert (
        entries[CODE_EXECUTION_ACTION]["available"] is settings.code_execution_enabled
    )

    monkeypatch.setattr(settings, "social_search_enabled", False)
    entries = await _catalog(client, headers)
    assert entries[SOCIAL_SEARCH_ACTION]["available"] is False


async def test_catalog_body_carries_no_key_material(client) -> None:  # noqa: ANN001
    """The response is built from the provider column; no secret can ride along."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/api-keys",
        json={"provider": LLMProvider.X.value, "key": _SECRET, "label": "X"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text

    raw = (await client.get("/api/v1/agents/tools", headers=headers)).text
    assert _SECRET not in raw
    assert "encrypted" not in raw.lower()


async def test_connected_providers_never_decrypts(client, monkeypatch) -> None:  # noqa: ANN001
    """Presence is answered from the provider column alone (CLAUDE.md §9.1).

    Decryption is sabotaged: if the catalog path touched a secret it would raise
    here instead of answering.
    """
    from app.services import service_key_service

    headers = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/api-keys",
        json={"provider": LLMProvider.X.value, "key": _SECRET, "label": "X"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text

    def _explode(_: str) -> str:
        raise AssertionError("connected_providers must not decrypt")

    monkeypatch.setattr(service_key_service, "decrypt_secret", _explode)
    entries = await _catalog(client, headers)
    assert entries[SOCIAL_SEARCH_ACTION]["connected"] is True


async def test_catalog_is_scoped_to_the_caller(client) -> None:  # noqa: ANN001
    """One user's key never marks another user's tool connected."""
    owner = await _register_and_login(client, "owner@user.com")
    resp = await client.post(
        "/api/v1/api-keys",
        json={"provider": LLMProvider.X.value, "key": _SECRET, "label": "X"},
        headers=owner,
    )
    assert resp.status_code in (200, 201), resp.text

    other = await _register_and_login(client, "other@user.com")
    entries = await _catalog(client, other)
    assert entries[SOCIAL_SEARCH_ACTION]["connected"] is False


async def test_catalog_requires_authentication(client) -> None:  # noqa: ANN001
    """The catalog is per-user, so it is not a public endpoint."""
    resp = await client.get("/api/v1/agents/tools")
    assert resp.status_code == 401, resp.text
