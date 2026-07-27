"""Executable tool directives for the subagent loop.

Provider-agnostic by design: instead of native function calling, the model
replies with a small JSON object naming an action; we execute it and feed the
result back. This module parses those directives and resolves which tools a
domain may use at runtime.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.agents.registry import get_domain_info
from app.core.config import settings
from app.core.constants import (
    CODE_EXECUTION_ACTION,
    CODE_EXECUTION_PREVIEW_MAX_CHARS,
    COMMUNITY_PLATFORMS,
    COMMUNITY_READ_ACTION,
    CONNECTED_DEFAULT_WINDOW,
    CONNECTED_TOOL_IDS,
    CONNECTED_TOOL_PROVIDERS,
    CONNECTED_WINDOWS,
    DATA_FETCH_ACTION,
    DATA_FETCH_SELECTOR_MAX_CHARS,
    DOCUMENT_SEARCH_ACTION,
    DOCUMENT_SEARCH_RESULTS_CLOSE,
    DOCUMENT_SEARCH_RESULTS_OPEN,
    EXECUTABLE_TOOL_IDS,
    KEYLESS_CONNECTED_TOOL_IDS,
    MEMORY_RECALL_ACTION,
    MEMORY_RECALL_RESULTS_CLOSE,
    MEMORY_RECALL_RESULTS_OPEN,
    OBJECTIVE_MAX_CHARS,
    ORIGINAL_REQUEST_CLOSE,
    ORIGINAL_REQUEST_OPEN,
    PLACES_INTEL_ACTION,
    PLACES_INTEL_ASPECTS,
    PLACES_INTEL_DEFAULT_ASPECT,
    QDRANT_CONVERSATION_MEMORIES,
    QDRANT_DOCUMENT_CHUNKS,
    REPO_INTEL_ACTION,
    REPO_INTEL_ASPECTS,
    REPO_INTEL_DEFAULT_ASPECT,
    REQUEST_TOOL_ACTION,
    SOCIAL_SEARCH_ACTION,
    VIEW_ORIGINAL_REQUEST_ACTION,
    WEB_SEARCH_ACTION,
    WEB_SEARCH_CATEGORIES,
    WEB_SEARCH_DEFAULT_CATEGORY,
)
from app.services import (
    code_execution_service,
    community_read_service,
    data_fetch_service,
    memory_service,
    places_intel_service,
    repo_intel_service,
    social_search_service,
    web_search_service,
)
from app.services.service_key_service import ServiceCredentials

from .base import extract_json, truncate_text


@dataclass(slots=True)
class ToolDirective:
    """One parsed tool request from the model."""

    action: str
    args: dict[str, str] = field(default_factory=dict)


# args stays str-valued (it feeds the Architect event payload verbatim), so
# booleans travel as this sentinel. Models emit true/"true"/"yes"/1
# interchangeably, hence the permissive read.
_RENDER_TRUE = "true"
_TRUTHY = frozenset({"true", "yes", "1", "on"})


def _as_bool(value: object) -> bool:
    """Coerce a model-supplied flag to a bool without trusting its type."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY


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
    # Which BYOK service this call authenticates against, for the Architect
    # rail. None for the keyless tools (web_search, data_fetch, code_execution),
    # which deliberately get no lane. A callable rather than a constant because
    # community_read's provider is chosen per call by its ``platform`` argument.
    provider_of: Callable[[ToolDirective], str | None] | None = None


async def _run_web_search(directive: ToolDirective) -> str:
    outcome = await web_search_service.search(
        directive.args["query"], category=directive.args["category"]
    )
    return web_search_service.format_results_block(outcome)


async def _run_data_fetch(directive: ToolDirective) -> str:
    return await data_fetch_service.fetch(
        directive.args["url"],
        selector=directive.args.get("selector") or None,
        render=directive.args.get("render") == _RENDER_TRUE,
    )


async def _run_code_execution(directive: ToolDirective) -> str:
    result = await code_execution_service.run_python(directive.args["code"])
    return code_execution_service.format_execution_block(result)


def _describe_web_search(directive: ToolDirective, done: bool) -> str:
    target = directive.args["query"]
    return f"Web search done: {target}" if done else f"Searching the web: {target}"


