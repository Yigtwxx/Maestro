"""Durable task-execution engine: checkpoints, resume, reconciliation, billing.

Covers the Backend v2 §4.1 guarantees the pre-v2 ``_run_task`` had zero tests
for: a step with a checkpoint is replayed (no LLM call); a crashed worker's
orphan is reclaimed and either resumed or finalized (never stuck at "running");
usage is monotone (upsert-max) and free-tier tokens are excluded from quota.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.constants import (
    TASK_MAX_RESUME_ATTEMPTS,
    EventType,
    LLMProvider,
    SubscriptionPlan,
    SubscriptionStatus,
    TaskStatus,
)
from app.models.subscription import Subscription
from app.models.task_run import TaskRun
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.schemas.task import TaskCreate
from app.services import (
    checkpoint_store,
    reconcile,
    task_engine,
    task_run_store,
    task_service,
    usage_service,
)


class _FakeSessions:
    """Swallows Mongo status/result writes the engine performs."""

    async def update_one(self, *args: Any, **kwargs: Any) -> None:
        return None


async def _make_user(db_session) -> User:  # noqa: ANN001
    now = datetime.now(UTC)
    user = User(email=f"engine-{now.timestamp()}@test.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.STARTER.value,
            status=SubscriptionStatus.ACTIVE.value,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
    )
    await db_session.commit()
    return user


def _payload() -> dict[str, Any]:
    return TaskCreate(prompt="hi", provider="ollama").model_dump(mode="json")


async def _seed_run(
    db_session,  # noqa: ANN001
    user: User,
    task_id: str,
    *,
    status: str = TaskStatus.RUNNING.value,
    lease_offset_seconds: int = -300,
    attempt: int = 0,
    deadline_offset_seconds: int = 3600,
) -> None:
    now = datetime.now(UTC)
    await task_run_store.create_run(
        task_id=task_id,
        user_id=user.id,
        payload=_payload(),
        provider=LLMProvider.OLLAMA.value,
        deadline_at=now + timedelta(seconds=deadline_offset_seconds),
    )
    row = await db_session.get(TaskRun, task_id)
    row.status = status
    row.lease_expires_at = now + timedelta(seconds=lease_offset_seconds)
    row.attempt = attempt
    await db_session.commit()


def _stub_terminal_io(monkeypatch) -> list[tuple[EventType, dict]]:  # noqa: ANN001
    """Silence the Mongo/bus/RAG side effects and capture emitted events."""
    recorded: list[tuple[EventType, dict]] = []

    def _fake_make_emit(task_id, user_id):  # noqa: ANN001
        async def emit(event_type: EventType, payload: dict) -> None:
            recorded.append((event_type, payload))

        return emit

    monkeypatch.setattr(task_service, "_make_emit", _fake_make_emit)
    monkeypatch.setattr(task_service, "_sessions_collection", lambda: _FakeSessions())
    monkeypatch.setattr(task_service, "_gather_context", AsyncMock(return_value=[]))
    monkeypatch.setattr(task_service, "_remember", AsyncMock())
    monkeypatch.setattr(task_service.event_bus, "close", AsyncMock())
    monkeypatch.setattr(task_engine.event_bus, "close", AsyncMock())
    return recorded


# --- checkpoint store -----------------------------------------------------


async def test_checkpoint_write_is_idempotent(db_session) -> None:
    user = await _make_user(db_session)
    task_id = "cp-idem"
    await _seed_run(db_session, user, task_id)

    await checkpoint_store.write(task_id, "route", {"v": 1, "domain": "general"}, 5)
    # A second write for the same key is a no-op (first write wins).
    await checkpoint_store.write(task_id, "route", {"v": 1, "domain": "other"}, 99)

    assert await checkpoint_store.is_complete(task_id, "route")
    payload = await checkpoint_store.load(task_id, "route")
    assert payload == {"v": 1, "domain": "general"}, payload
    assert await checkpoint_store.token_sum(task_id) == 5


# --- resume / replay ------------------------------------------------------


async def test_engine_replays_checkpointed_steps_without_llm(
    db_session, monkeypatch
) -> None:
    """Both steps checkpointed -> the engine finalizes without any LLM call."""
    user = await _make_user(db_session)
    task_id = "eng-replay"
    await _seed_run(db_session, user, task_id, status=TaskStatus.PENDING.value)
    await checkpoint_store.write(
        task_id, "route", {"v": 1, "domain": "general", "source": "orchestrator"}, 10
    )
    await checkpoint_store.write(
        task_id,
        "execute",
        {
            "v": 1,
            "result": {
                "answer": "cached answer",
                "all_subtasks_failed": False,
                "domain": "general",
                "metadata": {},
            },
        },
        20,
    )

    async def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("an LLM step ran despite an existing checkpoint")

    monkeypatch.setattr(task_service, "_route", _boom)
    monkeypatch.setattr(task_engine.main_agent, "run", _boom)
    recorded = _stub_terminal_io(monkeypatch)

    rc = task_engine.TaskRunContext(
        task_id=task_id,
        user_id=user.id,
        payload=TaskCreate(prompt="hi", provider="ollama"),
        api_key=None,
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
        resumed=True,
    )
    await task_engine.run(rc)

    run = await task_run_store.get_run(task_id)
    assert run is not None and run.status == TaskStatus.COMPLETED.value, run
    assert any(t is EventType.TASK_COMPLETED for t, _ in recorded), recorded

    record = await db_session.scalar(
        select(UsageRecord).where(UsageRecord.task_id == task_id)
    )
    assert record is not None, "resumed run was not billed"
    # Seeded meter = sum of checkpoint tokens (10 + 20); Ollama is non-billable.
    assert record.tokens == 30, record.tokens
    assert record.billable is False, "free-tier tokens must not be billable"


# --- reconciliation -------------------------------------------------------


async def test_sweep_claims_orphan_and_resumes(db_session, monkeypatch) -> None:
    user = await _make_user(db_session)
    task_id = "eng-orphan"
    await _seed_run(db_session, user, task_id)

    spawned: dict[str, task_engine.TaskRunContext] = {}

    async def _fake_run(rc: task_engine.TaskRunContext) -> None:
        spawned["rc"] = rc

    monkeypatch.setattr(task_engine, "run", _fake_run)

    acted = await reconcile.sweep_once()
    await asyncio.sleep(0)  # let the spawned resume task record its context

    assert acted == 1, acted
    run = await task_run_store.get_run(task_id)
    assert run is not None and run.attempt == 1, "claim must increment attempt"
    assert "rc" in spawned, "an orphan under the cap must be resumed"
    assert spawned["rc"].resumed is True
    task_service._running.pop(task_id, None)


async def test_sweep_fails_run_over_attempt_cap(db_session, monkeypatch) -> None:
    user = await _make_user(db_session)
    task_id = "eng-overcap"
    await _seed_run(db_session, user, task_id, attempt=TASK_MAX_RESUME_ATTEMPTS)
    _stub_terminal_io(monkeypatch)

    acted = await reconcile.sweep_once()

    assert acted == 1, acted
    run = await task_run_store.get_run(task_id)
    assert run is not None and run.status == TaskStatus.FAILED.value, run
    record = await db_session.scalar(
        select(UsageRecord).where(UsageRecord.task_id == task_id)
    )
    assert record is not None, "a repeatedly-crashed task must still be billed"


async def test_partial_failure_completes_with_warnings(db_session, monkeypatch) -> None:
    """Some (not all) subtasks failed -> completed_with_warnings + warnings event."""
    user = await _make_user(db_session)
    task_id = "eng-warn"
    await _seed_run(db_session, user, task_id, status=TaskStatus.PENDING.value)
    await checkpoint_store.write(
        task_id, "route", {"v": 1, "domain": "general", "source": "orchestrator"}, 5
    )
    await checkpoint_store.write(
        task_id,
        "execute",
        {
            "v": 1,
            "result": {
                "answer": "partial answer",
                "all_subtasks_failed": False,
                "domain": "general",
                "metadata": {},
                "failed_subtasks": [
                    {
                        "member_id": "m2",
                        "member_name": "Researcher",
                        "brief": "gather data",
                        "error": "boom",
                    }
                ],
            },
        },
        5,
    )

    async def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no LLM step should run on a full replay")

    monkeypatch.setattr(task_service, "_route", _boom)
    monkeypatch.setattr(task_engine.main_agent, "run", _boom)
    recorded = _stub_terminal_io(monkeypatch)

    rc = task_engine.TaskRunContext(
        task_id=task_id,
        user_id=user.id,
        payload=TaskCreate(prompt="hi", provider="ollama"),
        api_key=None,
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
        resumed=True,
    )
    await task_engine.run(rc)

    run = await task_run_store.get_run(task_id)
    assert run is not None and run.status == TaskStatus.COMPLETED_WITH_WARNINGS.value, (
        run
    )
    warned = [p for t, p in recorded if t is EventType.TASK_COMPLETED_WITH_WARNINGS]
    assert warned, recorded
    assert warned[0]["warnings"], "the warnings list must name the failed subtask"


async def test_sweep_times_out_run_past_deadline(db_session, monkeypatch) -> None:
    user = await _make_user(db_session)
    task_id = "eng-deadline"
    await _seed_run(db_session, user, task_id, deadline_offset_seconds=-10)
    _stub_terminal_io(monkeypatch)

    acted = await reconcile.sweep_once()

    assert acted == 1, acted
    run = await task_run_store.get_run(task_id)
    assert run is not None and run.status == TaskStatus.TIMEOUT.value, run


# --- billing --------------------------------------------------------------


async def test_usage_upsert_is_monotone(db_session) -> None:
    user = await _make_user(db_session)

    async def _record(tokens: int) -> None:
        await usage_service.record_task_usage(
            user_id=user.id,
            task_id="usage-monotone",
            tokens=tokens,
            provider=LLMProvider.OLLAMA.value,
            status=TaskStatus.RUNNING.value,
        )

    await _record(100)
    await _record(40)  # a resumed re-count must never lower the stored total
    row = await db_session.scalar(
        select(UsageRecord).where(UsageRecord.task_id == "usage-monotone")
    )
    assert row.tokens == 100, row.tokens
    await _record(250)
    await db_session.refresh(row)
    assert row.tokens == 250, row.tokens


async def test_non_billable_usage_is_excluded_from_quota(db_session) -> None:
    user = await _make_user(db_session)
    period_start = (
        await db_session.scalar(
            select(Subscription).where(Subscription.user_id == user.id)
        )
    ).current_period_start

    await usage_service.record_task_usage(
        user_id=user.id,
        task_id="free-tokens",
        tokens=500,
        provider=LLMProvider.OLLAMA.value,
        status=TaskStatus.COMPLETED.value,
        billable=False,
    )
    await usage_service.record_task_usage(
        user_id=user.id,
        task_id="paid-tokens",
        tokens=300,
        provider=LLMProvider.OPENAI.value,
        status=TaskStatus.COMPLETED.value,
        billable=True,
    )

    used = await usage_service.used_tokens_this_period(
        db_session, user.id, period_start
    )
    assert used == 300, f"only billable tokens count; got {used}"
