"""Shared agent primitives: context, structured results, JSON helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agents.prompts import CURRENT_DATE_LINE
from app.core.constants import EventType, SubagentStatus
from app.services.llm_service import LLMAdapter

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
    # Web-search budget per subtask run (directive loop in subagent.py).
    max_web_searches: int = 2


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "issues": self.issues,
            "retry_hints": self.retry_hints,
        }


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Best-effort parse of a JSON object from an LLM response.

    Small models sometimes wrap JSON in prose or code fences; we extract the
    first balanced-looking object. Raises ValueError if none is found.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError("Could not parse JSON from LLM output") from exc
    raise ValueError("No JSON object found in LLM output")
