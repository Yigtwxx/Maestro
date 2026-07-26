"""Task request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.registry import CUSTOM_DOMAIN_PREFIX, DOMAINS, is_custom_domain
from app.core.config import settings
from app.core.constants import LLMProvider, TaskStatus


class TaskCreate(BaseModel):
    """Payload to start a new orchestration task."""

    prompt: str = Field(min_length=1, max_length=8000)
    # User-selected domain agent; None means the orchestrator routes the task.
    domain: str | None = None
    # Which BYOK/local provider to use as the "brain". None falls back to the
    # user's default brain (users.default_provider), then to the local model.
    provider: LLMProvider | None = None
    # None falls back to the user's default (users.default_reviewer_enabled),
    # resolved in the start-task handler before the task runs.
    reviewer_enabled: bool | None = None
    # Human-in-the-loop: allow an agent to ask the user one clarifying question.
    allow_questions: bool = False
    # Record an execution trace (span waterfall, per-call tokens and cost).
    # None falls back to users.default_tracing_enabled, then to the server-wide
    # TRACING_ENABLED; resolved in the start-task handler before the task runs.
    tracing_enabled: bool | None = None
    max_iterations: int = Field(default=settings.max_iterations, ge=1, le=50)
    max_review_iterations: int = Field(
        default=settings.max_review_iterations, ge=0, le=10
    )
    # Optional per-role model pin, e.g. {"main": "claude-opus-4-8"}. Merged over
    # the user's saved model_preferences at task start; None = use tier defaults.
    model_overrides: dict[str, str] | None = None

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, value: str | None) -> str | None:
        """Reject unknown domains instead of silently falling back to general.

        A ``custom:{uuid}`` selector is accepted syntactically here; ownership is
        verified against the caller's agents in the task-start handler (Pydantic
        validators cannot do async DB reads).
        """
        if value is None:
            return None
        value = value.strip().lower()
        if is_custom_domain(value):
            agent_id = value[len(CUSTOM_DOMAIN_PREFIX) :]
            try:
                uuid.UUID(agent_id)
            except ValueError as exc:
                raise ValueError(f"Invalid custom agent id: {agent_id}") from exc
            return value
        if value not in DOMAINS:
            raise ValueError(f"Unknown domain: {value}")
        return value


class TaskCreated(BaseModel):
    task_id: str
    status: TaskStatus


class TaskAnswer(BaseModel):
    """A user's reply to an agent's clarifying question (human-in-the-loop)."""

    answer: str = Field(min_length=1, max_length=4000)


class TaskState(BaseModel):
    """Full task session state (mirrors the MongoDB document)."""

    model_config = ConfigDict(extra="ignore")

    task_id: str
    status: TaskStatus
    prompt: str
    domain: str | None = None
    # Needed to redraw the reviewer node when a past task is reopened.
    reviewer_enabled: bool = False
    result: Any | None = None
    error: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSummary(BaseModel):
    """One row of the task history list. Carries no `events`."""

    task_id: str
    status: TaskStatus
    # Truncated server-side (see `task_service.build_summary`).
    prompt: str
    domain: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    """A page of task summaries, newest first."""

    items: list[TaskSummary]
    total: int
    limit: int
    offset: int
