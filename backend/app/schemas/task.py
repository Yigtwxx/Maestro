"""Task request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.registry import DOMAINS
from app.core.config import settings
from app.core.constants import LLMProvider, TaskStatus


class TaskCreate(BaseModel):
    """Payload to start a new orchestration task."""

    prompt: str = Field(min_length=1, max_length=8000)
    # User-selected domain agent; None means the orchestrator routes the task.
    domain: str | None = None
    # Which BYOK/free provider to use as the "brain". None falls back to the
    # user's default brain (users.default_provider), then to the free tier.
    provider: LLMProvider | None = None
    reviewer_enabled: bool = False
    # Human-in-the-loop: allow an agent to ask the user one clarifying question.
    allow_questions: bool = False
    max_iterations: int = Field(default=settings.max_iterations, ge=1, le=50)
    max_review_iterations: int = Field(
        default=settings.max_review_iterations, ge=0, le=10
    )

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, value: str | None) -> str | None:
        """Reject unknown domains instead of silently falling back to general."""
        if value is None:
            return None
        value = value.strip().lower()
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
