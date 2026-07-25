"""Invariants the BYOK provider catalog must hold.

The catalog is three parallel lists (the ``LLMProvider`` enum, the chat/service
split, and the adapter registry) plus a pricing table, and every one of them is
hand-maintained. These tests are what stop a half-added provider from reaching
production, where the failure modes are quiet: a provider missing from the
pricing table bills at zero, and an id one character too long for its column
raises only after the LLM spend has already happened.
"""

from __future__ import annotations

import pytest

from app.core.constants import (
    LLM_CHAT_PROVIDERS,
    PROVIDER_COST_PER_1K_TOKENS,
    SERVICE_PROVIDERS,
    LLMProvider,
)
from app.services.llm_service import _ADAPTERS

# api_keys.provider / task_runs.provider.
_KEY_COLUMN_LIMIT = 32
# users.default_provider and usage_records.provider are both narrower, and only
# a brain is ever written to them.
_BRAIN_COLUMN_LIMIT = 20


def test_every_provider_is_classified_as_brain_or_service():
    """A member in neither set is invisible to both the UI and the key loader."""
    unclassified = set(LLMProvider) - LLM_CHAT_PROVIDERS - SERVICE_PROVIDERS
    assert not unclassified, f"providers in neither split: {unclassified}"


def test_brain_and_service_splits_are_disjoint():
    """A chat provider must never be loadable as a tool credential."""
    both = LLM_CHAT_PROVIDERS & SERVICE_PROVIDERS
    assert not both, f"providers in both splits: {both}"


@pytest.mark.parametrize("provider", sorted(LLMProvider, key=lambda p: p.value))
def test_provider_id_fits_the_api_key_column(provider: LLMProvider):
    assert len(provider.value) <= _KEY_COLUMN_LIMIT, (
        f"'{provider.value}' is {len(provider.value)} chars; "
        f"api_keys.provider and task_runs.provider are String({_KEY_COLUMN_LIMIT})"
    )


@pytest.mark.parametrize("provider", sorted(LLM_CHAT_PROVIDERS, key=lambda p: p.value))
def test_brain_id_fits_the_narrower_brain_columns(provider: LLMProvider):
    """The failure this guards is expensive and late.

    An over-long brain id passes schema validation, passes the adapter, runs the
    task, and only then raises StringDataRightTruncation writing the usage
    record -- after the provider has already been billed for the tokens.
    """
    assert len(provider.value) <= _BRAIN_COLUMN_LIMIT, (
        f"'{provider.value}' is {len(provider.value)} chars; "
        f"users.default_provider and usage_records.provider are "
        f"String({_BRAIN_COLUMN_LIMIT})"
    )


@pytest.mark.parametrize(
    "provider",
    # Ollama is local and free; custom is a user endpoint whose price genuinely
    # cannot be known. Every named paid provider must carry a rate.
    sorted(
        LLM_CHAT_PROVIDERS - {LLMProvider.OLLAMA, LLMProvider.CUSTOM},
        key=lambda p: p.value,
    ),
)
def test_paid_brain_has_a_cost_rate(provider: LLMProvider):
    """Both cost call sites use ``.get(provider, 0.0)``.

    A missing entry therefore does not raise -- it silently reports a paid
    provider as free on the cost dashboard and in every trace span.
    """
    assert provider.value in PROVIDER_COST_PER_1K_TOKENS, (
        f"'{provider.value}' has no PROVIDER_COST_PER_1K_TOKENS entry, so it "
        f"would silently bill at $0"
    )


def test_every_chat_provider_has_an_adapter():
    missing = LLM_CHAT_PROVIDERS - set(_ADAPTERS)
    assert not missing, f"chat providers without adapters: {missing}"


def test_no_service_provider_has_an_adapter():
    """A stored service key must never be usable as a task brain."""
    leaked = SERVICE_PROVIDERS & set(_ADAPTERS)
    assert not leaked, f"service providers registered as adapters: {leaked}"
