"""The repo_intel recovery ladder: a wrong slug must not be a dead end.

A model guesses a repository owner from a package name, or remembers a project
under the name it had before it moved. Both land as a plain 404, and the agent
used to be told only "unknown, private, or rate-limited" — nothing it could act
on. These tests pin the three ways out (drop a token that cannot see the repo,
follow a rename, search for where the project actually lives), the honesty of
the header when one of them fires, and — just as important — the cases where the
ladder must *not* run, because every rung is a real request against a 60/hour
anonymous quota.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.constants import REPO_INTEL_MAX_ATTEMPTS
from app.services import connected_common, repo_intel_service
from app.services.connected_common import ApiResult
from app.services.service_key_service import ServiceCredentials

WITH_KEY = ServiceCredentials({"github": "gh-token"})
NO_KEY = ServiceCredentials()

NOT_FOUND = ApiResult(status=404)
PROFILE = {"full_name": "requests/toolbelt", "stargazers_count": 1038}


def _search_hit(full_name: str) -> dict[str, object]:
    return {"items": [{"full_name": full_name}]}


# --- the ladder ------------------------------------------------------------


async def test_a_missing_repo_is_resolved_by_search_and_retried(http):
    """The reported case: psf/requests-toolbelt is at requests/toolbelt."""
    fake = http(NOT_FOUND, _search_hit("requests/toolbelt"), PROFILE)

    block = await repo_intel_service.fetch("psf/requests-toolbelt", credentials=NO_KEY)

    urls = [str(c["url"]) for c in fake.calls]
    assert "/search/repositories" in urls[1], f"A 404 must trigger a search: {urls}"
    assert urls[2].endswith("/repos/requests/toolbelt"), (
        f"The resolved slug must be retried: {urls}"
    )
    assert '"stars": 1038' in block, f"The retry's payload must be returned: {block}"


async def test_a_resolved_repo_is_named_in_the_header(http):
    """Analysing a different repository silently would be worse than failing."""
    http(NOT_FOUND, _search_hit("requests/toolbelt"), PROFILE)

    block = await repo_intel_service.fetch("psf/requests-toolbelt", credentials=NO_KEY)

    assert "Repo: requests/toolbelt" in block, f"The real slug must lead: {block}"
    assert 'requested "psf/requests-toolbelt"' in block, (
        f"The agent must be able to notice a wrong resolution: {block}"
    )


async def test_a_token_that_cannot_see_a_public_repo_falls_back_to_anonymous(http):
    """A fine-grained PAT scoped to selected repos 404s on every other one.

    Without this, storing a key makes a squad that works keyless stop working,
    and nothing anywhere says why.
    """
    fake = http(NOT_FOUND, PROFILE, PROFILE)

    block = await repo_intel_service.fetch("requests/toolbelt", credentials=WITH_KEY)

    assert "Authorization" in fake.calls[0]["headers"], "The first try uses the token"
    assert "Authorization" not in fake.calls[1]["headers"], (
        "An authenticated probe would prove nothing about the token"
    )
    assert "Authorization" not in fake.calls[2]["headers"], (
        "Once the token is known to be blind here it must not be used again"
    )
    assert "could not see this repository" in block, (
        f"The tier change must be reportable in Data coverage: {block}"
    )


async def test_an_unresolvable_repo_tells_the_model_what_to_do_next(http):
    fake = http(NOT_FOUND, {"items": []})

    block = await repo_intel_service.fetch("nope/nope", credentials=NO_KEY)

    assert len(fake.calls) == 2, f"One aspect call, one search: {fake.calls}"
    assert "Verify the exact owner/name" in block, f"Must be actionable: {block}"
    assert "do not guess an owner from a package name" in block, (
        f"This is the mistake that produced the bug: {block}"
    )


async def test_a_malformed_search_result_is_never_put_into_a_url(http):
    """A provider response is not trusted input just because it is the provider."""
    fake = http(NOT_FOUND, _search_hit("../../etc/passwd"))

    block = await repo_intel_service.fetch("nope/nope", credentials=NO_KEY)

    assert len(fake.calls) == 2, (
        f"The candidate must be rejected, not fetched: {fake.calls}"
    )
    assert "could not complete" in block, f"A notice must be returned: {block}"


async def test_the_ladder_stops_at_max_attempts(http):
    """Every rung is a real call against a 60/hour quota, so it must be bounded."""
    fake = http(
        NOT_FOUND,
        NOT_FOUND,  # attempt 1, authenticated
        PROFILE,  # the anonymous probe can see it
        NOT_FOUND,
        NOT_FOUND,  # attempt 2, anonymous
        _search_hit("requests/toolbelt"),
        NOT_FOUND,
        NOT_FOUND,  # attempt 3, resolved slug
        PROFILE,
        PROFILE,  # a fourth attempt must never reach these
    )

    block = await repo_intel_service.fetch(
        "psf/requests-toolbelt", aspect="activity", credentials=WITH_KEY
    )

    commits = [c for c in fake.calls if str(c["url"]).endswith("/commits")]
    assert len(commits) == REPO_INTEL_MAX_ATTEMPTS, (
        f"Ladder ran away: {[str(c['url']) for c in fake.calls]}"
    )
    assert "could not complete" in block, f"An exhausted ladder is a notice: {block}"


# --- where the ladder must not run -----------------------------------------


async def test_an_exhausted_rate_limit_does_not_trigger_a_search(http):
    """Deepening a rate limit does not make a wrong answer arrive sooner."""
    fake = http(ApiResult(status=403, rate_limited=True))

    block = await repo_intel_service.fetch("requests/toolbelt", credentials=NO_KEY)

    assert len(fake.calls) == 1, f"Only a 404 is recoverable: {fake.calls}"
    assert "rate limit is exhausted" in block, f"Must not read as missing: {block}"


async def test_a_rejected_token_is_named_as_the_problem(http):
    fake = http(ApiResult(status=401))

    block = await repo_intel_service.fetch("requests/toolbelt", credentials=WITH_KEY)

    assert len(fake.calls) == 1, (
        f"A rejected credential is not a wrong slug: {fake.calls}"
    )
    assert "Settings > API Keys" in block, f"The fix must be actionable: {block}"


async def test_the_happy_path_makes_no_extra_request(http):
    fake = http(PROFILE)

    block = await repo_intel_service.fetch("requests/toolbelt", credentials=WITH_KEY)

    assert len(fake.calls) == 1, (
        f"Recovery must cost nothing when nothing failed: {fake.calls}"
    )
    assert "resolved by GitHub search" not in block, f"Nothing was resolved: {block}"
    assert "access: authenticated" in block, f"The token was used and worked: {block}"


# --- the one-hop redirect (connected_common) -------------------------------


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )


async def test_a_rename_redirect_is_followed_within_github(monkeypatch):
    """GitHub answers a moved repository with 301; not following it loses the repo."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path.startswith("/repos/"):
            return httpx.Response(
                301,
                headers={"location": "https://api.github.com/repositories/15515181"},
            )
        return httpx.Response(200, json={"full_name": "requests/toolbelt"})

    monkeypatch.setattr(connected_common, "_client", _mock_client(handler))

    result = await connected_common.request_api(
        "https://api.github.com/repos/sigmavirus24/requests-toolbelt",
        timeout=5,
        follow_redirect_host="api.github.com",
    )

    assert result.data == {"full_name": "requests/toolbelt"}, f"Hop lost: {result}"
    assert len(seen) == 2, f"Exactly one hop, no more: {seen}"


