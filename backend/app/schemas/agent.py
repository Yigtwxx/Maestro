"""Agent configuration schemas (user-defined custom agents).

Custom agents live in MongoDB (``agent_configurations``) and carry a system
prompt plus a set of declared tools. System prompts are security-scanned on
write (CLAUDE.md §9.3).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentConfigCreate(BaseModel):
    """Payload to create a custom agent."""

    name: str = Field(min_length=1, max_length=80)
    domain: str = Field(min_length=1, max_length=40)
    system_prompt: str = Field(min_length=1, max_length=8000)
    tools: list[str] = Field(default_factory=list)
    # Metadata that shapes how the agent runs and whether the orchestrator may
    # auto-route to it (Backend v2 §4.3). All optional and backward-compatible.
    description: str = Field(default="", max_length=280)
    routing_hint: str = Field(default="", max_length=280)
    output_format: str = Field(default="", max_length=2000)
    routable: bool = False


class AgentConfigUpdate(BaseModel):
    """Partial update for a custom agent (only provided fields change)."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    domain: str | None = Field(default=None, min_length=1, max_length=40)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    tools: list[str] | None = None
    description: str | None = Field(default=None, max_length=280)
    routing_hint: str | None = Field(default=None, max_length=280)
    output_format: str | None = Field(default=None, max_length=2000)
    routable: bool | None = None


class SystemPromptUpdate(BaseModel):
    """Focused update of just an agent's system prompt."""

    system_prompt: str = Field(min_length=1, max_length=8000)


class AgentConfigPublic(BaseModel):
    """A user-defined custom agent."""

    id: str
    name: str
    domain: str
    system_prompt: str
    tools: list[str]
    description: str = ""
    routing_hint: str = ""
    output_format: str = ""
    routable: bool = False
    source: str = "custom"
    type: str = "custom"
    created_at: datetime
    updated_at: datetime