def _describe_data_fetch(directive: ToolDirective, done: bool) -> str:
    target = directive.args["url"]
    # Safe to interpolate: parse_directive caps the selector's length and
    # rejects newlines before it ever reaches an event payload.
    selector = directive.args.get("selector")
    suffix = f" [{selector}]" if selector else ""
    return f"Fetched: {target}{suffix}" if done else f"Fetching: {target}{suffix}"


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


def _describe_repo_intel(directive: ToolDirective, done: bool) -> str:
    target = f"{directive.args['repo']} ({directive.args['aspect']})"
    return f"Repo read: {target}" if done else f"Reading repo: {target}"


def _describe_social_search(directive: ToolDirective, done: bool) -> str:
    target = f"{directive.args['query']} ({directive.args['window']})"
    return f"Social search done: {target}" if done else f"Searching X: {target}"


def _describe_community_read(directive: ToolDirective, done: bool) -> str:
    target = f"{directive.args['platform']}/{directive.args['channel']}"
    return f"Community read: {target}" if done else f"Reading community: {target}"


def _describe_places_intel(directive: ToolDirective, done: bool) -> str:
    target = f"{directive.args['query']} ({directive.args['aspect']})"
    return f"Places read: {target}" if done else f"Reading places: {target}"


def _describe_document_search(directive: ToolDirective, done: bool) -> str:
    query = directive.args["query"]
    return f"Document search done: {query}" if done else f"Searching documents: {query}"


def _describe_memory_recall(directive: ToolDirective, done: bool) -> str:
    query = directive.args["query"]
    return f"Memory recall done: {query}" if done else f"Recalling memory: {query}"


def make_rag_tool_specs(user_id: uuid.UUID) -> dict[str, ToolSpec]:
    """Per-run specs for the RAG tools, closing over this user's id.

    Like the connected specs, these cannot live in the process-wide
    ``TOOL_SPECS``: their executors need the run's ``user_id`` to scope every
    Qdrant query to that user's own data — the load-bearing per-user isolation
    invariant (CLAUDE.md §6). Keyless, so ``provider_of`` is None and they draw
    no Architect rail lane. Both degrade to a "no results" note on a cold Qdrant
    (``memory_service.retrieve_memories`` never raises), so they never block a run.
    """

    async def _run_document_search(directive: ToolDirective) -> str:
        hits = await memory_service.retrieve_memories(
            user_id, directive.args["query"], collection=QDRANT_DOCUMENT_CHUNKS
        )
        return memory_service.format_rag_block(
            hits,
            open_tag=DOCUMENT_SEARCH_RESULTS_OPEN,
            close_tag=DOCUMENT_SEARCH_RESULTS_CLOSE,
        )

    async def _run_memory_recall(directive: ToolDirective) -> str:
        hits = await memory_service.retrieve_memories(
            user_id, directive.args["query"], collection=QDRANT_CONVERSATION_MEMORIES
        )
        return memory_service.format_rag_block(
            hits,
            open_tag=MEMORY_RECALL_RESULTS_OPEN,
            close_tag=MEMORY_RECALL_RESULTS_CLOSE,
        )

    return {
        DOCUMENT_SEARCH_ACTION: ToolSpec(
            action=DOCUMENT_SEARCH_ACTION,
            budget_attr="max_document_searches",
            metadata_key="document_searches_used",
            event_arg="query",
            executor=_run_document_search,
            describe=_describe_document_search,
        ),
        MEMORY_RECALL_ACTION: ToolSpec(
            action=MEMORY_RECALL_ACTION,
            budget_attr="max_memory_recalls",
            metadata_key="memory_recalls_used",
            event_arg="query",
            executor=_run_memory_recall,
            describe=_describe_memory_recall,
        ),
    }


