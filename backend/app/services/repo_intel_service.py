"""Repository intelligence over the GitHub REST API.

Backs the ``repo_intel`` tool for the ``opensource`` squad: instead of reading
one page about a project, an agent asks for a specific *aspect* and gets
structured facts it can compute over — release cadence, close-time distribution,
contributor concentration.

**This is the one connected tool that works with no key at all.** GitHub serves
anonymous reads at 60 requests/hour; a stored token raises the ceiling to 5000.
So the squad is fully functional out of the box and a key is purely an
accelerator — which is exactly the contract the other three tools promise but
cannot demonstrate without credentials.

A slug is the one input a model reliably gets wrong: it guesses an owner from a
package name, or remembers a repository under the name it had before it moved.
Both land as a plain 404, so :func:`fetch` runs a bounded recovery ladder —
drop to the anonymous tier if the *token* is what cannot see the repository,
then ask GitHub's search where the project actually lives. What the ladder did
is always stated in the result header: silently analysing a different repository
than the one asked for would be worse than failing.

Best-effort like every tool service: any failure returns a notice, never an
exception (``subagent._execute`` has no ``try/except``).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import settings
from app.core.constants import (
    GITHUB_API_BASE_URL,
    GITHUB_API_HOST,
    GITHUB_SEARCH_REPOS_PATH,
    REPO_INTEL_ASPECTS,
    REPO_INTEL_COMMIT_MAX_CHARS,
    REPO_INTEL_DEFAULT_ASPECT,
    REPO_INTEL_ITEM_MAX_CHARS,
    REPO_INTEL_MAX_ATTEMPTS,
    REPO_INTEL_REPO_PATTERN,
    REPO_INTEL_RESULT_CLOSE,
    REPO_INTEL_RESULT_OPEN,
    REPO_INTEL_SEARCH_CANDIDATES,
    LLMProvider,
)
from app.services.connected_common import (
    ApiResult,
    drop_suspicious,
    failure,
    render_block,
    request_api,
    truncate,
)
from app.services.service_key_service import ServiceCredentials

logger = logging.getLogger(__name__)

_TOOL = "repo_intel"
_REPO_RE = re.compile(REPO_INTEL_REPO_PATTERN)
_NOT_FOUND = 404

# GitHub rejects requests without a User-Agent with 403 — this is not optional.
_BASE_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "maestro-agent",
}

# One aspect attempt: the payload, and the call outcome that explains its
# absence — carried whole so "quota exhausted" survives as far as the message.
_Attempt = tuple[dict[str, Any] | None, ApiResult]


async def fetch(
    repo: str,
    *,
    aspect: str = REPO_INTEL_DEFAULT_ASPECT,
    credentials: ServiceCredentials,
) -> str:
    """Return a delimited block of GitHub facts for ``repo``. Never raises."""
    if not settings.repo_intel_enabled:
        return failure(_TOOL, "the tool is disabled")
    requested = (repo or "").strip()
    # ``repo`` is interpolated into a URL path, so it is validated before it can
    # reach a request at all — no traversal, no injected query, no other host.
    if not _REPO_RE.match(requested):
        return failure(_TOOL, f'"{repo}" is not a valid "owner/name" repository')
    if aspect not in REPO_INTEL_ASPECTS:
        aspect = REPO_INTEL_DEFAULT_ASPECT

    token = credentials.get(LLMProvider.GITHUB)
    headers = _headers(token)
    slug = requested
    token_blocked = False
    attempts = 1

    payload, outcome = await _fetch_aspect(slug, aspect, headers)

    # Step A — is the *token* what cannot see this repository? A fine-grained PAT
    # scoped to selected repositories answers 404 for every other one, public
    # included, so a stored key can make a squad that works keyless stop working.
    # The anonymous tier is still 60 reads/hour, so falling back to it is a real
    # recovery rather than a consolation.
    if _missing(payload, outcome) and token and attempts < REPO_INTEL_MAX_ATTEMPTS:
        probe = await _get(f"/repos/{slug}", _headers(None))
        if probe.data is not None:
            token_blocked = True
            headers = _headers(None)
            attempts += 1
            payload, outcome = await _fetch_aspect(slug, aspect, headers)

    # Step B — wrong owner, or the project moved. Only ever on a 404: deepening a
    # rate limit does not make a wrong answer arrive sooner.
    if _missing(payload, outcome) and attempts < REPO_INTEL_MAX_ATTEMPTS:
        found = await _search_repo(slug, headers)
        if found and found != slug:
            attempts += 1
            candidate, candidate_outcome = await _fetch_aspect(found, aspect, headers)
            if candidate is not None:
                slug, payload, outcome = found, candidate, candidate_outcome

    if payload is None:
        return failure(_TOOL, _failure_reason(slug, outcome, bool(token)))

    return render_block(
        open_tag=REPO_INTEL_RESULT_OPEN,
        close_tag=REPO_INTEL_RESULT_CLOSE,
        header=_header(
            slug=slug,
            requested=requested,
            aspect=aspect,
            token=bool(token),
            token_blocked=token_blocked,
        ),
        payload=payload,
    )


def _missing(payload: dict[str, Any] | None, outcome: ApiResult) -> bool:
    """Did this attempt fail in the one way the ladder can do something about?

    Only a 404 means "you asked for the wrong thing". Every other failure is
    about the caller's standing or GitHub's mood, and retrying a variant of the
    same question just spends the task's clock — the same rule the web-search
    ladder follows.
    """
    return payload is None and outcome.status == _NOT_FOUND


def _headers(token: str | None) -> dict[str, str]:
    headers = dict(_BASE_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _header(
    *,
    slug: str,
    requested: str,
    aspect: str,
    token: bool,
    token_blocked: bool,
) -> str:
    """State which repository these facts came from and on whose authority.

    The resolved slug is named because GitHub's search returns a *best* match,
    not a certain one — the agent has to be able to notice that the project it
    got is not the project it asked about. The access tier is named so the
    mandatory ``Data coverage`` section can be honest about it.
    """
    origin = (
        ""
        if slug == requested
        else f' (requested "{requested}", resolved by GitHub search)'
    )
    if token_blocked:
        access = (
            "unauthenticated (60 req/hour; the stored token could not see "
            "this repository, so it was not used)"
        )
    elif token:
        access = "authenticated"
    else:
        access = "unauthenticated (60 req/hour)"
    return f"Repo: {slug}{origin} | aspect: {aspect} | access: {access}"


def _failure_reason(slug: str, outcome: ApiResult, token: bool) -> str:
    """Say what went wrong precisely enough for the model to do something else.

    The old single message covered unknown, private and rate-limited at once,
    which left a model with a mistyped slug no way to tell that retrying with a
    corrected one was the move.
    """
    status = outcome.status
    if status == _NOT_FOUND:
        return (
            f'GitHub has no repository "{slug}", and a search for a renamed or '
            "moved project matched nothing. Verify the exact owner/name from the "
            "project's repository URL — do not guess an owner from a package "
            "name — or use web_search to find where the project actually lives"
        )
    if outcome.rate_limited:
        return (
            "the GitHub rate limit is exhausted (anonymous reads are 60/hour); "
            "use web_search instead and mark those figures as unverified"
        )
    if status in (401, 403):
        if token:
            return (
                "GitHub rejected the stored token — check that the GitHub key "
                "under Settings > API Keys is valid and has not expired"
            )
        return "GitHub refused the request"
    if status == 0:
        return "GitHub could not be reached"
    return f"GitHub returned an unexpected status ({status})"


async def _search_repo(slug: str, headers: dict[str, str]) -> str | None:
    """Find the repository a wrong owner or an old name was meant to point at.

    Searching on the *name* alone is deliberate: the owner is the half a model
    gets wrong (a package name is not an org name), and requiring the name to
    match exactly would miss the common case where a project was renamed as it
    moved — ``requests-toolbelt`` now lives at ``requests/toolbelt``.
    """
    name = slug.split("/", 1)[1]
    result = await _get(
        GITHUB_SEARCH_REPOS_PATH,
        headers,
        q=name,
        per_page=REPO_INTEL_SEARCH_CANDIDATES,
    )
    if not isinstance(result.data, dict):
        return None
    for item in result.data.get("items") or []:
        if not isinstance(item, dict):
            continue
        candidate = str(item.get("full_name") or "")
        # This reaches a URL path exactly as the model's own input did, so it is
        # validated exactly as strictly — a provider response is not trusted
        # input just because it came from the provider.
        if _REPO_RE.match(candidate):
            return candidate
    return None


async def _fetch_aspect(slug: str, aspect: str, headers: dict[str, str]) -> _Attempt:
    if aspect == "profile":
        return await _profile(slug, headers)
    if aspect == "activity":
        return await _activity(slug, headers)
    if aspect == "issues":
        return await _issues(slug, headers)
    return await _releases(slug, headers)


def _limit() -> int:
    return settings.repo_intel_max_results


async def _get(path: str, headers: dict[str, str], **params: Any) -> ApiResult:
    return await request_api(
        f"{GITHUB_API_BASE_URL}{path}",
        headers=headers,
        params=params or None,
        timeout=settings.repo_intel_timeout_seconds,
        # GitHub answers a renamed or transferred repository with 301 and the
        # shared client follows nothing; without this a rename is indistinguishable
        # from a deletion. Pinned to one host, so no hop can carry the token away.
        follow_redirect_host=GITHUB_API_HOST,
    )


async def _profile(slug: str, headers: dict[str, str]) -> _Attempt:
    """Identity, licensing and headline counts."""
    result = await _get(f"/repos/{slug}", headers)
    data = result.data
    if not isinstance(data, dict):
        return None, result
    licence = data.get("license") or {}
    return {
        "full_name": data.get("full_name"),
        "description": truncate(
            data.get("description") or "", REPO_INTEL_ITEM_MAX_CHARS
        ),
        "language": data.get("language"),
        "license": licence.get("spdx_id") if isinstance(licence, dict) else None,
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "watchers": data.get("subscribers_count"),
        "open_issues": data.get("open_issues_count"),
        "topics": (data.get("topics") or [])[:10],
        "archived": data.get("archived"),
        "created_at": data.get("created_at"),
        "pushed_at": data.get("pushed_at"),
        "default_branch": data.get("default_branch"),
        "homepage": data.get("homepage"),
    }, result


async def _activity(slug: str, headers: dict[str, str]) -> _Attempt:
    """Recent commit rhythm plus contributor concentration (the bus-factor input)."""
    commits = await _get(f"/repos/{slug}/commits", headers, per_page=_limit())
    contributors = await _get(
        f"/repos/{slug}/contributors", headers, per_page=_limit(), anon="false"
    )
    if not isinstance(commits.data, list) and not isinstance(contributors.data, list):
        # Both target the same repository, so the commits outcome explains both.
        return None, commits

    recent = []
    for item in commits.data if isinstance(commits.data, list) else []:
        if not isinstance(item, dict):
            continue
        commit = item.get("commit") or {}
        author = commit.get("author") or {}
        # Subject line only. Full commit bodies are mostly changelogs and URLs;
        # keeping them pushed one `activity` call past 8000 characters, which is
        # both a token cost and enough to trip transcript compaction.
        subject = str(commit.get("message") or "").split("\n", 1)[0]
        recent.append(
            {
                "date": author.get("date"),
                "author": author.get("name"),
                "message": truncate(subject, REPO_INTEL_COMMIT_MAX_CHARS),
            }
        )
    # A commit message is attacker-controlled on any repo that accepts PRs.
    recent = drop_suspicious(recent, lambda c: str(c.get("message", "")))

    top = [
        {"login": c.get("login"), "contributions": c.get("contributions")}
        for c in (contributors.data if isinstance(contributors.data, list) else [])
        if isinstance(c, dict)
    ]
    payload = {"recent_commits": recent, "top_contributors": top[: _limit()]}
    return payload, commits


async def _issues(slug: str, headers: dict[str, str]) -> _Attempt:
    """Issue backlog shape. Pull requests are excluded, see below."""
    result = await _get(
        f"/repos/{slug}/issues",
        headers,
        state="all",
        sort="updated",
        per_page=_limit(),
    )
    if not isinstance(result.data, list):
        return None, result
    issues = []
    for item in result.data:
        if not isinstance(item, dict):
            continue
        # GitHub's /issues endpoint returns pull requests too; the only reliable
        # discriminator is the presence of this key. Counting PRs as issues would
        # quietly corrupt every close-time and backlog metric downstream.
        if "pull_request" in item:
            continue
        user = item.get("user") or {}
        issues.append(
            {
                "number": item.get("number"),
                "title": truncate(item.get("title") or "", REPO_INTEL_ITEM_MAX_CHARS),
                "state": item.get("state"),
                "comments": item.get("comments"),
                "author": user.get("login") if isinstance(user, dict) else None,
                "created_at": item.get("created_at"),
                "closed_at": item.get("closed_at"),
                "labels": [
                    label.get("name")
                    for label in (item.get("labels") or [])
                    if isinstance(label, dict)
                ][:5],
            }
        )
    issues = drop_suspicious(issues, lambda i: str(i.get("title", "")))
    return {"issues": issues}, result


async def _releases(slug: str, headers: dict[str, str]) -> _Attempt:
    """Release cadence — the cheapest honest signal of whether a project ships."""
    result = await _get(f"/repos/{slug}/releases", headers, per_page=_limit())
    if not isinstance(result.data, list):
        return None, result
    releases = [
        {
            "tag": item.get("tag_name"),
            "name": truncate(item.get("name") or "", REPO_INTEL_ITEM_MAX_CHARS),
            "published_at": item.get("published_at"),
            "prerelease": item.get("prerelease"),
        }
        for item in result.data
        if isinstance(item, dict)
    ]
    return {"releases": releases}, result
