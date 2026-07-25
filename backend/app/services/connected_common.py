"""Shared plumbing for the connected-API tools (repo, social, community, places).

The four tools differ only in endpoint and parsing; everything around that is
identical and easy to get subtly wrong, so it lives here once:

* one module-global ``httpx.AsyncClient`` — also the single monkeypatch seam the
  tests replace, mirroring how ``test_web_search_service`` swaps ``DDGS`` and
  ``data_fetch_service`` exposes ``_static_fetcher``;
* :func:`request_api`, which **never raises and never logs a credential**, and
  :func:`request_json`, the same call with the outcome discarded;
* :func:`render_block`, the one output shape — delimited payload followed by
  ``UNTRUSTED_CONTENT_NOTICE``;
* :func:`drop_suspicious`, per-item injection filtering.

Why per-item dropping rather than replacing the whole block (the ``data_fetch``
convention): these tools return *lists* of user-generated posts and messages,
which is the richest prompt-injection surface in the product. One hostile
comment must not blank out 49 legitimate ones, and ``web_search_service`` already
established the drop convention for list-shaped results.

None of these tools takes a model-supplied host. Every base URL is a constant in
``core.constants``, so there is no SSRF surface and ``url_guard`` deliberately
does not appear here. Values that reach a URL *path* (a repo slug, a channel id)
are pattern-validated by their own service before interpolation.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.constants import UNTRUSTED_CONTENT_NOTICE
from app.utils.prompt_guard import is_suspicious

logger = logging.getLogger(__name__)

__all__ = [
    "ApiResult",
    "drop_suspicious",
    "failure",
    "get_client",
    "render_block",
    "request_api",
    "request_json",
    "truncate",
]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


@dataclass(slots=True)
class ApiResult:
    """What a call did, not only what it returned.

    Collapsing every failure to ``None`` is enough for a tool that can do nothing
    but report "no data". It is not enough for one that can recover: a 404 means
    the caller asked for the wrong thing and should ask again, while a 403 means
    it should stop. ``status`` is 0 when no response was produced at all.
    """

    data: Any | None = None
    status: int = 0
    rate_limited: bool = False


# Module-global so a single client is reused across calls (connection pooling)
# and so tests have one place to patch. Reset by the autouse conftest fixture.
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Return the shared HTTP client, creating it on first use."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(follow_redirects=False)
    return _client


async def close_client() -> None:
    """Dispose of the shared client (application shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    timeout: float,
    log_target: str | None = None,
) -> Any | None:
    """Call ``url`` and parse the JSON response. Returns None on any failure.

    Never raises: ``subagent._execute`` has no ``try/except``, so an exception
    escaping a tool executor fails the entire subtask.

    Never logs ``headers`` (they carry the bearer token), the response body, or
    the query string. ``log_target`` overrides the derived host+path label for
    the one provider that puts its credential in the URL *path* — see
    :func:`_safe_target`.
    """
    result = await request_api(
        url,
        method=method,
        headers=headers,
        params=params,
        json_body=json_body,
        timeout=timeout,
        log_target=log_target,
    )
    return result.data


async def request_api(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    timeout: float,
    log_target: str | None = None,
    follow_redirect_host: str | None = None,
) -> ApiResult:
    """Call ``url`` and report both the parsed JSON and how the call ended.

    Same guarantees as :func:`request_json` — never raises, never logs a
    credential — with the outcome kept so a caller can tell "you asked for the
    wrong thing" from "stop asking".

    ``follow_redirect_host`` opts into following **one** redirect, and only to
    that exact host. The shared client has redirects disabled, so a provider that
    answers a renamed resource with 301 (GitHub does) reads as a plain failure
    without this. A hop anywhere else is refused *before* it is requested, which
    is what stops a redirect from carrying ``headers`` — the bearer token — to
    another origin.
    """
    target = log_target or _safe_target(url)
    response = await _send(method, url, headers, params, json_body, timeout, target)
    if response is None:
        return ApiResult()

    if follow_redirect_host and response.status_code in _REDIRECT_STATUSES:
        hop = urljoin(url, response.headers.get("location", "")) or ""
        if urlsplit(hop).netloc != follow_redirect_host:
            logger.warning(
                "Connected API redirect refused: %s -> %s",
                target,
                urlsplit(hop).netloc or "<no location>",
            )
            return ApiResult(status=response.status_code)
        target = _safe_target(hop)
        response = await _send(method, hop, headers, params, json_body, timeout, target)
        if response is None:
            return ApiResult()

    if response.status_code >= 400:
        # Status only. A 4xx body from these providers frequently echoes the
        # request, which is how a token ends up in a log.
        logger.warning("Connected API returned %s: %s", response.status_code, target)
        return ApiResult(
            status=response.status_code, rate_limited=_is_rate_limited(response)
        )
    try:
        return ApiResult(data=response.json(), status=response.status_code)
    except Exception:  # noqa: BLE001 - a non-JSON body is a provider change
        logger.warning("Connected API returned non-JSON: %s", target)
        return ApiResult(status=response.status_code)


async def _send(
    method: str,
    url: str,
    headers: dict[str, str] | None,
    params: dict[str, Any] | None,
    json_body: Any | None,
    timeout: float,
    target: str,
) -> httpx.Response | None:
    """One HTTP call. Returns None — never raises — on any transport failure."""
    try:
        return await get_client().request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001 - httpx raises assorted types; best-effort
        logger.warning("Connected API request failed: %s", target)
        return None


def _is_rate_limited(response: httpx.Response) -> bool:
    """Separate an exhausted quota from a rejected credential.

    GitHub returns 403 for both, and the difference decides whether the caller
    should report a quota gap or a broken key — advice a model can act on either
    way, but only if we get it right.
    """
    if response.status_code not in (403, 429):
        return False
    return (
        response.headers.get("x-ratelimit-remaining") == "0"
        or "retry-after" in response.headers
    )


def _safe_target(url: str) -> str:
    """host + path of a URL — never the query string, which carries secrets.

    The path is not automatically safe either: Telegram's Bot API embeds the
    token as a path segment (``/bot<token>/getUpdates``). That caller passes an
    explicit ``log_target`` instead of relying on this.
    """
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}"


def drop_suspicious(items: Sequence[Any], text_of: Callable[[Any], str]) -> list[Any]:
    """Drop items whose text looks like a prompt-injection payload."""
    return [item for item in items if not is_suspicious(text_of(item))]


def truncate(text: str, limit: int) -> str:
    """Collapse whitespace and cap length — token cost control per item."""
    collapsed = " ".join(str(text).split())
    return collapsed[:limit]


def render_block(
    *,
    open_tag: str,
    close_tag: str,
    header: str,
    payload: Any,
) -> str:
    """Render a tool result as a delimited, untrusted-data block for the LLM.

    ``payload`` is serialized with the stdlib JSON encoder (not orjson) so the
    output is a plain ``str`` and ``ensure_ascii=False`` keeps non-Latin text
    readable to the model instead of escaped.
    """
    body = json.dumps(payload, ensure_ascii=False)
    return "\n".join([open_tag, header, body, close_tag, UNTRUSTED_CONTENT_NOTICE])


def failure(tool: str, reason: str) -> str:
    """A tool result the model can act on. Mirrors ``data_fetch_service._failure``.

    Deliberately prose rather than an exception: the subagent should carry on
    with its remaining tools and say what it could not reach.
    """
    return (
        f"The {tool} tool could not complete this call: {reason}. "
        "Continue without it and note the limitation."
    )