def make_connected_tool_specs(credentials: ServiceCredentials) -> dict[str, ToolSpec]:
    """Per-run specs for the tools that authenticate with a user's BYOK key.

    They cannot live in the process-wide ``TOOL_SPECS`` because their executors
    need this run's credentials, and ``ToolSpec.executor`` takes only a
    directive. Closing over the credentials is the same seam
    :func:`make_view_original_request_spec` already uses for run-scoped state,
    and it keeps decryption at the engine edge instead of inside the agent loop.
    """

    async def _run_repo_intel(directive: ToolDirective) -> str:
        return await repo_intel_service.fetch(
            directive.args["repo"],
            aspect=directive.args["aspect"],
            credentials=credentials,
        )

    async def _run_social_search(directive: ToolDirective) -> str:
        return await social_search_service.fetch(
            directive.args["query"],
            window=directive.args["window"],
            credentials=credentials,
        )

    async def _run_community_read(directive: ToolDirective) -> str:
        return await community_read_service.fetch(
            directive.args["channel"],
            platform=directive.args["platform"],
            window=directive.args["window"],
            credentials=credentials,
        )

    async def _run_places_intel(directive: ToolDirective) -> str:
        return await places_intel_service.fetch(
            directive.args["query"],
            location=directive.args.get("location", ""),
            aspect=directive.args["aspect"],
            credentials=credentials,
        )

    return {
        REPO_INTEL_ACTION: ToolSpec(
            action=REPO_INTEL_ACTION,
            budget_attr="max_repo_lookups",
            metadata_key="repo_lookups_used",
            event_arg="repo",
            executor=_run_repo_intel,
            describe=_describe_repo_intel,
            provider_of=lambda _: CONNECTED_TOOL_PROVIDERS[REPO_INTEL_ACTION].value,
        ),
        SOCIAL_SEARCH_ACTION: ToolSpec(
            action=SOCIAL_SEARCH_ACTION,
            budget_attr="max_social_searches",
            metadata_key="social_searches_used",
            event_arg="query",
            executor=_run_social_search,
            describe=_describe_social_search,
            provider_of=lambda _: CONNECTED_TOOL_PROVIDERS[SOCIAL_SEARCH_ACTION].value,
        ),
        COMMUNITY_READ_ACTION: ToolSpec(
            action=COMMUNITY_READ_ACTION,
            budget_attr="max_community_reads",
            metadata_key="community_reads_used",
            event_arg="channel",
            executor=_run_community_read,
            describe=_describe_community_read,
            # The platform argument *is* the provider here, which is why this
            # field is a callable rather than a constant.
            provider_of=lambda d: d.args.get("platform"),
        ),
        PLACES_INTEL_ACTION: ToolSpec(
            action=PLACES_INTEL_ACTION,
            budget_attr="max_places_lookups",
            metadata_key="places_lookups_used",
            event_arg="query",
            executor=_run_places_intel,
            describe=_describe_places_intel,
            provider_of=lambda _: CONNECTED_TOOL_PROVIDERS[PLACES_INTEL_ACTION].value,
        ),
    }


def specs_for(
    enabled: frozenset[str],
    credentials: ServiceCredentials,
    user_id: uuid.UUID | None = None,
) -> dict[str, ToolSpec]:
    """Assemble one run's specs: stateless built-ins plus per-run ones.

    The single place the three registries are merged, so the subagent loop never
    has to know that some specs are process-wide (``TOOL_SPECS``), some close
    over BYOK credentials (connected), and some close over the user's id (RAG).
    RAG specs are only built when ``user_id`` is known; without it those actions
    resolve to nothing and are dropped, so a run with no user id simply has no
    RAG tools.
    """
    connected = make_connected_tool_specs(credentials)
    rag = make_rag_tool_specs(user_id) if user_id is not None else {}
    per_run = {**connected, **rag}
    return {
        action: TOOL_SPECS[action] if action in TOOL_SPECS else per_run[action]
        for action in enabled
        if action in TOOL_SPECS or action in per_run
    }


