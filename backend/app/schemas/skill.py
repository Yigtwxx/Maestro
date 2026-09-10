"""Schemas for agent skills: reusable, versioned instruction bundles.

A skill is text a user (or a marketplace publisher, or a plugin) wrote that ends
up verbatim inside a subagent's *system prompt*. That makes this file a security
boundary in the same sense as ``schemas/custom_api_tool``, but against a
different threat: there is no outbound request to guard, only prompt injection.
Two rules follow from it.

* ``name`` and ``description`` are collapsed to a single line at write time. A
  newline in either would let a skill open a new instruction line in the agent
  that attaches it, which is the whole trick.
* Lengths are capped tightly. The cap is not politeness — ``SKILLS_PER_AGENT_MAX``
  bundles at ``SKILL_INSTRUCTIONS_MAX_CHARS`` each is already a large share of a
  small local model's context window, and Ollama drops the *front* of an
  over-long prompt, taking the member's role and output contract with it.

``required_tools`` is advisory and is filtered rather than rejected: a skill
published against a catalog that later loses a tool should keep working with one
fewer declared requirement, exactly as ``marketplace_service.publish`` filters a
published agent's tool list instead of refusing the publish.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import (
    SKILL_DESCRIPTION_MAX_CHARS,
    SKILL_INSTRUCTIONS_MAX_CHARS,
    SKILL_NAME_MAX_CHARS,
    SKILL_OUTPUT_FORMAT_MAX_CHARS,
    SKILL_SLUG_PATTERN,
    TOOL_IDS,
)


def _single_line(value: str) -> str:
    """Collapse a string to one line.

    Load-bearing, not cosmetic — see the module docstring. Mirrors
    ``custom_api_service._single_line``, which guards the same surface for a
    registered endpoint's name.
    """
    return " ".join(str(value).split())


def _known_tools(tools: list[str]) -> list[str]:
    """Drop unknown tool ids, de-duplicate, preserve order."""
    return list(dict.fromkeys(t for t in tools if t in TOOL_IDS))


class SkillCreate(BaseModel):
    """Payload to create a skill."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=SKILL_SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=SKILL_NAME_MAX_CHARS)
    description: str = Field(default="", max_length=SKILL_DESCRIPTION_MAX_CHARS)
    instructions: str = Field(min_length=1, max_length=SKILL_INSTRUCTIONS_MAX_CHARS)
    output_format: str = Field(default="", max_length=SKILL_OUTPUT_FORMAT_MAX_CHARS)
    # Advisory: the wizard warns when an attaching agent does not declare these.
    # Never widens an agent's tool set at runtime — see skill_service.
    required_tools: list[str] = Field(default_factory=list, max_length=len(TOOL_IDS))

    @field_validator("name", "description")
    @classmethod
    def _collapse(cls, value: str) -> str:
        return _single_line(value)

    @field_validator("required_tools")
    @classmethod
    def _filter_tools(cls, value: list[str]) -> list[str]:
        return _known_tools(value)


class SkillUpdate(BaseModel):
    """Partial update. Only the provided fields change."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None, min_length=1, max_length=SKILL_NAME_MAX_CHARS
    )
    description: str | None = Field(
        default=None, max_length=SKILL_DESCRIPTION_MAX_CHARS
    )
    instructions: str | None = Field(
        default=None, min_length=1, max_length=SKILL_INSTRUCTIONS_MAX_CHARS
    )
    output_format: str | None = Field(
        default=None, max_length=SKILL_OUTPUT_FORMAT_MAX_CHARS
    )
    required_tools: list[str] | None = Field(default=None, max_length=len(TOOL_IDS))

    @field_validator("name", "description")
    @classmethod
    def _collapse(cls, value: str | None) -> str | None:
        return None if value is None else _single_line(value)

    @field_validator("required_tools")
    @classmethod
    def _filter_tools(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _known_tools(value)


class SkillPublic(BaseModel):
    """A skill as returned to its owner.

    ``security_scan_passed`` is surfaced rather than kept internal because a
    skill that trips the scanner is silently withheld from every run
    (``skill_service.load_skills``). Without this field the user would see a
    skill attached in the wizard and never learn why it does nothing.
    """

    id: str
    slug: str
    name: str
    description: str
    instructions: str
    output_format: str = ""
    required_tools: list[str] = Field(default_factory=list)
    version: int = 1
    source: str = "custom"
    marketplace_item_id: str | None = None
    plugin_id: str | None = None
    security_scan_passed: bool = True
    created_at: datetime
    updated_at: datetime
