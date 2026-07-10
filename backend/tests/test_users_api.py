"""Integration tests for /users/me profile endpoints (SQLite-backed)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.constants import ACCOUNT_DELETION_GRACE_DAYS, SubscriptionStatus
from app.models.subscription import Subscription
from app.models.user import User
from app.services import task_service

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


async def _add_key(client, headers: dict[str, str], provider: str) -> None:  # noqa: ANN001
    resp = await client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"provider": provider, "label": "k", "key": "sk-secret-value-1234"},
    )
    assert resp.status_code == 201, f"Key create failed: {resp.text}"


async def test_get_me_returns_profile(client):
    headers = await _register_and_login(client)
    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == _EMAIL
    assert body["subscription_tier"] == "starter"
    assert body["default_provider"] is None
    assert "hashed_password" not in body


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


async def test_patch_me_updates_email_lowercased(client):
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"email": "New@Mail.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "new@mail.com"


async def test_patch_me_duplicate_email_conflict(client):
    await _register_and_login(client, email="other@user.com")
    headers = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me", headers=headers, json={"email": "other@user.com"}
    )
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}"


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
    async def fake_start_task(*, user_id, payload, api_key) -> str:  # noqa: ANN001, ANN003
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
    async def fake_start_task(*, user_id, payload, api_key) -> str:  # noqa: ANN001, ANN003
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


async def test_delete_me_leaves_a_trial_alone(client, db_session):
    """A trial bills nothing, so cancelling it would only punish a restore."""
    headers = await _register_and_login(client)
    await _request_deletion(client, headers)

    subscription = await _subscription_of(db_session, _EMAIL)
    assert subscription.status == SubscriptionStatus.TRIALING.value, (
        f"Expected the trial to survive, got {subscription.status}"
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

    async def fake_start_task(*, user_id, payload, api_key) -> str:  # noqa: ANN001, ANN003
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

    async def fake_start_task(*, user_id, payload, api_key) -> str:  # noqa: ANN001, ANN003
        captured["provider"] = payload.provider
        return "task-123"

    monkeypatch.setattr(task_service, "start_task", fake_start_task)

    headers = await _register_and_login(client)
    resp = await client.post("/api/v1/tasks", headers=headers, json={"prompt": "hello"})
    assert resp.status_code == 202
    assert captured["provider"].value == "ollama"


async def test_task_start_explicit_provider_beats_default(client, monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_start_task(*, user_id, payload, api_key) -> str:  # noqa: ANN001, ANN003
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
