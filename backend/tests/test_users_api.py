"""Integration tests for /users/me profile endpoints (SQLite-backed)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.api.v1 import tasks as tasks_api
from app.core.config import settings
from app.core.constants import ACCOUNT_DELETION_GRACE_DAYS, SubscriptionStatus
from app.models.subscription import Subscription
from app.models.user import User
from app.services import quota_service, task_service

_EMAIL = "profile@user.com"
_PASSWORD = "supersecret"


async def _register_and_login(client, email: str = _EMAIL) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Profile"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _verify_email(client, sent_emails) -> None:  # noqa: ANN001
    """Redeem the link from the registration email."""
    match = re.search(r"token=([A-Za-z0-9_\-]+)", sent_emails[0].text)
    assert match is not None, "registration should have emailed a link"
    resp = await client.post(
        "/api/v1/auth/verify-email", json={"token": match.group(1)}
    )
    assert resp.status_code == 200, f"Verify failed: {resp.text}"


async def _add_key(client, headers: dict[str, str], provider: str) -> None:  # noqa: ANN001
    resp = await client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"provider": provider, "label": "k", "key": "sk-secret-value-1234"},
    )
    assert resp.status_code == 201, f"Key create failed: {resp.text}"


@pytest.fixture(autouse=True)
def _bypass_quota(monkeypatch):  # noqa: ANN001, ANN202
    """These tests exercise task-start defaulting, not billing.

    There is no trial, so a freshly registered account cannot start a task
    without subscribing. Quota enforcement is covered in test_quota_service /
    test_billing_api; here it is stubbed out so the provider- and reviewer-
    defaulting assertions are not masked by a 402.
    """

    async def _allow(db, user) -> None:  # noqa: ANN001
        return None

    monkeypatch.setattr(quota_service, "enforce_can_start_task", _allow)


async def test_get_me_returns_profile(client):
    headers = await _register_and_login(client)
    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == _EMAIL
    assert body["subscription_tier"] is None, "fresh accounts hold no subscription"
    assert body["default_provider"] is None
    assert "hashed_password" not in body
    # New personalization/preference fields are present with safe defaults.
    assert body["bio"] is None
    assert body["avatar_color"] is None
    assert body["two_factor_enabled"] is False
    assert body["default_reviewer_enabled"] is False
    assert body["created_at"] is not None, "created_at drives 'member since'"
    # The TOTP secret must never be exposed on the profile.
    assert "totp_secret" not in body


async def test_patch_me_updates_personalization(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"bio": "Hello there", "avatar_color": "cyan", "avatar_emoji": "🚀"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bio"] == "Hello there"
    assert body["avatar_color"] == "cyan"
    assert body["avatar_emoji"] == "🚀"


async def test_patch_me_rejects_unknown_avatar_color(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"avatar_color": "chartreuse"}
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


async def test_patch_me_blank_bio_clears_it(client):
    headers = await _register_and_login(client)
    await client.patch("/api/v1/users/me", headers=headers, json={"bio": "x"})
    resp = await client.patch("/api/v1/users/me", headers=headers, json={"bio": "   "})
    assert resp.status_code == 200
    assert resp.json()["bio"] is None


async def test_patch_me_sets_timezone_and_reviewer_default(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"timezone": "Europe/Istanbul", "default_reviewer_enabled": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["timezone"] == "Europe/Istanbul"
    assert resp.json()["default_reviewer_enabled"] is True


async def test_patch_me_rejects_unknown_timezone(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"timezone": "Mars/Phobos"}
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


async def test_get_me_requires_auth(client):
    assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_patch_me_updates_display_name(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"display_name": "Yeni Ad"}
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Yeni Ad"
    # Untouched fields survive a partial update.
    assert resp.json()["email"] == _EMAIL


async def test_patch_me_ignores_email_and_keeps_it_verified(client, sent_emails):
    """The address is immutable here -- changing it must re-run verification.

    An unknown key is ignored rather than 422'd, so a cached frontend bundle
    still posting ``email`` mid-deploy degrades to a no-op.
    """
    headers = await _register_and_login(client)
    await _verify_email(client, sent_emails)

    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"email": "attacker@evil.com"}
    )

    assert resp.status_code == 200
    assert resp.json()["email"] == _EMAIL, "email must not be updatable here"
    assert resp.json()["email_verified"] is True, "and must stay verified"


async def test_patch_me_default_provider_without_key_rejected(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_provider": "openai"}
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"


async def test_patch_me_default_provider_with_key_accepted(client):
    headers = await _register_and_login(client)
    await _add_key(client, headers, "openai")
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_provider": "openai"}
    )
    assert resp.status_code == 200
    assert resp.json()["default_provider"] == "openai"


async def test_patch_me_default_provider_ollama_needs_no_key(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_provider": "ollama"}
    )
    assert resp.status_code == 200
    assert resp.json()["default_provider"] == "ollama"


async def test_patch_me_default_provider_reset_to_null(client):
    headers = await _register_and_login(client)
    await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_provider": "ollama"}
    )
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_provider": None}
    )
    assert resp.status_code == 200
    assert resp.json()["default_provider"] is None


async def test_patch_me_default_provider_non_chat_rejected(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_provider": "x"}
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


async def test_patch_model_preferences_roundtrip(client):
    headers = await _register_and_login(client)
    prefs = {"main": "claude-opus-4-8", "synthesis": "gpt-4o"}
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"model_preferences": prefs}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["model_preferences"] == prefs

    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.json()["model_preferences"] == prefs, "pins must survive a GET"


async def test_patch_model_preferences_unknown_role_rejected(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"model_preferences": {"driver": "gpt-4o"}},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


async def test_patch_model_preferences_non_string_value_rejected(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"model_preferences": {"main": ["gpt-4o"]}},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


async def test_patch_model_preferences_blank_value_drops_role(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"model_preferences": {"main": "gpt-4o", "reviewer": "   "}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["model_preferences"] == {"main": "gpt-4o"}, (
        "a blank value must drop that role's pin"
    )


@pytest.mark.parametrize("clear_payload", [None, {}])
async def test_patch_model_preferences_null_or_empty_clears(client, clear_payload):
    headers = await _register_and_login(client)
    await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"model_preferences": {"main": "gpt-4o"}},
    )
    resp = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"model_preferences": clear_payload},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["model_preferences"] is None

    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.json()["model_preferences"] is None


async def test_patch_omitting_model_preferences_leaves_them_untouched(client):
    headers = await _register_and_login(client)
    prefs = {"main": "gpt-4o"}
    await client.patch(
        "/api/v1/users/me", headers=headers, json={"model_preferences": prefs}
    )
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"display_name": "Still Me"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["model_preferences"] == prefs, (
        "an omitted field must not touch the stored map"
    )


async def test_patch_model_preferences_value_too_long_rejected(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"model_preferences": {"main": "m" * 201}},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


async def test_password_change_wrong_current_rejected(client):
    headers = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": "wrongpass", "new_password": "newsupersecret"},
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"


async def test_password_change_allows_login_with_new_password(client):
    headers = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": _PASSWORD, "new_password": "newsupersecret"},
    )
    assert resp.status_code == 204
    old_login = await client.post(
        "/api/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD}
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/v1/auth/login", json={"email": _EMAIL, "password": "newsupersecret"}
    )
    assert new_login.status_code == 200


async def test_delete_me_wrong_password_rejected(client):
    headers = await _register_and_login(client)
    resp = await client.request(
        "DELETE",
        "/api/v1/users/me",
        headers=headers,
        json={"password": "wrongpass"},
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"


async def _request_deletion(client, headers: dict[str, str]):  # noqa: ANN001, ANN202
    resp = await client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Deletion request failed: {resp.text}"
    return resp.json()


async def test_delete_me_locks_account_without_destroying_it(client):
    headers = await _register_and_login(client)
    await _add_key(client, headers, "openai")

    body = await _request_deletion(client, headers)
    requested = datetime.fromisoformat(body["deletion_requested_at"])
    purge_after = datetime.fromisoformat(body["purge_after"])
    delta = purge_after - requested
    assert delta == timedelta(days=ACCOUNT_DELETION_GRACE_DAYS), (
        f"Expected a {ACCOUNT_DELETION_GRACE_DAYS}-day grace, got {delta}"
    )

    # Credentials keep working: the user must be able to come back and restore.
    login = await client.post(
        "/api/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD}
    )
    assert login.status_code == 200, "A locked account must still authenticate"

    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["deletion_requested_at"] is not None


async def test_delete_me_is_idempotent_and_does_not_extend_the_grace(client):
    headers = await _register_and_login(client)
    first = await _request_deletion(client, headers)
    second = await _request_deletion(client, headers)
    assert second["purge_after"] == first["purge_after"], (
        "Re-requesting deletion must not slide the purge date forward"
    )


async def test_locked_account_cannot_start_a_task(client, monkeypatch):
    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        raise AssertionError("A locked account must never reach task_service")

    monkeypatch.setattr(task_service, "start_task", fake_start_task)

    headers = await _register_and_login(client)
    await _request_deletion(client, headers)
    resp = await client.post("/api/v1/tasks", headers=headers, json={"prompt": "hello"})
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


async def test_locked_account_cannot_reach_other_product_endpoints(client):
    headers = await _register_and_login(client)
    await _request_deletion(client, headers)
    for path in ("/api/v1/api-keys", "/api/v1/agents", "/api/v1/documents"):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 403, (
            f"{path} must 403 while locked, got {resp.status_code}"
        )


async def test_locked_account_can_cancel_deletion_and_resume(client, monkeypatch):
    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)

    headers = await _register_and_login(client)
    await _request_deletion(client, headers)

    resp = await client.post("/api/v1/users/me/deletion/cancel", headers=headers)
    assert resp.status_code == 200, f"Restore failed: {resp.text}"
    assert resp.json()["deletion_requested_at"] is None

    resumed = await client.post(
        "/api/v1/tasks", headers=headers, json={"prompt": "hello"}
    )
    assert resumed.status_code == 202, "A restored account must be usable again"


async def test_cancel_deletion_on_an_active_account_is_a_noop(client):
    headers = await _register_and_login(client)
    resp = await client.post("/api/v1/users/me/deletion/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["deletion_requested_at"] is None


async def _subscription_of(db_session, email: str) -> Subscription:  # noqa: ANN001
    user = await db_session.scalar(select(User).where(User.email == email))
    return await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )


async def test_delete_me_cancels_a_paid_subscription(client, db_session):
    headers = await _register_and_login(client)
    subscribed = await client.post(
        "/api/v1/billing/subscribe",
        headers=headers,
        json={
            "plan": "starter",
            "card": {
                "number": "4242424242424242",
                "exp_month": 12,
                "exp_year": 2030,
                "cvc": "123",
                "holder": "A Person",
            },
        },
    )
    assert subscribed.status_code == 200, f"Subscribe failed: {subscribed.text}"

    await _request_deletion(client, headers)

    subscription = await _subscription_of(db_session, _EMAIL)
    assert subscription.status == SubscriptionStatus.CANCELED.value, (
        f"Expected canceled, got {subscription.status}"
    )
    assert subscription.cancel_at_period_end is True


async def test_delete_me_with_no_subscription_is_fine(client, db_session):
    """A fresh account holds no subscription; deletion has nothing to cancel."""
    headers = await _register_and_login(client)
    await _request_deletion(client, headers)

    subscription = await _subscription_of(db_session, _EMAIL)
    assert subscription is None, (
        f"A fresh account should have no subscription, got {subscription}"
    )


async def test_locked_account_can_export_its_data(client, monkeypatch):
    async def fake_export(db, user) -> dict[str, Any]:  # noqa: ANN001
        return {"profile": {"email": user.email}, "tasks": []}

    from app.api.v1 import users as users_module

    monkeypatch.setattr(users_module.user_service, "export_user_data", fake_export)

    headers = await _register_and_login(client)
    await _request_deletion(client, headers)

    resp = await client.get("/api/v1/users/me/export", headers=headers)
    assert resp.status_code == 200, f"Export failed: {resp.text}"
    assert resp.json()["profile"]["email"] == _EMAIL
    assert "attachment" in resp.headers["content-disposition"]


async def test_task_start_uses_default_brain_when_provider_omitted(client, monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        captured["provider"] = payload.provider
        captured["api_key"] = api_key
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)

    headers = await _register_and_login(client)
    await _add_key(client, headers, "openai")
    await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_provider": "openai"}
    )
    resp = await client.post("/api/v1/tasks", headers=headers, json={"prompt": "hello"})
    assert resp.status_code == 202, f"Task start failed: {resp.text}"
    assert captured["provider"].value == "openai"
    assert captured["api_key"] == "sk-secret-value-1234"


async def test_task_start_defaults_to_ollama_without_brain(client, monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        captured["provider"] = payload.provider
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)

    headers = await _register_and_login(client)
    resp = await client.post("/api/v1/tasks", headers=headers, json={"prompt": "hello"})
    assert resp.status_code == 202
    assert captured["provider"].value == "ollama"


async def test_task_start_explicit_provider_beats_default(client, monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        captured["provider"] = payload.provider
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)

    headers = await _register_and_login(client)
    await _add_key(client, headers, "openai")
    await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_provider": "openai"}
    )
    resp = await client.post(
        "/api/v1/tasks", headers=headers, json={"prompt": "hi", "provider": "ollama"}
    )
    assert resp.status_code == 202
    assert captured["provider"].value == "ollama"


async def test_task_start_ollama_disabled_returns_400(client, monkeypatch):
    started: dict[str, Any] = {}

    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        started["provider"] = payload.provider
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)
    monkeypatch.setattr(settings, "ollama_chat_enabled", False)

    headers = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/tasks", headers=headers, json={"prompt": "hi", "provider": "ollama"}
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"] == tasks_api.OLLAMA_CHAT_DISABLED_DETAIL
    assert not started, "Task must not start when the free chat model is disabled"


async def test_task_start_ollama_disabled_leaves_byok_providers_working(
    client, monkeypatch
):
    captured: dict[str, Any] = {}

    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        captured["provider"] = payload.provider
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)
    monkeypatch.setattr(settings, "ollama_chat_enabled", False)

    headers = await _register_and_login(client)
    await _add_key(client, headers, "openai")
    resp = await client.post(
        "/api/v1/tasks", headers=headers, json={"prompt": "hi", "provider": "openai"}
    )
    assert resp.status_code == 202, f"Task start failed: {resp.text}"
    assert captured["provider"].value == "openai"


async def test_task_start_merges_saved_model_preferences(client, monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        captured["model_overrides"] = payload.model_overrides
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)

    headers = await _register_and_login(client)
    await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"model_preferences": {"main": "pref-main", "reviewer": "pref-reviewer"}},
    )
    resp = await client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"prompt": "hi", "model_overrides": {"main": "req-main"}},
    )
    assert resp.status_code == 202, resp.text
    assert captured["model_overrides"] == {
        "main": "req-main",  # the request's per-role pin wins
        "reviewer": "pref-reviewer",  # the saved preference fills the gap
    }, f"Unexpected merge result: {captured['model_overrides']}"


async def test_task_start_inherits_reviewer_default_when_unset(client, monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        captured["reviewer_enabled"] = payload.reviewer_enabled
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)

    headers = await _register_and_login(client)
    await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_reviewer_enabled": True}
    )
    # Omitting reviewer_enabled falls back to the user's preference.
    resp = await client.post("/api/v1/tasks", headers=headers, json={"prompt": "hi"})
    assert resp.status_code == 202, resp.text
    assert captured["reviewer_enabled"] is True


async def test_task_start_explicit_reviewer_beats_default(client, monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_start_task(*, user_id, payload, api_key, **_kwargs) -> str:  # noqa: ANN001, ANN003
        captured["reviewer_enabled"] = payload.reviewer_enabled
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)

    headers = await _register_and_login(client)
    await client.patch(
        "/api/v1/users/me", headers=headers, json={"default_reviewer_enabled": True}
    )
    resp = await client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"prompt": "hi", "reviewer_enabled": False},
    )
    assert resp.status_code == 202
    assert captured["reviewer_enabled"] is False
