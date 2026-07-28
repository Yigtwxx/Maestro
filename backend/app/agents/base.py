"""Shared agent primitives: context, structured results, JSON helpers."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.agents.prompts import CURRENT_DATE_LINE
from app.core.constants import EventType, SubagentStatus
from app.services.custom_api_service import CustomApiTool
from app.services.llm_service import LLMAdapter
from app.services.service_key_service import ServiceCredentials

if TYPE_CHECKING:
    from app.agents.domains import DomainInfo
    from app.services.llm_service import AdapterPool

# Emit callback: (event_type, payload) -> awaitable. Wired by the task service
# to publish to the event bus and persist logs.
EmitFn = Callable[[EventType, dict[str, Any]], Awaitable[None]]

# Human-in-the-loop callback: (question) -> awaitable[answer]. Wired by the task
# service to a WebSocket/REST answer channel (CLAUDE.md §12).
AskFn = Callable[[str], Awaitable[str]]


async def _noop_emit(event_type: EventType, payload: dict[str, Any]) -> None:
    return None


@dataclass(slots=True)
class AgentContext:
    """Everything an agent needs to run one task."""

    adapter: LLMAdapter
    emit: EmitFn = _noop_emit
    max_iterations: int = 10
    max_review_iterations: int = 3
    # Retrieved RAG context (prior conversations + document chunks), already
    # filtered to the current user. Injected into agent prompts as grounding.
    memory_context: list[str] = field(default_factory=list)
    # Optional human-in-the-loop callback: (question) -> answer text.
    ask_user: AskFn | None = None
    allow_questions: bool = False
    # Per-tool budgets per subtask run (directive loop in subagent.py), plus
    # a total tool-call cap across all tools.
    max_web_searches: int = 3
    max_data_fetches: int = 3
    max_code_executions: int = 3
    # RAG tools over the user's own data (document uploads + conversation memory).
    max_document_searches: int = 3
    max_memory_recalls: int = 3
    # Connected-API tools (BYOK service keys). repo_intel gets a larger budget
    # because its aspects are deliberately separate calls — a member normally
    # needs two or three to say anything about a project.
    max_repo_lookups: int = 4
    max_social_searches: int = 3
    max_community_reads: int = 3
    max_places_lookups: int = 3
    max_tool_calls: int = 6
    # Budget for the built-in view_original_request directive; exempt from
    # max_tool_calls so it never crowds out real tools.
    max_original_request_views: int = 1
    # How many tools a subagent may be granted mid-run via ``request_tool``
    # escalation (Phase B). Read-only here on purpose: the running count and the
    # granted specs are kept LOCAL to ``_run_subtask``. A wave of sibling
    # subagents shares one AgentContext, so a grant recorded on ``ctx`` would
    # leak to every sibling — the exact bug the local-state design prevents.
    max_tool_grants: int = 2
    # Concurrent subagents per task (wave execution in main_agent.py).
    max_parallel_subagents: int = 3
    # Read-only RAG lookups the Main Agent may run before planning (Phase C).
    max_discovery_calls: int = 2
    # Resolved domain agent for this task. Set for a custom (``custom:{id}``)
    # agent — a one-member team adapted from the user's config; None means use
    # the built-in catalog by domain string (registry.resolve_domain_info).
    domain_info: DomainInfo | None = None
    # Task-scoped token budget (Backend v2 §4.6/D19). None means unbounded; when
    # set, the Main Agent stops launching new subagent waves once the metered
    # spend crosses it. Read from the wrapping TokenMeter's running total.
    token_budget: int | None = None
    # Per-role adapter pool (Backend v2 §4.4). When set, ``role_adapter`` hands
    # each agent role its own model (all sharing one token counter); when None,
    # every role uses ``adapter``. Kept off in unit tests (they pass ``adapter``).
    adapter_pool: AdapterPool | None = None
    # This user's decrypted BYOK service keys (X, GitHub, Maps, chat platforms),
    # resolved once at the engine edge like ``memory_context``. The default is
    # the empty set, which is the normal case: the connected tools are then
    # withheld and every squad falls back to web_search.
    service_credentials: ServiceCredentials = field(default_factory=ServiceCredentials)
    # This user's id, needed by the per-user RAG tools (document_search,
    # memory_recall) to scope every Qdrant query to their own data. Optional so
    # the many existing AgentContext(...) test constructors keep compiling; when
    # None, ``specs_for`` builds no RAG specs and those runs simply have no RAG
    # tools. The per-user isolation invariant (CLAUDE.md §6) rides on this value
    # reaching the executor — never a global default.
    user_id: uuid.UUID | None = None
    # This user's registered HTTP endpoints, loaded and decrypted at the engine
    # edge like ``service_credentials``. Empty is the normal case. The budget is
    # shared across them rather than per endpoint, which is what it looks like:
    # ``_tool_budget`` reads one attribute, but ``usage`` is keyed per action,
    # so each tool independently gets this many calls while ``max_tool_calls``
    # still bounds the total (CLAUDE.md §9.2).
    custom_api_tools: tuple[CustomApiTool, ...] = ()
    max_custom_api_calls: int = 3

    def role_adapter(self, role: str) -> LLMAdapter:
        """The adapter an agent role should use: its pooled per-role model when a
        pool is present, else the single ``adapter``."""
        if self.adapter_pool is not None:
            return self.adapter_pool.for_role(role)
        return self.adapter


def format_memory_block(items: list[str]) -> str:
    """Render retrieved memory as a promptable context block (empty if none)."""
    if not items:
        return ""
    joined = "\n".join(f"- {item.strip()}" for item in items if item.strip())
    if not joined:
        return ""
    return (
        f"Relevant context from the user's history (use only if helpful):\n{joined}\n"
    )


def format_optional_block(header: str, text: str) -> str:
    """Render an optional prompt section: empty text leaves no dangling header."""
    if not text.strip():
        return ""
    return f"\n{header}\n{text.strip()}\n"


_TRUNCATION_MARK = "\n...[truncated]"


def truncate_text(text: str, limit: int) -> str:
    """Cap ``text`` at ``limit`` characters, marking any cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATION_MARK


