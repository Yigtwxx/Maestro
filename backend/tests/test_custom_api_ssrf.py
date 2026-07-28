"""SSRF containment for user-registered endpoints.

A custom API tool is the only place a *user* chooses the host the backend calls,
so the guard runs twice: once at registration and again on every call. Both are
needed — the record outlives its validation, and the DNS for a hostname the user
owns is theirs to change afterwards.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import connected_common, custom_api_service
from app.utils import url_guard


@pytest.fixture(autouse=True)
def _custom_api_tools_on(monkeypatch):
    """The feature ships off (CUSTOM_API_TOOLS_ENABLED=false, see config.py).

    These tests exercise it, so they opt in explicitly — which also keeps the
    one test that asserts the *disabled* behaviour honest, since it has to turn
    the switch back off itself.
    """
    monkeypatch.setattr(settings, "custom_api_tools_enabled", True)


_PASSWORD = "supersecret"

_BASE = {
    "slug": "probe",
    "name": "Probe",
    "method": "GET",
    "base_url": "https://api.example.com",
    "path_template": "/v1/ping",
    "parameters": [],
}


def _payload(**overrides) -> dict:
    return {**_BASE, **overrides}


async def _register_and_login(client, email: str = "ssrf@user.com") -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Owner"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create(client, auth, **overrides):  # noqa: ANN001
    """``auth`` is the bearer header; ``overrides`` patch the JSON payload.

    Named apart on purpose: the payload has a ``headers`` field of its own, and
    a shared name here silently sends the auth header as the tool's static
    headers instead of testing what the test says it tests.
    """
    return await client.post(
        "/api/v1/custom-api-tools", json=_payload(**overrides), headers=auth
    )


# --- Registration: the shape check (no DNS) --------------------------------


@pytest.mark.parametrize(
    "base_url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "gopher://example.com",
        "https://user:password@example.com",
        "http://",
        "not-a-url",
    ],
)
async def test_registration_rejects_a_malformed_or_credentialed_url(
    client, custom_api_db, base_url: str
) -> None:  # noqa: ANN001
    auth = await _register_and_login(client)
    resp = await _create(client, auth, base_url=base_url)
    assert resp.status_code == 422, f"{base_url} was accepted: {resp.text}"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://169.254.169.254",  # cloud instance metadata
        "http://127.0.0.1:8000",
        "http://localhost:5432",
        "http://10.0.0.5",
        "http://192.168.1.1",
        "http://[::1]",
    ],
)
async def test_registration_rejects_a_private_or_metadata_host(
    client, custom_api_db, base_url: str
) -> None:  # noqa: ANN001
    """The resolving half of the guard, run in the route."""
    auth = await _register_and_login(client)
    resp = await _create(client, auth, base_url=base_url)
    assert resp.status_code == 422, f"{base_url} was accepted: {resp.text}"
    assert "rejected" in resp.text


async def test_registration_rejects_a_host_that_does_not_resolve(
    client, custom_api_db, monkeypatch
) -> None:  # noqa: ANN001
    """Resolution is pinned rather than asked of the network.

    Every other case in this file is deterministic — the private-host cases are
    literal IPs, the call-time ones monkeypatch the resolver. Leaving this one to
    real DNS would let a wildcard or hijacking resolver answer for
    ``api.example.com`` and turn a guard test red for an unrelated reason.
    """
    monkeypatch.setattr(url_guard, "resolve_is_public", lambda _host: False)
    auth = await _register_and_login(client)
    resp = await _create(client, auth, base_url="https://api.example.com")
    assert resp.status_code == 422, resp.text


async def test_registration_is_skipped_when_the_operator_disables_the_guard(
    client, custom_api_db, monkeypatch
) -> None:  # noqa: ANN001
    """`llm_ssrf_guard_enabled=false` means "this deployment may reach private
    hosts" — a deliberate self-hosting choice, honoured in one place."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)
    auth = await _register_and_login(client)
    resp = await _create(client, auth, base_url="http://127.0.0.1:8000")
    assert resp.status_code == 201, resp.text


# --- Header smuggling ------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    ["Authorization", "authorization", "Cookie", "Host", "Content-Length"],
)
async def test_registration_rejects_a_platform_owned_header(
    client, custom_api_db, monkeypatch, header: str
) -> None:  # noqa: ANN001
    """A static Authorization/Cookie would smuggle a second credential past the
    declared auth_mode; a static Host would rebind the request after the guard
    validated the URL."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)
    auth = await _register_and_login(client)
    resp = await _create(client, auth, headers={header: "value"})
    assert resp.status_code == 422, f"{header} was accepted: {resp.text}"


# --- Path template escape --------------------------------------------------


@pytest.mark.parametrize(
    "path_template",
    ["/v1/../admin", "//evil.example/x", "/v1?admin=1", "/v1#frag", "https://evil"],
)
async def test_registration_rejects_a_path_that_could_escape_the_base(
    client, custom_api_db, monkeypatch, path_template: str
) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)
    auth = await _register_and_login(client)
    resp = await _create(client, auth, path_template=path_template)
    assert resp.status_code == 422, f"{path_template} was accepted: {resp.text}"


# --- Call time: the second gate --------------------------------------------


def _tool(
    base_url: str = "https://api.example.com",
) -> custom_api_service.CustomApiTool:
    return custom_api_service.CustomApiTool(
        id="t1",
        slug="probe",
        name="Probe",
        description="",
        method="GET",
        base_url=base_url,
        path_template="/v1/ping",
        query_template={},
        headers={},
        auth_mode="none",
        auth_name="",
        parameters=[],
        body_template=None,
        response_json_path="",
        response_max_chars=8000,
        timeout_seconds=15,
        secret=None,
    )


async def test_call_refuses_a_host_that_turned_private_after_registration(
    monkeypatch,
) -> None:
    """The rebinding case: registration passed, then the DNS record changed.

    The window url_guard's own docstring accepts as residual risk is routine
    here, because the attacker owns the record. Re-checking per call is what
    keeps a record that was valid yesterday from being a free pass today.
    """
    sent: list[str] = []

    async def _never(*args, **kwargs):  # pragma: no cover - must not run
        sent.append(args[0] if args else "")
        return connected_common.ApiResult(data={"ok": True}, status=200)

    monkeypatch.setattr(connected_common, "request_api", _never)
    monkeypatch.setattr(url_guard, "resolve_is_public", lambda _host: False)

    result = await custom_api_service.call(_tool(), {})
    assert "not reachable" in result
    assert sent == [], "the request was sent despite the guard refusing it"


async def test_call_proceeds_when_the_host_is_public(monkeypatch) -> None:
    calls: list[str] = []

    async def _ok(url: str, **_kwargs):
        calls.append(url)
        return connected_common.ApiResult(data={"ok": True}, status=200)

    monkeypatch.setattr(connected_common, "request_api", _ok)
    monkeypatch.setattr(url_guard, "resolve_is_public", lambda _host: True)

    result = await custom_api_service.call(_tool(), {})
    assert result.startswith("<custom_api_result>"), result
    assert calls == ["https://api.example.com/v1/ping"]


async def test_call_skips_the_check_when_the_operator_disabled_the_guard(
    monkeypatch,
) -> None:
    calls: list[str] = []

    async def _ok(url: str, **_kwargs):
        calls.append(url)
        return connected_common.ApiResult(data={"ok": True}, status=200)

    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)
    monkeypatch.setattr(connected_common, "request_api", _ok)

    await custom_api_service.call(_tool("http://127.0.0.1:9000"), {})
    assert calls == ["http://127.0.0.1:9000/v1/ping"]
