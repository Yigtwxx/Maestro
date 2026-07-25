"""BYOK service-credential loading.

The whole point of this layer is that it must never break a task: a missing,
rotated or corrupt key means "this tool is unavailable", never an exception. And
it must never leak — the object it returns ends up in agent contexts, log
records and tracebacks.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.constants import LLMProvider
from app.core.security import encrypt_secret
from app.models.api_key import ApiKey
from app.models.user import User
from app.services.service_key_service import (
    ServiceCredentials,
    load_service_credentials,
)

SECRET = "ghp_super_secret_value"


async def _make_user(db_session) -> User:
    user = User(
        email=f"{uuid.uuid4().hex}@example.com",
        hashed_password="x",
        display_name="Key Owner",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _add_key(
    db_session,
    user: User,
    provider: LLMProvider,
    secret: str = SECRET,
    *,
    is_active: bool = True,
    encrypted: str | None = None,
) -> ApiKey:
    key = ApiKey(
        user_id=user.id,
        provider=provider.value,
        encrypted_key=encrypted if encrypted is not None else encrypt_secret(secret),
        label=f"{provider.value} key",
        is_active=is_active,
    )
    db_session.add(key)
    await db_session.commit()
    return key


async def test_load_service_credentials_decrypts_stored_service_keys(db_session):
    user = await _make_user(db_session)
    await _add_key(db_session, user, LLMProvider.GITHUB)

    creds = await load_service_credentials(user.id)

    assert creds.get(LLMProvider.GITHUB) == SECRET, "Stored key must round-trip"
    assert creds.has(LLMProvider.GITHUB), "has() must agree with get()"


async def test_load_service_credentials_ignores_chat_providers(db_session):
    """An OpenAI brain key is not a tool credential and must not be exposed."""
    user = await _make_user(db_session)
    await _add_key(db_session, user, LLMProvider.OPENAI)

    creds = await load_service_credentials(user.id)

    assert creds.connected() == frozenset(), (
        f"Chat providers must be excluded, got {creds.connected()}"
    )


async def test_load_service_credentials_ignores_inactive_keys(db_session):
    user = await _make_user(db_session)
    await _add_key(db_session, user, LLMProvider.X, is_active=False)

    creds = await load_service_credentials(user.id)

    assert creds.get(LLMProvider.X) is None, "Inactive keys must not be loaded"


async def test_load_service_credentials_skips_undecryptable_key(db_session):
    """A rotated master key or corrupt row must degrade, not raise."""
    user = await _make_user(db_session)
    await _add_key(db_session, user, LLMProvider.SLACK, encrypted="not-base64-at-all")
    await _add_key(db_session, user, LLMProvider.GITHUB)

    creds = await load_service_credentials(user.id)

    assert creds.get(LLMProvider.SLACK) is None, "Corrupt key must be skipped"
    assert creds.get(LLMProvider.GITHUB) == SECRET, (
        "One bad key must not lose the others"
    )


async def test_load_service_credentials_is_empty_for_user_without_keys(db_session):
    user = await _make_user(db_session)

    creds = await load_service_credentials(user.id)

    assert creds.connected() == frozenset(), "No keys means an empty credential set"


async def test_load_service_credentials_scopes_to_the_requesting_user(db_session):
    """Credentials are per-user; one account must never see another's key."""
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    await _add_key(db_session, owner, LLMProvider.GITHUB)

    creds = await load_service_credentials(other.id)

    assert creds.get(LLMProvider.GITHUB) is None, "Keys must not leak across users"


@pytest.mark.parametrize("renderer", [repr, str])
def test_service_credentials_never_render_their_secrets(renderer):
    """This object reaches log records and tracebacks — it must stay opaque."""
    creds = ServiceCredentials({"github": SECRET, "x": "another-secret"})

    rendered = renderer(creds)

    assert SECRET not in rendered, f"Secret leaked into {renderer.__name__}: {rendered}"
    assert "another-secret" not in rendered, f"Secret leaked: {rendered}"
    assert "github" in rendered, "Provider names are safe and useful to show"


def test_service_credentials_accepts_plain_provider_strings():
    """The event payload and tool args carry provider ids as plain strings."""
    creds = ServiceCredentials({"discord": SECRET})

    assert creds.get("discord") == SECRET, "String lookup must work"
    assert creds.get(LLMProvider.DISCORD) == SECRET, "Enum lookup must work too"