async def test_a_redirect_to_another_host_is_refused_before_it_is_requested(
    monkeypatch,
):
    """The hop would carry the Authorization header, so it must never be made."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(301, headers={"location": "https://evil.example.com/x"})

    monkeypatch.setattr(connected_common, "_client", _mock_client(handler))

    result = await connected_common.request_api(
        "https://api.github.com/repos/a/b",
        headers={"Authorization": "Bearer secret"},
        timeout=5,
        follow_redirect_host="api.github.com",
    )

    assert result.data is None, "A refused redirect yields no data"
    assert result.status == 301, f"The status must survive for the caller: {result}"
    assert [r.url.host for r in seen] == ["api.github.com"], (
        f"The token must never leave GitHub: {[str(r.url) for r in seen]}"
    )


async def test_redirects_are_not_followed_without_an_explicit_host(monkeypatch):
    """The other three tools opt out, and the shared client still follows nothing."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(301, headers={"location": "https://api.github.com/b"})

    monkeypatch.setattr(connected_common, "_client", _mock_client(handler))

    result = await connected_common.request_api("https://api.github.com/a", timeout=5)

    assert len(seen) == 1, f"Opt-in means opt-in: {seen}"
    assert result.data is None, "An unfollowed redirect carries no body"


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({"x-ratelimit-remaining": "0"}, True),
        ({"retry-after": "60"}, True),
        ({"x-ratelimit-remaining": "59"}, False),
        ({}, False),
    ],
)
async def test_an_exhausted_quota_is_told_apart_from_a_bad_credential(
    monkeypatch, headers, expected
):
    """GitHub returns 403 for both, and the advice to the model differs."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers=headers, json={"message": "Forbidden"})

    monkeypatch.setattr(connected_common, "_client", _mock_client(handler))

    result = await connected_common.request_api("https://api.github.com/a", timeout=5)

    assert result.rate_limited is expected, f"Misread 403 with {headers}: {result}"
