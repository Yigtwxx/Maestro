"""Per-account concurrency: how many tasks one user may hold in flight.

The token quota bounds what an account spends over a month and says nothing
about how much it runs at once. Before this cap the only ceiling was
``RATE_LIMIT_EXPENSIVE`` x ``task_timeout_seconds`` -- hundreds of simultaneous
runs per account, each fanning out to subagents, outbound fetches and sandbox
containers.

What is load-bearing here is *where* the check lives: at the single run-header
insert, inside the transaction that writes it. A count in the route handler
would pass for every request of a simultaneous burst.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.constants import (
    PLAN_MAX_CONCURRENT_TASKS,
    RESUMABLE_TASK_STATUSES,
    SubscriptionPlan,
    TaskStatus,
    UserRole,
)
from app.models import TaskRun, User
from app.services import quota_service, task_run_store

_PASSWORD = "password123"


async def _make_user(db_session, email: str, *, role: UserRole = UserRole.USER) -> User:
    user = User(email=email, hashed_password="x", role=role.value)
    db_session.add(user)
    await db_session.commit()
    return user


async def _create(user_id: uuid.UUID, task_id: str, *, max_active: int | None) -> None:
    await task_run_store.create_run(
        task_id=task_id,
        user_id=user_id,
        payload={"prompt": "hello"},
        provider="ollama",
        deadline_at=datetime.now(UTC) + timedelta(seconds=300),
        max_active=max_active,
    )


async def _run_count(db_session, user_id: uuid.UUID) -> int:
    rows = await db_session.scalars(select(TaskRun).where(TaskRun.user_id == user_id))
    return len(rows.all())


def test_every_plan_declares_a_concurrency_ceiling() -> None:
    """A plan missing from the map would KeyError at task start, not default."""
    assert set(PLAN_MAX_CONCURRENT_TASKS) == {p.value for p in SubscriptionPlan}
    assert all(limit >= 1 for limit in PLAN_MAX_CONCURRENT_TASKS.values()), (
        "A zero or negative ceiling would refuse every task on that plan"
    )


async def test_create_run_refuses_past_the_cap_and_writes_nothing(db_session) -> None:
    user = await _make_user(db_session, "cap@concurrency.example.com")

    await _create(user.id, "run-1", max_active=1)
    with pytest.raises(task_run_store.ConcurrencyLimitReached) as excinfo:
        await _create(user.id, "run-2", max_active=1)

    assert excinfo.value.limit == 1
    assert await _run_count(db_session, user.id) == 1, (
        "A refused start must leave no run header behind"
    )


async def test_a_terminal_run_frees_the_slot(db_session) -> None:
    user = await _make_user(db_session, "free-slot@concurrency.example.com")

    await _create(user.id, "run-1", max_active=1)
    await task_run_store.set_status("run-1", TaskStatus.COMPLETED.value)
    await _create(user.id, "run-2", max_active=1)

    assert await _run_count(db_session, user.id) == 2


@pytest.mark.parametrize("status", [s.value for s in RESUMABLE_TASK_STATUSES])
async def test_every_resumable_status_holds_a_slot(db_session, status: str) -> None:
    """Including AWAITING_ANSWER: a paused task still owns a lease and a runner."""
    user = await _make_user(db_session, f"{status}@concurrency.example.com")

    await _create(user.id, f"{status}-1", max_active=1)
    await task_run_store.set_status(f"{status}-1", status)

    with pytest.raises(task_run_store.ConcurrencyLimitReached):
        await _create(user.id, f"{status}-2", max_active=1)


async def test_the_cap_is_per_user(db_session) -> None:
    first = await _make_user(db_session, "one@concurrency.example.com")
    second = await _make_user(db_session, "two@concurrency.example.com")

    await _create(first.id, "run-1", max_active=1)
    await _create(second.id, "run-2", max_active=1)

    assert await _run_count(db_session, second.id) == 1, (
        "One user's in-flight task must never consume another's slot"
    )


async def test_no_cap_when_max_active_is_none(db_session) -> None:
    user = await _make_user(db_session, "uncapped@concurrency.example.com")

    for index in range(4):
        await _create(user.id, f"run-{index}", max_active=None)

    assert await _run_count(db_session, user.id) == 4


async def test_free_plan_resolves_to_its_declared_ceiling(client, db_session) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "plan@concurrency.example.com", "password": _PASSWORD},
    )
    user = await db_session.scalar(
        select(User).where(User.email == "plan@concurrency.example.com")
    )

    limit = await quota_service.resolve_task_concurrency_limit(db_session, user)
    assert limit == PLAN_MAX_CONCURRENT_TASKS[SubscriptionPlan.FREE.value]


async def test_admins_are_uncapped(db_session) -> None:
    """Unmetered accounts bypass the cap, as they do the token quota."""
    admin = await _make_user(
        db_session, "admin@concurrency.example.com", role=UserRole.ADMIN
    )

    limit = await quota_service.resolve_task_concurrency_limit(db_session, admin)
    assert limit is None


async def test_start_task_endpoint_answers_429_when_the_slot_is_taken(
    client, db_session
) -> None:
    email = "endpoint@concurrency.example.com"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": _PASSWORD}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    user = await db_session.scalar(select(User).where(User.email == email))
    await _create(user.id, "in-flight", max_active=None)

    resp = await client.post("/api/v1/tasks", headers=headers, json={"prompt": "hi"})

    assert resp.status_code == 429, f"Expected 429, got {resp.status_code}: {resp.text}"
    assert "at a time" in resp.json()["detail"]
