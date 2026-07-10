"""Web search via DuckDuckGo (``ddgs``) — free, no API key.

Gives subagents access to current information beyond the model's training
cutoff. Best-effort by design: any failure yields an empty result list so the
task keeps running. Result snippets are untrusted external content — they are
injection-scanned here and delimited before reaching the LLM (CLAUDE.md §9.3).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from ddgs import DDGS

from app.core.config import settings
from app.core.constants import (
    UNTRUSTED_CONTENT_NOTICE,
    WEB_SEARCH_RESULTS_CLOSE,
    WEB_SEARCH_RESULTS_OPEN,
    WEB_SEARCH_SNIPPET_MAX_CHARS,
)
from app.utils.prompt_guard import is_suspicious

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchResult:
    """One web search hit, normalized across ddgs result shapes."""

    title: str
    url: str
    snippet: str
    date: str = ""


async def search(query: str, *, category: str = "text") -> list[SearchResult]:
    """Run one search off-thread. Best-effort: any failure returns []."""
    if not settings.web_search_enabled:
        return []
    try:
        return await asyncio.to_thread(_search_sync, query, category)
    except Exception:  # noqa: BLE001 - ddgs raises assorted types; best-effort
        logger.warning("Web search failed for query %r", query, exc_info=True)
        return []


def _search_sync(query: str, category: str) -> list[SearchResult]:
    with DDGS(timeout=settings.web_search_timeout_seconds) as client:
        fetch = client.news if category == "news" else client.text
        raw = fetch(query, max_results=settings.web_search_max_results)
    results = [_to_result(item) for item in raw or []]
    # Drop hits that look like prompt-injection payloads before the LLM sees them.
    return [r for r in results if not is_suspicious(f"{r.title} {r.snippet}")]


def _to_result(item: dict[str, str]) -> SearchResult:
    return SearchResult(
        title=str(item.get("title", "")),
        # ``.text()`` results carry "href"; ``.news()`` results carry "url".
        url=str(item.get("href") or item.get("url") or ""),
        snippet=str(item.get("body", "")),
        date=str(item.get("date", "")),
    )


def format_results_block(query: str, results: list[SearchResult]) -> str:
    """Render results as a delimited, untrusted-data block for the LLM."""
    if not results:
        return (
            f'No web results were found for "{query}". '
            "Answer from your own knowledge and explicitly note this limitation."
        )
    lines = [WEB_SEARCH_RESULTS_OPEN, f"Query: {query}"]
    for number, result in enumerate(results, start=1):
        dated = f" ({result.date})" if result.date else ""
        lines.append(f"[{number}] {result.title} — {result.url}{dated}")
        if result.snippet:
            lines.append(f"    {result.snippet[:WEB_SEARCH_SNIPPET_MAX_CHARS]}")
    lines.append(WEB_SEARCH_RESULTS_CLOSE)
    lines.append(UNTRUSTED_CONTENT_NOTICE)
    return "\n".join(lines)
