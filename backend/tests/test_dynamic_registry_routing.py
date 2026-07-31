"""Tur 11 remainder: custom-agent metadata, provenance, and auto-routing.

The orchestrator can route directly to a user's routable custom agent, and only
to one the caller actually owns; a hallucinated custom id falls back to default.
"""

from __future__ import annotations

import json
import uuid

from app.agents import orchestrator
from app.agents.base import AgentContext
from app.core.constants import LLMProvider
from app.schemas.agent import AgentConfigCreate
from app.services import agent_service
from app.services.llm_service import LLMAdapter, LLMResponse
from app.utils import prompt_guard


class _RouteAdapter(LLMAdapter):
    """Returns a fixed routing decision; records the catalog it was shown."""

    provider = LLMProvider.OLLAMA

    def __init__(self, domain: str) -> None:
        super().__init__()
        self._domain = domain
        self.system_seen = ""

    async def chat(self, messages, *, temperature=0.2, max_tokens=None, **_):  # noqa: ANN001
        self.system_seen = messages[0].content
        content = json.dumps({"domain": self._domain, "reason": "r"})
        return LLMResponse(content=content, model="fake", tokens_used=1)


async def test_routable_custom_agent_is_offered_and_selected() -> None:
    adapter = _RouteAdapter("custom:abc")
    ctx = AgentContext(adapter=adapter)
    result = await orchestrator.route_decision(
        ctx,
        "do the thing",
        custom_agents=[{"id": "abc", "name": "My Agent", "routing_hint": "does X"}],
    )
    assert "custom:abc: does X" in adapter.system_seen, "custom agent must be offered"
    assert result.domain == "custom:abc", "the orchestrator may route to a custom agent"


async def test_unowned_custom_selection_falls_back_to_default() -> None:
    # The model picks a custom id that is NOT in the caller's allow-list.
    adapter = _RouteAdapter("custom:not-mine")
    ctx = AgentContext(adapter=adapter)
    result = await orchestrator.route_decision(
        ctx, "do the thing", custom_agents=[{"id": "abc", "routing_hint": "does X"}]
    )
    assert result.domain == "general", "a non-owned custom id must not be honoured"


async def test_no_custom_agents_keeps_builtin_routing() -> None:
    adapter = _RouteAdapter("software")
    ctx = AgentContext(adapter=adapter)
    result = await orchestrator.route_decision(ctx, "write code")
    assert result.domain == "software"
    assert "custom:" not in adapter.system_seen, "no custom options when none provided"


class _FakeColl:
    def __init__(self) -> None:
        self.inserted: dict | None = None

    async def count_documents(self, criteria: dict) -> int:
        # Owned-agent count, read by the CUSTOM_AGENTS_MAX check on create.
        return 1 if self.inserted is not None else 0

    async def insert_one(self, doc: dict) -> None:
        self.inserted = doc


async def test_create_agent_stamps_provenance_metadata_and_scan(monkeypatch) -> None:
    fake = _FakeColl()
    monkeypatch.setattr(agent_service, "_collection", lambda: fake)
    doc = await agent_service.create_agent(
        uuid.uuid4(),
        AgentConfigCreate(
            name="A",
            domain="general",
            system_prompt="Be a helpful specialist.",
            routable=True,
            routing_hint="does X",
            description="d",
        ),
        source="marketplace",
        marketplace_item_id="item1",
    )
    assert doc["source"] == "marketplace"
    assert doc["marketplace_item_id"] == "item1"
    assert doc["routable"] is True
    assert doc["routing_hint"] == "does X"
    assert doc["security_scan"] == {
        "version": prompt_guard.SCANNER_VERSION,
        "passed": True,
    }
