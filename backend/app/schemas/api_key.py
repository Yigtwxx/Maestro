"""BYOK API-key request/response schemas.

Responses expose only non-secret metadata (provider, label, hint) — never the
plaintext or encrypted key (CLAUDE.md §9.1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import LLMProvider


class ApiKeyCreate(BaseModel):
    provider: LLMProvider
    label: str = Field(min_length=1, max_length=120)
    key: str = Field(min_length=1, max_length=512, description="Plaintext secret")


class ApiKeyPublic(BaseModel):
    """Safe representation of a stored key (no secret material)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: LLMProvider
    label: str
    key_hint: str
    is_active: bool
    created_at: datetime
