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


class MfaChallenge(BaseModel):
    """Returned by /login when the account has 2FA on: complete it via /login/totp."""

    mfa_required: bool = True
    mfa_token: str


class TotpVerifyRequest(BaseModel):
    """Second login step: the interim token plus a TOTP or recovery code."""

    mfa_token: str
    code: str = Field(min_length=6, max_length=14)


class VerifyEmailRequest(BaseModel):
    """Redeem an emailed verification link."""

    token: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Redeem an emailed password-reset link. Same password policy as register."""

    token: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class DetailResponse(BaseModel):
    """A human-readable outcome message (mirrors FastAPI's error shape)."""

    detail: str


# A login result is either a full token pair or an MFA challenge to complete.
LoginResult = TokenPair | MfaChallenge


class UserPublic(BaseModel):
    """User data safe to return to the client (no password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    # None means the account holds no subscription (fresh or never subscribed).
    subscription_tier: str | None
    # Default LLM "brain" for tasks; None means the local model (ollama).
    default_provider: LLMProvider | None = None
    # Per-role model pins ({"main": "claude-opus-4-8", ...}); None = tier
    # defaults.
    model_preferences: dict[str, str] | None = None
    # Profile personalization (client-rendered monogram avatar + short bio).
    bio: str | None = None
    avatar_color: str | None = None
    avatar_emoji: str | None = None
    # Account preferences.
    timezone: str | None = None
    default_reviewer_enabled: bool = False
    # Whether TOTP two-factor auth is active (never exposes the secret).
    two_factor_enabled: bool = False
    # Whether the emailed verification link was redeemed. While false, task
    # start and API-key creation are soft-gated (403).
    email_verified: bool = False
    # When the account was created ("member since" on the profile).
    created_at: datetime | None = None
    # Non-null means the account is locked and scheduled for purge. This is how
    # the client learns to show the locked screen instead of the app.
    deletion_requested_at: datetime | None = None
    # Authorization role ("user" | "admin"). The client reveals the admin
    # moderation surface only when this is "admin".
    role: str = "user"
    # Non-null means a moderator suspended the account; the client shows a
    # suspended screen instead of the product.
    suspended_at: datetime | None = None