# The registry: stateless executable tools. The credentialed ones are built
# per run by ``make_connected_tool_specs`` and merged in by ``specs_for``.
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

    # Recognized before the ``enabled`` gate: by definition a member asks for a
    # tool it does *not* currently have, so this action is never in ``enabled``.
    # An unknown or non-executable ``tool`` degrades to None (final answer)
    # rather than a dead directive.
    if action == REQUEST_TOOL_ACTION:
        tool = str(parsed.get("tool", "")).strip()
        if tool not in EXECUTABLE_TOOL_IDS:
            return None
        justification = str(parsed.get("justification", "")).strip()
        return ToolDirective(action, {"tool": tool, "justification": justification})

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
        args = {"url": url}
        # A malformed selector degrades the call to a full-text fetch rather
        # than killing the directive: returning None here would make the loop
        # read this JSON as the subagent's final answer, which is strictly worse.
        selector = str(parsed.get("selector", "")).strip()
        if (
            selector
            and len(selector) <= DATA_FETCH_SELECTOR_MAX_CHARS
            and "\n" not in selector
        ):
            args["selector"] = selector
        if _as_bool(parsed.get("render")):
            args["render"] = _RENDER_TRUE
        return ToolDirective(action, args)

    if action == CODE_EXECUTION_ACTION:
        code = str(parsed.get("code", "")).strip()
        if not code:
            return None
        return ToolDirective(action, {"code": code})

    if action == REPO_INTEL_ACTION:
        repo = str(parsed.get("repo", "")).strip()
        if not repo:
            return None
        # Like data_fetch's selector, a bad optional arg degrades to the default
        # rather than returning None, which the loop would read as a final answer.
        aspect = str(parsed.get("aspect", "")).strip().lower()
        if aspect not in REPO_INTEL_ASPECTS:
            aspect = REPO_INTEL_DEFAULT_ASPECT
        return ToolDirective(action, {"repo": repo, "aspect": aspect})

    if action == SOCIAL_SEARCH_ACTION:
        query = str(parsed.get("query", "")).strip()
        if not query:
            return None
        return ToolDirective(
            action, {"query": query, "window": _window_arg(parsed.get("window"))}
        )

    if action == COMMUNITY_READ_ACTION:
        channel = str(parsed.get("channel", "")).strip()
        platform = str(parsed.get("platform", "")).strip().lower()
        # Both are required: unlike an aspect there is no safe default platform,
        # and guessing one would read the wrong community.
        if not channel or platform not in COMMUNITY_PLATFORMS:
            return None
        return ToolDirective(
            action,
            {
                "channel": channel,
                "platform": platform,
                "window": _window_arg(parsed.get("window")),
            },
        )

    if action == PLACES_INTEL_ACTION:
        query = str(parsed.get("query", "")).strip()
        if not query:
            return None
        aspect = str(parsed.get("aspect", "")).strip().lower()
        if aspect not in PLACES_INTEL_ASPECTS:
            aspect = PLACES_INTEL_DEFAULT_ASPECT
        args = {"query": query, "aspect": aspect}
        location = str(parsed.get("location", "")).strip()
        if location:
            args["location"] = location
        return ToolDirective(action, args)

    return None


def _window_arg(raw: object) -> str:
    """Normalize a model-supplied lookback window to a supported value."""
    window = str(raw or "").strip().lower()
    return window if window in CONNECTED_WINDOWS else CONNECTED_DEFAULT_WINDOW


def _connected_is_usable(action: str, credentials: ServiceCredentials) -> bool:
    """Whether a connected tool has what it needs to do anything at all.

    ``repo_intel`` is usable with no key (GitHub serves anonymous reads), so it
    stays enabled either way. The rest are dropped when their credential is
    missing, for the same reason ``code_execution`` is dropped without Docker:
    offering a tool that cannot work guarantees a wasted tool call. The subagent
    then works from ``web_search`` and reports the gap in its Data coverage.
    """
    if action in KEYLESS_CONNECTED_TOOL_IDS:
        return True
    if action == COMMUNITY_READ_ACTION:
        # Any one of the three platforms is enough to make the tool worth having.
        return any(credentials.has(platform) for platform in COMMUNITY_PLATFORMS)
    provider = CONNECTED_TOOL_PROVIDERS.get(action)
    return provider is not None and credentials.has(provider)


