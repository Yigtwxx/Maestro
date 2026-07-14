"""BYOK API-key request/response schemas.

Responses expose only non-secret metadata (provider, label, hint) — never the
plaintext or encrypted key (CLAUDE.md §9.1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.constants import LLM_CHAT_PROVIDERS, LLMProvider
from app.utils.url_guard import validate_url_shape


class ApiKeyCreate(BaseModel):
    provider: LLMProvider
    label: str = Field(min_length=1, max_length=120)
    key: str = Field(min_length=1, max_length=512, description="Plaintext secret")
    # base_url: only the custom OpenAI-compatible provider (its endpoint).
    base_url: str | None = Field(default=None, max_length=512)
    # model: required for custom; an optional override for any other chat
    # provider (BYOK users pick which model their key runs — e.g. a Gemini key
    # set to "gemini-2.5-pro"). Empty -> the provider's built-in default.
    model: str | None = Field(default=None, max_length=120)

    @field_validator("key")
    @classmethod
    def _key_is_header_safe(cls, value: str) -> str:
        """Strip stray whitespace and reject non-ASCII keys at creation.

        The key becomes an HTTP auth header (``Authorization``/``x-api-key``); a
        mis-pasted non-Latin character otherwise crashes the LLM call at task
        time with a cryptic encoding error instead of failing here with a clear
        message.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("API key must not be blank.")
        if not stripped.isascii():
            raise ValueError(
                "API key must contain only ASCII characters "
                "(found a non-Latin character — check for a mis-paste)."
            )
        return stripped

    @model_validator(mode="after")
    def _check_custom_endpoint(self) -> ApiKeyCreate:
        """Endpoint/model rules per provider (custom, chat, service)."""
        if self.provider is LLMProvider.CUSTOM:
            if not self.base_url or not self.model:
                raise ValueError(
                    "A custom provider requires both 'base_url' and 'model'."
                )
            # Cheap synchronous shape check (scheme/credentials/host). The
            # private-address (SSRF) check needs DNS, so it runs async in the
            # create endpoint and again at request time (url_guard).
            reason = validate_url_shape(self.base_url)
            if reason is not None:
                raise ValueError(f"Invalid custom endpoint URL: {reason}")
        else:
            if self.base_url is not None:
                raise ValueError("'base_url' is only allowed for the custom provider.")
            if self.model is not None and self.provider not in LLM_CHAT_PROVIDERS:
                raise ValueError("'model' is only allowed for chat providers.")
        return self


class ApiKeyPublic(BaseModel):
    """Safe representation of a stored key (no secret material)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: LLMProvider
    label: str
    key_hint: str
    is_active: bool
    created_at: datetime
    # Non-secret endpoint metadata: base_url only for custom keys; model for
    # custom (required) or any chat key with an explicit override (NULL otherwise).
    base_url: str | None = None
    model: str | None = None
