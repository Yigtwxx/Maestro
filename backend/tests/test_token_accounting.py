"""Tests for the token meter and the usage ledger it feeds.

Two regressions are pinned here:
  (a) tokens spent by a task that fails, times out or is cancelled were never
      recorded, so quota under-counted;
  (b) only subagent tokens were summed, so routing, planning, synthesis and
      review calls were free.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.constants import (
    LLMProvider,
    SubscriptionPlan,
    SubscriptionStatus,
    TaskStatus,
)
from app.models.subscription import Subscription
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.services import usage_service
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse, TokenMeter


class _FakeAdapter(LLMAdapter):
    """Returns a fixed token count per call."""

    provider = LLMProvider.OLLAMA

    def __init__(self, tokens_per_call: int) -> None:
        super().__init__(model="fake")
        self.tokens_per_call = tokens_per_call
        self.calls = 0

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(content="ok", model="fake", tokens_used=self.tokens_per_call)


async def _make_user(db_session) -> User:
    now = datetime.now(UTC)
    user = User(email="meter@test.com", hashed_password="x")
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


async def test_token_meter_accumulates_across_calls() -> None:
    meter = TokenMeter(_FakeAdapter(tokens_per_call=120))
    messages = [ChatMessage(role="user", content="hi")]

    for _ in range(3):
        await meter.chat(messages)

    assert meter.total_tokens == 360, f"Expected 360 tokens, got {meter.total_tokens}"


async def test_token_meter_delegates_provider_and_response() -> None:
    inner = _FakeAdapter(tokens_per_call=5)
    meter = TokenMeter(inner)

    response = await meter.chat([ChatMessage(role="user", content="hi")])

    assert meter.provider is LLMProvider.OLLAMA, f"Got {meter.provider}"
    assert response.content == "ok", f"Got {response.content}"
    assert inner.calls == 1, f"Inner adapter called {inner.calls} times"


async def test_record_task_usage_writes_a_row(db_session) -> None:
    user = await _make_user(db_session)

    await usage_service.record_task_usage(
        user_id=user.id,
        task_id="task-abc",
        tokens=4321,
        provider=LLMProvider.OLLAMA.value,
        status=TaskStatus.COMPLETED.value,
    )

    record = await db_session.scalar(
        select(UsageRecord).where(UsageRecord.task_id == "task-abc")
    )
    assert record is not None, "No usage record was written"
    assert record.tokens == 4321, f"Got {record.tokens} tokens"


async def test_record_task_usage_charges_a_cancelled_task(db_session) -> None:
    """Regression (a): a doomed task still spent tokens, so it still pays."""
    user = await _make_user(db_session)

    await usage_service.record_task_usage(
        user_id=user.id,
        task_id="task-cancelled",
        tokens=900,
        provider=LLMProvider.OLLAMA.value,
        status=TaskStatus.CANCELLED.value,
    )

    record = await db_session.scalar(
        select(UsageRecord).where(UsageRecord.task_id == "task-cancelled")
    )
    assert record is not None, "Cancelled task was not charged"
    assert record.tokens == 900, f"Got {record.tokens} tokens"
    assert record.status == TaskStatus.CANCELLED.value


async def test_record_task_usage_is_idempotent(db_session) -> None:
    user = await _make_user(db_session)

    for _ in range(2):
        await usage_service.record_task_usage(
            user_id=user.id,
            task_id="task-dup",
            tokens=50,
            provider=LLMProvider.OLLAMA.value,
            status=TaskStatus.COMPLETED.value,
        )

    total = await usage_service.used_tokens_this_period(
        db_session,
        user.id,
        (
            await db_session.scalar(
                select(Subscription).where(Subscription.user_id == user.id)
            )
        ).current_period_start,
    )
    assert total == 50, f"Double-charged: expected 50 tokens, got {total}"


async def test_record_task_usage_without_subscription_is_a_noop(db_session) -> None:
    user = User(email="orphan@test.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    await usage_service.record_task_usage(
        user_id=user.id,
        task_id="task-orphan",
        tokens=10,
        provider=LLMProvider.OLLAMA.value,
        status=TaskStatus.COMPLETED.value,
    )

    record = await db_session.scalar(
        select(UsageRecord).where(UsageRecord.task_id == "task-orphan")
    )
    assert record is None, "Usage was charged without a subscription"
