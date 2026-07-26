"""Web search via DuckDuckGo (``ddgs``) — free, no API key.

Gives subagents access to current information beyond the model's training
cutoff. Best-effort by design: any failure yields an empty result list so the
task keeps running. Result snippets are untrusted external content — they are
injection-scanned here and delimited before reaching the LLM (CLAUDE.md §9.3).

A model-issued search is not one provider call. Small models reach for
``site:``/``OR``/quoted-phrase syntax that DuckDuckGo's backends — the news one
especially — answer with zero hits, and each such query used to cost the
subagent a whole budget slot with nothing to show for it. So a search that finds
nothing is retried here with the operators stripped, and a fruitless ``news``
query falls back to ``text``. The subagent sees one search; the ladder is
invisible to its budget.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

from app.core.config import settings
from app.core.constants import (
    DDGS_NO_RESULTS_MESSAGE,
    UNTRUSTED_CONTENT_NOTICE,
    WEB_SEARCH_BOOLEAN_KEYWORDS,
    WEB_SEARCH_MAX_ATTEMPTS,
    WEB_SEARCH_RESULTS_CLOSE,
    WEB_SEARCH_RESULTS_OPEN,
    WEB_SEARCH_SNIPPET_MAX_CHARS,
    WEB_SEARCH_UNSUPPORTED_OPERATORS,
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


@dataclass(slots=True)
class SearchOutcome:
    """What a search actually did, not just what it returned.

    ``query`` is the variant that produced ``results`` — which is not always the
    one the model asked for, since a fruitless query is retried relaxed.
    ``attempted`` lists every variant tried so the prompt block can name them
    and the model does not re-send a shape already known to return nothing.
    """

    results: list[SearchResult] = field(default_factory=list)
    query: str = ""
    attempted: list[str] = field(default_factory=list)


class _SearchAborted(Exception):
    """Real breakage (rate limit, timeout, crash) — stop trying variants."""


async def search(query: str, *, category: str = "text") -> SearchOutcome:
    """Run one search off-thread, relaxing the query until it finds something.

    Best-effort: any failure yields an outcome with no results.
    """
    if not settings.web_search_enabled:
        return SearchOutcome(query=query)
    try:
        return await asyncio.to_thread(_search_sync, query, category)
    except Exception:  # noqa: BLE001 - ddgs raises assorted types; best-effort
        logger.warning("Web search failed for query %r", query, exc_info=True)
        return SearchOutcome(query=query, attempted=[query])


def _search_sync(query: str, category: str) -> SearchOutcome:
    attempted: list[str] = []
    for attempt_query, attempt_category in _relaxed_attempts(query, category):
        attempted.append(attempt_query)
        try:
            raw = _fetch(attempt_query, attempt_category)
        except _SearchAborted:
            break
        if not raw:
            continue
        results = [_to_result(item) for item in raw]
        # Drop hits that look like prompt-injection payloads before the LLM sees
        # them. An empty list here means the search worked and everything in it
        # was hostile — retrying a relaxed variant would not help, so stop.
        return SearchOutcome(
            results=[r for r in results if not is_suspicious(f"{r.title} {r.snippet}")],
            query=attempt_query,
            attempted=attempted,
        )
    return SearchOutcome(
        query=attempted[-1] if attempted else query, attempted=attempted
    )


def _fetch(query: str, category: str) -> list[dict[str, str]]:
    """One provider call. Returns [] for a zero-hit search.

    Raises :class:`_SearchAborted` when the failure is real — a rate limit, a
    timeout or a crash is not fixed by simplifying the query, and retrying only
    spends the task's clock.
    """
    try:
        with DDGS(timeout=settings.web_search_timeout_seconds) as client:
            fetch = client.news if category == "news" else client.text
            return list(fetch(query, max_results=settings.web_search_max_results) or [])
    except (RatelimitException, TimeoutException):
        logger.warning("Web search backend unavailable for %r", query, exc_info=True)
        raise _SearchAborted from None
    except DDGSException as exc:
        # ddgs signals "found nothing" by raising. That is an ordinary outcome,
        # not a fault, so it must not log a traceback; anything else under this
        # base class is a wrapped engine error worth seeing, but a simpler query
        # may still reach a different engine, so the ladder continues either way.
        if str(exc) == DDGS_NO_RESULTS_MESSAGE:
            logger.debug("Web search found nothing for %r (%s)", query, category)
        else:
            logger.warning("Web search engine error for %r: %s", query, exc)
        return []
    except Exception:  # noqa: BLE001 - ddgs raises assorted types; best-effort
        logger.warning("Web search failed for query %r", query, exc_info=True)
        raise _SearchAborted from None


def _relaxed_attempts(query: str, category: str) -> list[tuple[str, str]]:
    """The ladder: as asked, then relaxed, then off the news endpoint.

    Duplicates are dropped, so a query that carries no operators costs exactly
    one provider call and a plain ``text`` search never retries itself.
    """
    relaxed = _strip_operators(query)
    candidates = [(query, category), (relaxed, category), (relaxed, "text")]
    attempts: list[tuple[str, str]] = []
    for candidate in candidates:
        if candidate[0] and candidate not in attempts:
            attempts.append(candidate)
    return attempts[:WEB_SEARCH_MAX_ATTEMPTS]


def _strip_operators(query: str) -> str:
    """Reduce a query to plain keywords DuckDuckGo actually honours."""
    words = []
    for word in query.split():
        bare = word.strip('"').strip()
        if not bare or bare.lower() in WEB_SEARCH_BOOLEAN_KEYWORDS:
            continue
        lowered = bare.lower()
        if any(lowered.startswith(op) for op in WEB_SEARCH_UNSUPPORTED_OPERATORS):
            continue
        words.append(bare)
    return " ".join(words)


def _to_result(item: dict[str, str]) -> SearchResult:
    return SearchResult(
        title=str(item.get("title", "")),
        # ``.text()`` results carry "href"; ``.news()`` results carry "url".
        url=str(item.get("href") or item.get("url") or ""),
        snippet=str(item.get("body", "")),
        date=str(item.get("date", "")),
    )


def format_results_block(outcome: SearchOutcome) -> str:
    """Render results as a delimited, untrusted-data block for the LLM."""
    if not outcome.results:
        return _no_results_block(outcome)
    lines = [WEB_SEARCH_RESULTS_OPEN, f"Query: {outcome.query}"]
    for number, result in enumerate(outcome.results, start=1):
        dated = f" ({result.date})" if result.date else ""
        lines.append(f"[{number}] {result.title} — {result.url}{dated}")
        if result.snippet:
            lines.append(f"    {result.snippet[:WEB_SEARCH_SNIPPET_MAX_CHARS]}")
    lines.append(WEB_SEARCH_RESULTS_CLOSE)
    lines.append(UNTRUSTED_CONTENT_NOTICE)
    return "\n".join(lines)


def _no_results_block(outcome: SearchOutcome) -> str:
    """Tell the model what was already tried and what to do instead.

    Naming the exhausted variants is the point: without them a model re-sends
    the same shape until its budget is gone. The closing line exists because a
    blank final answer is a subagent failure (``EMPTY_SUBAGENT_ANSWER``) — an
    unanswerable search must still produce a stated gap, never silence.
    """
    tried = "; ".join(f'"{q}"' for q in outcome.attempted) or f'"{outcome.query}"'
    return (
        f"No web results for any of these queries: {tried}. Do not repeat them. "
        "Try once more with different plain keywords (entity names, no operators, "
        "no quotes), or use data_fetch on a source URL you already know. If the "
        "data stays out of reach, answer from your own knowledge, state exactly "
        "what was unavailable, and never invent figures. Never return an empty "
        "answer."
    )