async def resolve_enabled_tools(
    domain: str,
    *,
    credentials: ServiceCredentials | None = None,
    assigned: frozenset[str] | None = None,
) -> frozenset[str]:
    """Executable tools this domain may use, filtered by runtime switches.

    ``assigned`` is the Main Agent's per-subagent grant. ``None`` means no
    assignment — the member gets the full domain-global set, preserving the
    pre-assignment behaviour. When set, it intersects the domain universe
    *before* the operator switch and credential gates below, so an assignment
    can only ever *narrow* the set: a member can never enable a tool the domain
    does not declare, the operator disabled, or the user has no key for.
    """
    declared = set(get_domain_info(domain).tools) & EXECUTABLE_TOOL_IDS
    if assigned is not None:
        declared &= assigned
    if not settings.web_search_enabled:
        declared.discard(WEB_SEARCH_ACTION)
    # Deliberately no browser-availability probe here, unlike code_execution
    # below. Without Docker, code_execution can do nothing at all, so offering
    # it guarantees a wasted tool call. data_fetch's baseline is
    # TLS-impersonating HTTP, which works on every image; the browser is an
    # optional accelerator for JS-heavy pages. Gating the whole tool on a
    # browser probe would delete a working capability from every domain on a
    # browser-free host. The probe lives inside the service, where a missing
    # browser silently degrades to the static tier.
    if not settings.data_fetch_enabled:
        declared.discard(DATA_FETCH_ACTION)
    # RAG tools are keyless and per-user; only an operator switch gates them. No
    # availability probe: a cold Qdrant is a graceful empty result, not a failure
    # (unlike code_execution below, which can do nothing without Docker).
    if not settings.document_search_enabled:
        declared.discard(DOCUMENT_SEARCH_ACTION)
    if not settings.memory_recall_enabled:
        declared.discard(MEMORY_RECALL_ACTION)
    if CODE_EXECUTION_ACTION in declared and not (
        settings.code_execution_enabled and await code_execution_service.is_available()
    ):
        declared.discard(CODE_EXECUTION_ACTION)

    # Connected-API tools: an operator switch, then a credential check.
    creds = credentials if credentials is not None else ServiceCredentials()
    for action in list(declared & CONNECTED_TOOL_IDS):
        if not getattr(settings, f"{action}_enabled", True):
            declared.discard(action)
        elif not _connected_is_usable(action, creds):
            declared.discard(action)
    return frozenset(declared)


# --- ToolProvider seam (Backend v2 §4.4) ----------------------------------
# An indirection over where tool specs come from, so a future MCP/plugin source
# can supply tools without touching the subagent loop. Only the built-in
# provider exists today; the loop resolves specs through this interface.


class ToolProvider(Protocol):
    """Supplies the executable tool specs available to a subagent run."""

    def specs(self) -> dict[str, ToolSpec]: ...


class BuiltinToolProvider:
    """The default provider: the process-wide built-in ``TOOL_SPECS``."""

    def specs(self) -> dict[str, ToolSpec]:
        return TOOL_SPECS


builtin_tool_provider: ToolProvider = BuiltinToolProvider()

