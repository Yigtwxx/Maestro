"""Guards around fetching a manifest from a URL the user names.

This is the one path in the feature that reaches a host nobody vetted, over
content that passed no publish scan and can change after it is installed. It has
its own switch for that reason, and the same three ``url_guard`` gates as every
other user-supplied host.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.constants import PLUGIN_MANIFEST_MAX_BYTES
from app.schemas.plugin import PluginImport
from app.services import connected_common, plugin_service
from app.services.plugin_service import PluginValidationError

_MANIFEST = {
    "id": "acme.research",
    "name": "Research Kit",
    "version": "1.0.0",
    "skills": [{"slug": "teardown", "name": "T", "instructions": "do it"}],
}


# --- gate 1: the schema, sync and DNS-free ---------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/plugin.json",
        "http://user:pw@example.com/plugin.json",
        "not a url",
    ],
)
def test_a_malformed_or_credentialed_url_is_refused_at_the_schema(url):
    with pytest.raises(Exception, match="url"):
        PluginImport(url=url)


# --- gate 3: the fetch itself ----------------------------------------------


async def test_the_fetch_re_checks_the_host(monkeypatch):
    """A URL the user typed a moment ago can resolve somewhere else by now."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", True)

    async def now_private(_url):
        return "resolves to a private address"

    monkeypatch.setattr(plugin_service, "check_public_url", now_private)
    with pytest.raises(PluginValidationError, match="rejected"):
        await plugin_service.fetch_manifest("https://cdn.example.com/plugin.json")


async def test_the_fetch_is_size_capped_and_follows_no_redirect(monkeypatch):
    """The cap is enforced while streaming, so a gigabyte is abandoned rather
    than buffered; the shared client follows no redirects at all."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)
    seen: dict = {}

    async def fake_request_api(url, **kwargs):  # noqa: ANN001
        seen.update(kwargs)
        return connected_common.ApiResult(data=_MANIFEST, status=200)

    monkeypatch.setattr(connected_common, "request_api", fake_request_api)
    await plugin_service.fetch_manifest("https://cdn.example.com/plugin.json")

    assert seen["max_bytes"] == PLUGIN_MANIFEST_MAX_BYTES
    assert "follow_redirect_host" not in seen


async def test_an_oversized_manifest_is_reported_not_truncated(monkeypatch):
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)

    async def fake_request_api(url, **kwargs):  # noqa: ANN001
        return connected_common.ApiResult(status=200, oversized=True)

    monkeypatch.setattr(connected_common, "request_api", fake_request_api)
    with pytest.raises(PluginValidationError, match="too large"):
        await plugin_service.fetch_manifest("https://cdn.example.com/plugin.json")


async def test_a_non_json_body_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)

    async def fake_request_api(url, **kwargs):  # noqa: ANN001
        return connected_common.ApiResult(status=200)

    monkeypatch.setattr(connected_common, "request_api", fake_request_api)
    with pytest.raises(PluginValidationError, match="readable JSON"):
        await plugin_service.fetch_manifest("https://cdn.example.com/plugin.json")


async def test_only_the_first_validation_error_is_echoed_back(monkeypatch):
    """A full pydantic dump of a stranger's document is a lot of their text
    reflected into our UI."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)

    async def fake_request_api(url, **kwargs):  # noqa: ANN001
        return connected_common.ApiResult(
            data={"id": "BAD ID", "name": "", "version": "nope"}, status=200
        )

    monkeypatch.setattr(connected_common, "request_api", fake_request_api)
    with pytest.raises(PluginValidationError) as excinfo:
        await plugin_service.fetch_manifest("https://cdn.example.com/plugin.json")
    assert str(excinfo.value).count("—") == 1


async def test_the_log_target_is_the_host_only(monkeypatch):
    """A manifest path can key a tenant; the host is the safe label."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)
    seen: dict = {}

    async def fake_request_api(url, **kwargs):  # noqa: ANN001
        seen.update(kwargs)
        return connected_common.ApiResult(data=_MANIFEST, status=200)

    monkeypatch.setattr(connected_common, "request_api", fake_request_api)
    await plugin_service.fetch_manifest("https://cdn.example.com/secret-path/p.json")
    assert seen["log_target"] == "cdn.example.com"
