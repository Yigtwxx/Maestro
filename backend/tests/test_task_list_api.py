"""Integration tests for GET /api/v1/tasks (Mongo layer mocked)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from app.services import task_service

_EMAIL = "history@user.com"
_PASSWORD = "supersecret"
_NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


async def _register_and_login(client) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": _EMAIL, "password": _PASSWORD, "display_name": "History"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _summary(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "status": "completed",
        "prompt": "Summarize the market",
        "domain": "finance",
        "error": None,
        "created_at": _NOW,
        "updated_at": _NOW,
    }


async def test_list_tasks_returns_paged_summaries(client, monkeypatch):
    monkeypatch.setattr(
        task_service,
        "list_tasks",
        AsyncMock(return_value=([_summary("a"), _summary("b")], 5)),
    )
    headers = await _register_and_login(client)

    resp = await client.get("/api/v1/tasks?limit=2&offset=0", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 5, body
    assert body["limit"] == 2, body
    assert [item["task_id"] for item in body["items"]] == ["a", "b"], body
    # The heavy event array must never reach the history list.
    assert "events" not in body["items"][0], body["items"][0]


async def test_list_tasks_scopes_the_query_to_the_caller(client, monkeypatch):
    spy = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(task_service, "list_tasks", spy)
    headers = await _register_and_login(client)

    resp = await client.get("/api/v1/tasks", headers=headers)

    assert resp.status_code == 200, resp.text
    me = await client.get("/api/v1/users/me", headers=headers)
    assert str(spy.await_args.args[0]) == me.json()["id"], spy.await_args
    assert spy.await_args.kwargs == {"limit": 20, "offset": 0}, spy.await_args


async def test_list_tasks_rejects_an_oversized_limit(client, monkeypatch):
    monkeypatch.setattr(task_service, "list_tasks", AsyncMock(return_value=([], 0)))
    headers = await _register_and_login(client)

    resp = await client.get("/api/v1/tasks?limit=500", headers=headers)

    assert resp.status_code == 422, resp.text


async def test_list_tasks_requires_authentication(client):
    resp = await client.get("/api/v1/tasks")
    assert resp.status_code == 401, resp.text