# JSON-schema parameter shapes for native function calling, one per tool. Mirrors
# the directive args each executor already expects.
_TOOL_PARAMETERS: dict[str, dict] = {
    WEB_SEARCH_ACTION: {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "category": {"type": "string", "enum": sorted(WEB_SEARCH_CATEGORIES)},
        },
        "required": ["query"],
    },
    DATA_FETCH_ACTION: {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "selector": {
                "type": "string",
                "maxLength": DATA_FETCH_SELECTOR_MAX_CHARS,
                "description": (
                    "Optional CSS selector. When set, only the matching "
                    "elements are returned, as a compact JSON array."
                ),
            },
            "render": {
                "type": "boolean",
                "description": (
                    "Render JavaScript in a real browser. Slow, and ignored "
                    "when no browser is installed on the server."
                ),
            },
        },
        "required": ["url"],
    },
    CODE_EXECUTION_ACTION: {
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    },
    REPO_INTEL_ACTION: {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": (
                    'Repository as "owner/name", exactly as it appears in the '
                    'project\'s GitHub URL, e.g. "psf/requests". The owner '
                    "cannot be derived from a package name — look it up rather "
                    "than assembling one."
                ),
            },
            "aspect": {
                "type": "string",
                "enum": sorted(REPO_INTEL_ASPECTS),
                "description": (
                    "Which facts to return: profile (identity, license, "
                    "counts), activity (commits, contributors), issues "
                    "(backlog), releases (cadence)."
                ),
            },
        },
        "required": ["repo"],
    },
    SOCIAL_SEARCH_ACTION: {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "window": {"type": "string", "enum": sorted(CONNECTED_WINDOWS)},
        },
        "required": ["query"],
    },
    COMMUNITY_READ_ACTION: {
        "type": "object",
        "properties": {
            "platform": {"type": "string", "enum": sorted(COMMUNITY_PLATFORMS)},
            "channel": {
                "type": "string",
                "description": (
                    "Channel identifier: a Discord or Slack channel id, or a "
                    'Telegram "@name" or numeric chat id.'
                ),
            },
            "window": {"type": "string", "enum": sorted(CONNECTED_WINDOWS)},
        },
        "required": ["platform", "channel"],
    },
    PLACES_INTEL_ACTION: {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What kind of place to find."},
            "location": {
                "type": "string",
                "description": "City, district or area to search within.",
            },
            "aspect": {
                "type": "string",
                "enum": sorted(PLACES_INTEL_ASPECTS),
                "description": (
                    "search returns places with ratings and price level; "
                    "reviews returns review text for theme mining."
                ),
            },
        },
        "required": ["query"],
    },
    DOCUMENT_SEARCH_ACTION: {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    MEMORY_RECALL_ACTION: {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    VIEW_ORIGINAL_REQUEST_ACTION: {"type": "object", "properties": {}},
}

_TOOL_DESCRIPTIONS: dict[str, str] = {
    WEB_SEARCH_ACTION: "Search the web for up-to-date information.",
    DATA_FETCH_ACTION: (
        "Fetch a URL and return its readable text. Pass a CSS selector to get "
        "just the matching elements as a JSON array instead of the whole page."
    ),
    CODE_EXECUTION_ACTION: "Run Python code in a sandbox and return its output.",
    REPO_INTEL_ACTION: (
        "Read structured facts about a GitHub repository — health, activity, "
        "issue backlog and release cadence — one aspect per call."
    ),
    SOCIAL_SEARCH_ACTION: (
        "Search recent public posts on X, with author, timestamp and "
        "engagement counts for each, so you can measure rather than guess."
    ),
    COMMUNITY_READ_ACTION: (
        "Read recent messages from a Discord, Slack or Telegram channel the "
        "user has connected."
    ),
    PLACES_INTEL_ACTION: (
        "Find places in an area with their ratings, review counts and price "
        "level, or read their reviews for complaint and theme mining."
    ),
    DOCUMENT_SEARCH_ACTION: (
        "Search the user's own uploaded documents for passages relevant to a "
        "query, returned as a list of matching excerpts."
    ),
    MEMORY_RECALL_ACTION: (
        "Recall relevant snippets from the user's past conversations for a query."
    ),
    VIEW_ORIGINAL_REQUEST_ACTION: "Read the original user request for context.",
}


def tool_defs_for(specs: dict[str, ToolSpec]) -> list:
    """Build native-function-calling ``ToolDef``s from the enabled specs.

    Imported lazily to avoid a hard dependency on the LLM service at module load.
    """
    from app.services.llm_service import ToolDef

    return [
        ToolDef(
            name=action,
            description=_TOOL_DESCRIPTIONS.get(action, action),
            parameters=_TOOL_PARAMETERS.get(
                action, {"type": "object", "properties": {}}
            ),
        )
        for action in specs
    ]


def request_tool_def(grantable: frozenset[str]):
    """Native ``ToolDef`` for the escalation directive, or None when nothing is
    grantable. The ``tool`` enum is the grantable pool, so a native model cannot
    even name a tool the assignment/domain/credential gates would refuse."""
    if not grantable:
        return None
    from app.services.llm_service import ToolDef

    return ToolDef(
        name=REQUEST_TOOL_ACTION,
        description=(
            "Ask the Main Agent to grant you a tool you were not given, when "
            "your brief needs one you do not currently have. Say why in "
            "'justification'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "tool": {"type": "string", "enum": sorted(grantable)},
                "justification": {"type": "string"},
            },
            "required": ["tool", "justification"],
        },
    )
