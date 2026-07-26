"""Social listening over the X (Twitter) API v2 recent-search endpoint.

Backs the ``social_search`` tool for the ``social`` squad. What a connected key
buys over ``web_search`` is not "more pages" but **countable items**: each post
arrives with a timestamp and public engagement metrics, so an agent can compute
volume, velocity and engagement-weighted distribution instead of describing a
vibe.

Honest limitation, stated in the result header so the agent can repeat it: the
recent-search endpoint covers roughly the last 7 days on the tiers most BYOK
users hold. A ``30d`` window is therefore requested but not guaranteed — X
decides, and what comes back is what the agent gets.

Post text is user-generated and is the richest prompt-injection surface in the
product; every item is scanned and dropped individually before the block is
built. Best-effort throughout: failures return a notice, never an exception.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.constants import (
    CONNECTED_DEFAULT_WINDOW,
    CONNECTED_TOOL_MISSING_KEY_NOTICE,
    CONNECTED_WINDOWS,
    SOCIAL_SEARCH_ITEM_MAX_CHARS,
    SOCIAL_SEARCH_QUERY_MAX_CHARS,
    SOCIAL_SEARCH_RESULT_CLOSE,
    SOCIAL_SEARCH_RESULT_OPEN,
    X_API_BASE_URL,
    LLMProvider,
)
from app.services.connected_common import (
    drop_suspicious,
    failure,
    render_block,
    request_json,
    truncate,
)
from app.services.service_key_service import ServiceCredentials

logger = logging.getLogger(__name__)

_TOOL = "social_search"
# X rejects max_results outside this range with a 400.
_MIN_RESULTS = 10
_MAX_RESULTS = 100
_WINDOW_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}


async def fetch(
    query: str,
    *,
    window: str = CONNECTED_DEFAULT_WINDOW,
    credentials: ServiceCredentials,
) -> str:
    """Return a delimited block of recent X posts matching ``query``."""
    if not settings.social_search_enabled:
        return failure(_TOOL, "the tool is disabled")
    terms = truncate(query or "", SOCIAL_SEARCH_QUERY_MAX_CHARS)
    if not terms:
        return failure(_TOOL, "no search query was provided")
    if window not in CONNECTED_WINDOWS:
        window = CONNECTED_DEFAULT_WINDOW

    token = credentials.get(LLMProvider.X)
    if not token:
        return CONNECTED_TOOL_MISSING_KEY_NOTICE.format(provider=LLMProvider.X.value)

    payload = await _search(terms, window, token)
    if payload is None:
        return failure(
            _TOOL, "X returned no usable response (rate limit, auth, or plan tier)"
        )
    if not payload["posts"]:
        return failure(_TOOL, f'X returned no posts for "{terms}" in the last {window}')

    return render_block(
        open_tag=SOCIAL_SEARCH_RESULT_OPEN,
        close_tag=SOCIAL_SEARCH_RESULT_CLOSE,
        header=(
            f"Query: {terms} | window: {window} | "
            f"posts returned: {len(payload['posts'])}"
        ),
        payload=payload,
    )


async def _search(terms: str, window: str, token: str) -> dict[str, Any] | None:
    start = datetime.now(UTC) - timedelta(hours=_WINDOW_HOURS[window])
    limit = max(_MIN_RESULTS, min(settings.social_search_max_results, _MAX_RESULTS))
    data = await request_json(
        f"{X_API_BASE_URL}/tweets/search/recent",
        headers={"Authorization": f"Bearer {token}"},
        params={
            # Exclude retweets: an amplified copy inflates volume without adding
            # a distinct opinion, and the `voices` member measures amplification
            # from the metrics instead.
            "query": f"{terms} -is:retweet",
            "max_results": limit,
            "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tweet.fields": "created_at,public_metrics,lang",
            "expansions": "author_id",
            "user.fields": "username,name,public_metrics,verified",
        },
        timeout=settings.social_search_timeout_seconds,
    )
    if not isinstance(data, dict):
        return None

    authors = _index_authors(data)
    posts = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        metrics = item.get("public_metrics") or {}
        author = authors.get(str(item.get("author_id")), {})
        posts.append(
            {
                "text": truncate(item.get("text") or "", SOCIAL_SEARCH_ITEM_MAX_CHARS),
                "author": author.get("username"),
                "author_followers": author.get("followers"),
                "created_at": item.get("created_at"),
                "lang": item.get("lang"),
                "likes": metrics.get("like_count"),
                "reposts": metrics.get("retweet_count"),
                "replies": metrics.get("reply_count"),
                "quotes": metrics.get("quote_count"),
            }
        )
    posts = drop_suspicious(posts, lambda p: str(p.get("text", "")))
    return {"posts": posts}


def _index_authors(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map author_id -> user, from the `includes` side-channel X returns.

    Posts carry only ``author_id``; without this join every post would read as
    anonymous and the `voices` member would have nothing to work with.
    """
    includes = data.get("includes")
    users = includes.get("users") if isinstance(includes, dict) else None
    indexed: dict[str, dict[str, Any]] = {}
    for user in users or []:
        if not isinstance(user, dict):
            continue
        metrics = user.get("public_metrics") or {}
        indexed[str(user.get("id"))] = {
            "username": user.get("username"),
            "followers": metrics.get("followers_count"),
        }
    return indexed
