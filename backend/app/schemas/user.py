"""User profile / account management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.constants import (
    AVATAR_COLORS,
    AVATAR_EMOJI_MAX_LEN,
    BIO_MAX_LEN,
    LLM_CHAT_PROVIDERS,
    MODEL_NAME_MAX_LEN,
    MODEL_TIER_DEFAULTS,
    LLMProvider,
)


class UserUpdate(BaseModel):
    """Partial profile update; absent fields are left untouched.

    ``default_provider`` may be explicitly set to null to reset the default
    brain back to the local model (distinguish via ``model_fields_set``).
    ``bio``/``avatar_color``/``avatar_emoji`` may likewise be set to null to
    clear them.

    ``model_preferences`` is a whole-map replace (never a per-key merge):
    null or ``{}`` clears every per-role pin, an omitted field leaves the
    stored map untouched.
    """

    display_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    default_provider: LLMProvider | None = None
    bio: str | None = Field(default=None, max_length=BIO_MAX_LEN)
    avatar_color: str | None = Field(default=None, max_length=20)
    avatar_emoji: str | None = Field(default=None, max_length=AVATAR_EMOJI_MAX_LEN)
    timezone: str | None = Field(default=None, max_length=64)
    default_reviewer_enabled: bool | None = None
    default_tracing_enabled: bool | None = None
    model_preferences: dict[str, str] | None = None

    @field_validator("default_provider")
    @classmethod
    def _validate_default_provider(
        cls, value: LLMProvider | None
    ) -> LLMProvider | None:
        """Only chat-capable providers can act as the default brain."""
        if value is not None and value not in LLM_CHAT_PROVIDERS:
            raise ValueError(f"Provider '{value.value}' cannot be used as a brain.")
        return value

    @field_validator("model_preferences")
    @classmethod
    def _validate_model_preferences(
        cls, value: dict[str, str] | None
    ) -> dict[str, str] | None:
        """Per-role model pins. Unknown roles are rejected; blank values drop
        the entry (back to the tier default); an empty result clears the field.
        """
        if value is None:
            return None
        cleaned: dict[str, str] = {}
        for role, model in value.items():
            if role not in MODEL_TIER_DEFAULTS:
                raise ValueError(f"Unknown agent role '{role}'.")
            stripped = model.strip()
            if not stripped:
                continue
            if len(stripped) > MODEL_NAME_MAX_LEN:
                raise ValueError(f"Model name for '{role}' is too long.")
            cleaned[role] = stripped
        return cleaned or None

    @field_validator("avatar_color")
    @classmethod
    def _validate_avatar_color(cls, value: str | None) -> str | None:
        """Only palette keys the client can render are accepted."""
        if value is not None and value not in AVATAR_COLORS:
            raise ValueError(f"Unknown avatar color '{value}'.")
        return value

    @field_validator("bio", "avatar_emoji")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        """Treat an all-whitespace value as clearing the field."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        """Accept only a resolvable IANA timezone; empty clears it."""
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        try:
            ZoneInfo(stripped)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone '{stripped}'.") from exc
        return stripped


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    # Best-practice default: a password change signs out every other session.
    revoke_other_sessions: bool = True


class SessionInfo(BaseModel):
    """One active login session (a refresh-token family)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Human-readable device/browser summary parsed from the User-Agent.
    device: str
    ip: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    # True for the session making this request.
    current: bool = False


class TwoFactorSetup(BaseModel):
    """Enrollment payload: the secret to store plus a ready-to-scan QR."""

    secret: str
    otpauth_uri: str
    qr_svg: str


class TwoFactorEnable(BaseModel):
    """Confirm a pending TOTP setup with the current password + a code."""

    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=10)


class TwoFactorDisable(BaseModel):
    """Turn 2FA off. Requires the password; the code adds defence in depth."""

    password: str = Field(min_length=1, max_length=128)
    code: str | None = Field(default=None, max_length=10)


class RecoveryCodes(BaseModel):
    """One-time backup codes, returned only once when 2FA is enabled."""

    recovery_codes: list[str]


class AccountDelete(BaseModel):
    """Password confirmation for a deletion request."""

    password: str = Field(min_length=1, max_length=128)


class AccountDeletionStatus(BaseModel):
    """When deletion was requested, and when it becomes irreversible."""

    deletion_requested_at: datetime
    purge_after: datetime
