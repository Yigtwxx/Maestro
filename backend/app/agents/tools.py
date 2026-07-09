"""Executable tool directives for the subagent loop.

Provider-agnostic by design: instead of native function calling, the model
replies with a small JSON object naming an action; we execute it and feed the
result back. This module parses those directives and resolves which tools a
domain may use at runtime.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.agents.registry import get_domain_info
from app.core.config import settings
from app.core.constants import (
    CODE_EXECUTION_ACTION,
    CODE_EXECUTION_PREVIEW_MAX_CHARS,
    DATA_FETCH_ACTION,
    EXECUTABLE_TOOL_IDS,
    OBJECTIVE_MAX_CHARS,
    ORIGINAL_REQUEST_CLOSE,
    ORIGINAL_REQUEST_OPEN,
    VIEW_ORIGINAL_REQUEST_ACTION,
    WEB_SEARCH_ACTION,
    WEB_SEARCH_CATEGORIES,
    WEB_SEARCH_DEFAULT_CATEGORY,
)
from app.services import code_execution_service, data_fetch_service, web_search_service

from .base import extract_json, truncate_text


@dataclass(slots=True)
class ToolDirective:
    """One parsed tool request from the model."""

    action: str
    args: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Everything the subagent loop needs to run one executable tool.

    Keeping the executor, budget source, metadata key, and UI labels together
    means adding a tool is one registry entry — the loop, budget check, event
    stream, and result metadata stay in sync automatically.
    """

    action: str
    # AgentContext attribute holding this tool's per-run budget.
    budget_attr: str
    # Per-tool usage key written into the subagent result metadata.
    metadata_key: str
    # directive.args key surfaced in the Architect event, or None (e.g. code).
    event_arg: str | None
    # Runs the directive and returns the prompt block to feed back to the LLM.
    executor: Callable[[ToolDirective], Awaitable[str]]
    # Human-readable one-liner for the live Architect stream.
    describe: Callable[[ToolDirective, bool], str]


async def _run_web_search(directive: ToolDirective) -> str:
    query = directive.args["query"]
    results = await web_search_service.search(
        query, category=directive.args["category"]
    )
    return web_search_service.format_results_block(query, results)


async def _run_data_fetch(directive: ToolDirective) -> str:
    return await data_fetch_service.fetch(directive.args["url"])


async def _run_code_execution(directive: ToolDirective) -> str:
    result = await code_execution_service.run_python(directive.args["code"])
    return code_execution_service.format_execution_block(result)


def _describe_web_search(directive: ToolDirective, done: bool) -> str:
    target = directive.args["query"]
    return f"Web search done: {target}" if done else f"Searching the web: {target}"


def _describe_data_fetch(directive: ToolDirective, done: bool) -> str:
    target = directive.args["url"]
    return f"Fetched: {target}" if done else f"Fetching: {target}"


def _describe_code_execution(directive: ToolDirective, done: bool) -> str:
    # Never surface the full code in events; the first line is enough context.
    preview = directive.args.get("code", "").splitlines()[0][
        :CODE_EXECUTION_PREVIEW_MAX_CHARS
    ]
    return (
        f"Sandbox run finished ({preview})"
        if done
        else f"Running code in sandbox ({preview})"
    )


def _describe_view_original_request(directive: ToolDirective, done: bool) -> str:
    return (
        "Read the original user request"
        if done
        else "Reading the original user request"
    )


def make_view_original_request_spec(objective: str) -> ToolSpec:
    """Per-run spec for the built-in directive: the executor closes over this
    run's original user request, since ``TOOL_SPECS`` executors are stateless.
    """

    async def _run(directive: ToolDirective) -> str:
        body = truncate_text(objective.strip(), OBJECTIVE_MAX_CHARS)
        return (
            f"{ORIGINAL_REQUEST_OPEN}\n{body}\n{ORIGINAL_REQUEST_CLOSE}\n"
            "Execute only the part of it relevant to your brief."
        )

    return ToolSpec(
        action=VIEW_ORIGINAL_REQUEST_ACTION,
        budget_attr="max_original_request_views",
        metadata_key="original_request_views",
        event_arg=None,
        executor=_run,
        describe=_describe_view_original_request,
    )


# The registry: one entry per executable tool (keys == EXECUTABLE_TOOL_IDS).
TOOL_SPECS: dict[str, ToolSpec] = {
    WEB_SEARCH_ACTION: ToolSpec(
        action=WEB_SEARCH_ACTION,
        budget_attr="max_web_searches",
        metadata_key="searches_used",
        event_arg="query",
        executor=_run_web_search,
        describe=_describe_web_search,
    ),
    DATA_FETCH_ACTION: ToolSpec(
        action=DATA_FETCH_ACTION,
        budget_attr="max_data_fetches",
        metadata_key="fetches_used",
        event_arg="url",
        executor=_run_data_fetch,
        describe=_describe_data_fetch,
    ),
    CODE_EXECUTION_ACTION: ToolSpec(
        action=CODE_EXECUTION_ACTION,
        budget_attr="max_code_executions",
        metadata_key="executions_used",
        event_arg=None,
        executor=_run_code_execution,
        describe=_describe_code_execution,
    ),
}


def parse_directive(content: str, enabled: frozenset[str]) -> ToolDirective | None:
    """Parse a reply as a tool directive, or None if it is a final answer.

    Only exact known ``action`` values with their required argument qualify —
    a JSON-shaped deliverable (e.g. from the data domain) must not be
    mistaken for a tool call.
    """
    try:
        parsed = extract_json(content)
    except ValueError:
        return None
    action = str(parsed.get("action", "")).strip()
    if action not in enabled:
        return None

    if action == VIEW_ORIGINAL_REQUEST_ACTION:
        return ToolDirective(action)

    if action == WEB_SEARCH_ACTION:
        query = str(parsed.get("query", "")).strip()
        if not query:
            return None
        category = (
            str(parsed.get("category", WEB_SEARCH_DEFAULT_CATEGORY)).strip().lower()
        )
        if category not in WEB_SEARCH_CATEGORIES:
            category = WEB_SEARCH_DEFAULT_CATEGORY
        return ToolDirective(action, {"query": query, "category": category})

    if action == DATA_FETCH_ACTION:
        url = str(parsed.get("url", "")).strip()
        if not url:
            return None
        return ToolDirective(action, {"url": url})

    if action == CODE_EXECUTION_ACTION:
        code = str(parsed.get("code", "")).strip()
        if not code:
            return None
        return ToolDirective(action, {"code": code})

    return None


async def resolve_enabled_tools(domain: str) -> frozenset[str]:
    """Executable tools this domain may use, filtered by runtime switches."""
    declared = set(get_domain_info(domain).tools) & EXECUTABLE_TOOL_IDS
    if not settings.web_search_enabled:
        declared.discard(WEB_SEARCH_ACTION)
    if not settings.data_fetch_enabled:
        declared.discard(DATA_FETCH_ACTION)
    if CODE_EXECUTION_ACTION in declared and not (
        settings.code_execution_enabled and await code_execution_service.is_available()
    ):
        declared.discard(CODE_EXECUTION_ACTION)
    return frozenset(declared)
