"""User-selected domain: pipeline skips the orchestrator, schema validates."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.agents import orchestrator
from app.agents.base import AgentContext
from app.core.constants import EventType
from app.schemas.task import TaskCreate
from app.services import task_service
from tests.test_agents_flow import FakeAdapter


async def test_pipeline_user_domain_skips_orchestrator(monkeypatch):
    async def _fail_route(ctx: AgentContext, prompt: str) -> str:
        raise AssertionError("orchestrator.route must not be called")

    monkeypatch.setattr(orchestrator, "route", _fail_route)

    events: list[dict[str, Any]] = []

    async def collect(event_type: EventType, payload: dict[str, Any]) -> None:
        events.append({"type": event_type.value, **payload})

    ctx = AgentContext(adapter=FakeAdapter(), emit=collect)
    payload = TaskCreate(prompt="analyze this stock", domain="finance")
    result = await task_service._pipeline(ctx, payload)

    assert result["domain"] == "finance", f"Expected finance, got {result['domain']}"
    routing = next(e for e in events if e.get("role") == "orchestrator")
    assert routing["source"] == "user", f"Expected source=user, got {routing}"
    assert routing["state"] == "done", f"Expected state=done, got {routing}"


async def test_pipeline_no_domain_uses_orchestrator():
    ctx = AgentContext(adapter=FakeAdapter())
    payload = TaskCreate(prompt="Build me a Python function")
    result = await task_service._pipeline(ctx, payload)
    # FakeAdapter's orchestrator always classifies as software.
    assert result["domain"] == "software", f"Got {result['domain']}"


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("finance", "finance"),
        ("SEO", "seo"),
        (" searching ", "searching"),
        ("legal", "legal"),
        (" Content ", "content"),
        ("education", "education"),
        (None, None),
    ],
)
def test_task_create_valid_domain_is_normalized(domain, expected):
    payload = TaskCreate(prompt="x", domain=domain)
    assert payload.domain == expected, f"Expected {expected}, got {payload.domain}"


def test_task_create_unknown_domain_raises_validation_error():
    with pytest.raises(ValidationError):
        TaskCreate(prompt="x", domain="astrology")
