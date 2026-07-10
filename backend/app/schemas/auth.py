"""Auth request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.constants import LLMProvider


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    """User data safe to return to the client (no password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    subscription_tier: str
    # Default LLM "brain" for tasks; None means the free local tier (ollama).
    default_provider: LLMProvider | None = None
    # Non-null means the account is locked and scheduled for purge. This is how
    # the client learns to show the locked screen instead of the app.
    deletion_requested_at: datetime | None = None
