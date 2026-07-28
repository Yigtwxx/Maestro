"""Agent configuration schemas (user-defined custom agents).

Custom agents live in MongoDB (``agent_configurations``) and carry a system
prompt plus a set of declared tools. System prompts are security-scanned on
write (CLAUDE.md §9.3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.constants import CUSTOM_API_TOOLS_PER_AGENT_MAX


class ToolCatalogEntry(BaseModel):
    """One declarable capability, with everything the wizard needs to explain it.

    ``kind`` separates the tools with a real runtime behind the directive loop
    from the ones the model performs natively in its reasoning — a distinction
    the previous ``{id, label}`` catalog left the UI unable to make, so every
    tool looked equally powerful.

    ``available`` is the operator switch; ``connected`` is whether *this* user
    holds the BYOK key. They are separate because the remedies differ: the first
    is the operator's to change, the second the user's.
    """

    id: str
    label: str
    description: str = ""
    kind: Literal["executable", "declarative", "custom_api"]
    # Plural: community_read authenticates against whichever of Discord, Slack
    # or Telegram the call names, so it has no single provider.
    providers: list[str] = Field(default_factory=list)
    keyless: bool = False
    connected: bool = True
    available: bool = True


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
    # Ids of the caller's own registered HTTP endpoints. Deliberately separate
    # from ``tools``: those are process-wide catalog ids, these are per-user
    # records, and mixing them would break _validate_tools, the marketplace
    # publish filter and the frontend parity tests at once.
    custom_api_tool_ids: list[str] = Field(
        default_factory=list, max_length=CUSTOM_API_TOOLS_PER_AGENT_MAX
    )


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
    custom_api_tool_ids: list[str] | None = Field(
        default=None, max_length=CUSTOM_API_TOOLS_PER_AGENT_MAX
    )


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
    custom_api_tool_ids: list[str] = Field(default_factory=list)
    source: str = "custom"
    type: str = "custom"
    created_at: datetime
    updated_at: datetime
