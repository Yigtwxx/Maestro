"""Failure and degradation must reach the client, not just the server log.

Every path here used to be silent: the UI showed a subagent stuck mid-run, or a
task that quietly fell back to a default and looked like a clean success.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from tenacity import RetryCallState

from app.agents import subagent
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info
from app.core.constants import EventType, LLMProvider, SubagentStatus
from app.services import llm_service
from app.services.llm_service import ChatMessage, LLMAdapter, LLMError, LLMResponse


class _Recorder:
    """Collects emitted events so a test can assert on the wire payload."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, event_type: EventType, payload: dict[str, Any]) -> None:
        self.events.append((event_type.value, payload))

    def of_type(self, event_type: EventType) -> list[dict[str, Any]]:
        return [p for t, p in self.events if t == event_type.value]


class _FailingAdapter(LLMAdapter):
    """Every chat call fails the way an unreachable Ollama does."""

    provider = LLMProvider.OLLAMA

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        raise LLMError("ollama chat failed: connection refused")


@pytest.mark.asyncio
async def test_subagent_llm_failure_closes_its_node_as_error():
    """A failed member must close its node, or the card hangs on "running"."""
    recorder = _Recorder()
    ctx = AgentContext(adapter=_FailingAdapter(), emit=recorder)
    member = get_domain_info("software").team[0]

    result = await subagent.run_subtask(
        ctx,
        domain="software",
        member=member,
        brief="Write a function",
        index=0,
        objective="Write a function",
    )

    assert result.status is SubagentStatus.ERROR, "A failed chat is an error result"
    states = [
        p["state"] for p in recorder.of_type(EventType.NODE_UPDATE) if p["index"] == 0
    ]
    assert states == ["running", "error"], (
        f"Expected the node to open then close as error, got {states}"
    )


@pytest.mark.asyncio
async def test_subagent_error_node_carries_the_cause():
    """The node update carries why it failed, so the log line is diagnosable."""
    recorder = _Recorder()
    ctx = AgentContext(adapter=_FailingAdapter(), emit=recorder)
    member = get_domain_info("software").team[0]

    await subagent.run_subtask(
        ctx,
        domain="software",
        member=member,
        brief="Write a function",
        index=0,
        objective="Write a function",
    )

    errored = [
        p for p in recorder.of_type(EventType.NODE_UPDATE) if p["state"] == "error"
    ]
    assert len(errored) == 1, "Exactly one error update per failed member"
    assert "connection refused" in errored[0]["error"], (
        "The node update must name the cause"
    )


def _retry_state(exc: BaseException) -> RetryCallState:
    """A RetryCallState whose outcome is a raised ``exc`` (tenacity internals)."""
    state = RetryCallState(retry_object=None, fn=None, args=(), kwargs={})
    state.set_exception((type(exc), exc, None))
    return state


@pytest.mark.asyncio
async def test_retry_notifier_reports_attempt_and_cause():
    """A degrading connection is reported while the task is still running."""
    seen: list[dict[str, Any]] = []

    async def observer(info: dict[str, Any]) -> None:
        seen.append(info)

    llm_service.set_retry_observer(observer)
    try:
        await llm_service._notify_retry(_retry_state(httpx.ConnectError("boom")))
    finally:
        llm_service.set_retry_observer(None)

    assert len(seen) == 1, "One notification per exhausted attempt"
    assert seen[0]["cause"] == "ConnectError", "The cause is the exception class"


@pytest.mark.asyncio
async def test_retry_notifier_never_leaks_the_provider_body():
    """Only the class name travels — an error body can hold a raw API response."""
    seen: list[dict[str, Any]] = []

    async def observer(info: dict[str, Any]) -> None:
        seen.append(info)

    secret = "sk-live-should-never-appear"
    llm_service.set_retry_observer(observer)
    try:
        await llm_service._notify_retry(_retry_state(httpx.ConnectError(secret)))
    finally:
        llm_service.set_retry_observer(None)

    assert secret not in str(seen[0]), f"Raw exception text leaked into {seen[0]}"


@pytest.mark.asyncio
async def test_retry_notifier_is_silent_without_an_observer():
    """Outside a task run (scripts, tests) there is nobody to notify."""
    llm_service.set_retry_observer(None)
    await llm_service._notify_retry(_retry_state(httpx.ConnectError("boom")))
