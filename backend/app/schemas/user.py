"""User profile / account management schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.constants import LLM_CHAT_PROVIDERS, LLMProvider


class UserUpdate(BaseModel):
    """Partial profile update; absent fields are left untouched.

    ``default_provider`` may be explicitly set to null to reset the default
    brain back to the free local tier (distinguish via ``model_fields_set``).
    """

    display_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    default_provider: LLMProvider | None = None

    @field_validator("default_provider")
    @classmethod
    def _validate_default_provider(
        cls, value: LLMProvider | None
    ) -> LLMProvider | None:
        """Only chat-capable providers can act as the default brain."""
        if value is not None and value not in LLM_CHAT_PROVIDERS:
            raise ValueError(f"Provider '{value.value}' cannot be used as a brain.")
        return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AccountDelete(BaseModel):
    """Password confirmation for a deletion request."""

    password: str = Field(min_length=1, max_length=128)


class AccountDeletionStatus(BaseModel):
    """When deletion was requested, and when it becomes irreversible."""

    deletion_requested_at: datetime
    purge_after: datetime
