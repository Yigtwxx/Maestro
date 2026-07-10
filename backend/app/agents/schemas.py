"""Pydantic models validating structured LLM outputs inside the agent layer.

Deliberately separate from ``app/schemas`` (the HTTP API layer): these models
describe what the *LLM* must return, not what the API exposes. All fields are
defaulted and extra keys ignored, so partially valid model output degrades
gracefully instead of failing hard; the existing fallback paths catch
``ValidationError`` because pydantic's ValidationError subclasses ValueError.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RouteDecision(BaseModel):
    """Orchestrator routing output: ``{"domain": ..., "reason": ...}``."""

    model_config = ConfigDict(extra="ignore")

    domain: str = ""
    reason: str = ""


class PlanAssignment(BaseModel):
    """One Main Agent team briefing.

    ``{"member": ..., "brief": ..., "depends_on": [...]}`` — ``depends_on``
    lists earlier members whose outputs this member needs (optional; older
    plans without it remain valid).
    """

    model_config = ConfigDict(extra="ignore")

    member: str = ""
    brief: str = ""
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("depends_on", mode="before")
    @classmethod
    def _coerce_depends_on(cls, value: object) -> object:
        """Accept a bare string or null — small models get this wrong."""
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        return value


class PlanResult(BaseModel):
    """Main Agent planning output: assignments or a clarifying question."""

    model_config = ConfigDict(extra="ignore")

    assignments: list[PlanAssignment] = Field(default_factory=list)
    question: str = ""


class ReviewVerdict(BaseModel):
    """Reviewer output: ``{"approved": ..., "issues": [...], "retry_hints": [...]}``."""

    model_config = ConfigDict(extra="ignore")

    approved: bool = False
    issues: list[str] = Field(default_factory=list)
    retry_hints: list[str] = Field(default_factory=list)