def with_current_date(system_prompt: str) -> str:
    """Prefix a system prompt with today's UTC date (grounds time-sensitive answers)."""
    date = datetime.now(UTC).date().isoformat()
    return CURRENT_DATE_LINE.format(date=date) + system_prompt


@dataclass(slots=True)
class SubagentResult:
    """Structured subagent output (CLAUDE.md §5.4)."""

    status: SubagentStatus
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "data": self.data,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ReviewResult:
    """Structured reviewer feedback (CLAUDE.md §5.4)."""

    approved: bool
    issues: list[str] = field(default_factory=list)
    retry_hints: list[str] = field(default_factory=list)
    # True when the reviewer itself failed and was auto-approved under the
    # "warn" fail mode — surfaced so the quality gate's silence is visible.
    review_skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "issues": self.issues,
            "retry_hints": self.retry_hints,
            "review_skipped": self.review_skipped,
        }


# Reasoning models (e.g. Qwen3) prefix answers with a <think>...</think> block.
_THINK_BLOCK = re.compile(r"^\s*<think>.*?</think>", re.DOTALL)
_FENCED_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _loads_dict(candidate: str) -> dict[str, Any] | None:
    """Parse ``candidate`` as JSON, returning it only if it is an object."""
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _balanced_objects(text: str) -> list[str]:
    """Yield balanced ``{...}`` substrings in order of appearance.

    String-aware: braces inside JSON string literals (including escaped
    quotes) do not affect the balance count.
    """
    candidates: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            if depth > 0:
                in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                candidates.append(text[start : index + 1])
    return candidates


def extract_json(text: str) -> dict[str, Any]:
    """Best-effort parse of a JSON object from an LLM response.

    Small models sometimes wrap JSON in prose, code fences, or a leading
    ``<think>`` block. Tries, in order: the whole text, fenced code blocks,
    then each balanced ``{...}`` substring in order of appearance (the first
    parseable object wins, matching the search-directive semantics in
    ``subagent._parse_search_directive``). Raises ValueError if none parses.
    """
    text = _THINK_BLOCK.sub("", text).strip()
    result = _loads_dict(text)
    if result is not None:
        return result
    for match in _FENCED_BLOCK.finditer(text):
        result = _loads_dict(match.group(1).strip())
        if result is not None:
            return result
    for candidate in _balanced_objects(text):
        result = _loads_dict(candidate)
        if result is not None:
            return result
    raise ValueError("No JSON object found in LLM output")
