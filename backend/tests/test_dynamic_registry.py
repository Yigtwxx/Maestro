"""Dynamic agent registry: custom agents resolve to a runnable one-member team.

Custom/marketplace agents now actually execute (Backend v2 §4.3): a
``custom:{id}`` selector loads the owner's config, sandboxes its system prompt in
a persona block, inherits the built-in domain's methodology/rubric, and runs
through the normal plan -> execute -> review pipeline.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.agents.registry import (
    CustomAgentUnavailable,
    get_domain_info,
    resolve_domain_info,
    to_domain_info,
)
from app.schemas.task import TaskCreate

_DOC = {
    "id": "abc",
    "user_id": "u",
    "name": "My Agent",
    "domain": "software",
    "system_prompt": "Always answer tersely.",
    "tools": ["web_search", "not_a_real_tool"],
    "routing_hint": "handles bespoke build tasks",
}


def test_to_domain_info_builds_a_sandboxed_single_member_team() -> None:
    info = to_domain_info(_DOC)

    assert info.id == "custom:abc", info.id
    assert len(info.team) == 1, info.team
    member = info.team[0]
    assert "<agent_persona>" in member.instructions
    assert "Always answer tersely." in member.instructions
    # Inherits the built-in software domain's methodology and review rubric.
    base = get_domain_info("software")
    assert info.methodology == base.methodology
    assert info.review_rubric == base.review_rubric
    # Only executable tools survive the intersection.
    assert "web_search" in info.tools
    assert "not_a_real_tool" not in info.tools


async def test_resolve_builtin_domain_returns_catalog_entry() -> None:
    info = await resolve_domain_info(uuid.uuid4(), "software")
    assert info.id == "software", info.id


async def test_resolve_custom_loads_owner_config(monkeypatch) -> None:
    from app.services import agent_service
    from app.utils import prompt_guard

    monkeypatch.setattr(agent_service, "get_agent", AsyncMock(return_value=_DOC))
    monkeypatch.setattr(prompt_guard, "scan_prompt", lambda _s: [])

    info = await resolve_domain_info(uuid.uuid4(), "custom:abc")

    assert info.id == "custom:abc", info.id
    assert info.team[0].name == "My Agent"


async def test_resolve_custom_missing_raises(monkeypatch) -> None:
    from app.services import agent_service

    monkeypatch.setattr(agent_service, "get_agent", AsyncMock(return_value=None))

    with pytest.raises(CustomAgentUnavailable):
        await resolve_domain_info(uuid.uuid4(), "custom:gone")


async def test_resolve_custom_that_fails_rescan_raises(monkeypatch) -> None:
    from app.services import agent_service
    from app.utils import prompt_guard

    monkeypatch.setattr(agent_service, "get_agent", AsyncMock(return_value=_DOC))
    # Simulate a scanner that now flags a config written before an upgrade.
    monkeypatch.setattr(prompt_guard, "scan_prompt", lambda _s: ["suspicious"])

    with pytest.raises(CustomAgentUnavailable):
        await resolve_domain_info(uuid.uuid4(), "custom:abc")


def test_taskcreate_accepts_a_custom_agent_selector() -> None:
    agent_id = str(uuid.uuid4())
    task = TaskCreate(prompt="do it", domain=f"custom:{agent_id}")
    assert task.domain == f"custom:{agent_id}", task.domain


def test_taskcreate_rejects_a_malformed_custom_id() -> None:
    with pytest.raises(ValidationError):
        TaskCreate(prompt="do it", domain="custom:not-a-uuid")
