"""Auth request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.constants import EMAIL_CODE_DIGITS, LLMProvider


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AccessTokenResponse(BaseModel):
    """The only token that crosses the wire in a body.

    The refresh half of the pair goes back as an httpOnly cookie and never
    reaches JavaScript (CLAUDE.md §9 rule 14).
    """

    access_token: str
    token_type: str = "bearer"


class TokenPair(BaseModel):
    """Service-internal: both halves, so the API layer can cookie one of them.

    Never a ``response_model``. ``auth_service`` deals in tokens; deciding that
    one of them travels as a cookie is a transport concern of the route.
    """

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


class VerifyEmailCodeRequest(BaseModel):
    """Redeem the numeric code from a verification email."""

    code: str = Field(
        min_length=EMAIL_CODE_DIGITS,
        max_length=EMAIL_CODE_DIGITS,
        pattern=r"^\d+$",
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Redeem an emailed password-reset link. Same password policy as register."""

    token: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class DetailResponse(BaseModel):
    """A human-readable outcome message (mirrors FastAPI's error shape)."""

    detail: str


# A login result is either an access token (with the refresh half set as a
# cookie) or an MFA challenge to complete.
LoginResult = AccessTokenResponse | MfaChallenge


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
    default_tracing_enabled: bool = False
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
