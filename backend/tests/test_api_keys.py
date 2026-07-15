"""Validation contract for the BYOK API-key create schema.

``base_url`` is exclusive to the custom OpenAI-compatible provider. ``model`` is
required for custom, an optional override for any other chat provider, and
forbidden for non-chat service providers.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.constants import LLMProvider
from app.schemas.api_key import ApiKeyCreate


def test_custom_requires_base_url_and_model():
    with pytest.raises(ValidationError):
        ApiKeyCreate(provider=LLMProvider.CUSTOM, label="My endpoint", key="sk-1")


def test_custom_with_endpoint_and_model_is_valid():
    payload = ApiKeyCreate(
        provider=LLMProvider.CUSTOM,
        label="My endpoint",
        key="sk-1",
        base_url="https://my-host/v1",
        model="llama-3.1-8b",
    )
    assert payload.base_url == "https://my-host/v1"
    assert payload.model == "llama-3.1-8b"


def test_custom_rejects_non_http_base_url():
    with pytest.raises(ValidationError):
        ApiKeyCreate(
            provider=LLMProvider.CUSTOM,
            label="Bad",
            key="sk-1",
            base_url="not-a-url",
            model="m",
        )


@pytest.mark.parametrize(
    "provider", [LLMProvider.OPENAI, LLMProvider.GROQ, LLMProvider.X]
)
def test_named_provider_forbids_endpoint_fields(provider: LLMProvider):
    with pytest.raises(ValidationError):
        ApiKeyCreate(
            provider=provider,
            label="Personal",
            key="sk-1",
            base_url="https://my-host/v1",
        )


@pytest.mark.parametrize(
    "provider", [LLMProvider.OPENAI, LLMProvider.ANTHROPIC, LLMProvider.GITHUB]
)
def test_named_provider_without_endpoint_is_valid(provider: LLMProvider):
    payload = ApiKeyCreate(provider=provider, label="Personal", key="sk-1")
    assert payload.base_url is None
    assert payload.model is None


@pytest.mark.parametrize(
    "provider,model",
    [
        (LLMProvider.GEMINI, "gemini-2.5-pro"),
        (LLMProvider.OPENAI, "gpt-4o"),
        (LLMProvider.ANTHROPIC, "claude-sonnet-5"),
    ],
)
def test_chat_provider_model_override_is_valid(provider: LLMProvider, model: str):
    payload = ApiKeyCreate(provider=provider, label="Personal", key="sk-1", model=model)
    assert payload.model == model
    assert payload.base_url is None


@pytest.mark.parametrize("provider", [LLMProvider.X, LLMProvider.GITHUB])
def test_service_provider_forbids_model(provider: LLMProvider):
    with pytest.raises(ValidationError):
        ApiKeyCreate(provider=provider, label="Personal", key="sk-1", model="whatever")


def test_non_ascii_key_is_rejected():
    """A mis-pasted key with a non-Latin character (e.g. Turkish 'ı') must be
    rejected at creation — it cannot become an HTTP auth header and would
    otherwise crash the LLM call at task time with a cryptic encoding error."""
    with pytest.raises(ValidationError):
        ApiKeyCreate(
            provider=LLMProvider.GEMINI,
            label="Personal",
            key="AIzaSyABCDEFGHIJKLMNOPQRSTUVWıXYZ",
        )


def test_key_surrounding_whitespace_is_stripped():
    payload = ApiKeyCreate(
        provider=LLMProvider.OPENAI, label="Personal", key="  sk-abc123  "
    )
    assert payload.key == "sk-abc123"
