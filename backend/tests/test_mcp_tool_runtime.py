"""MCP tools inside the live subagent loop: naming, gating, budgets, events.

Modelled on ``test_custom_api_tool_runtime.py``, which pins the same properties
for a registered HTTP endpoint. The first test in this file is the one that
matters most — see its docstring.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents import subagent
from app.agents import tools as tool_directives
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info, to_domain_info
from app.core.config import settings
from app.core.constants import EXECUTABLE_TOOL_IDS, TOOL_IDS
from app.services import mcp_service
from app.services.llm_service import ChatMessage, LLMAdapter, LLMProvider, LLMResponse
from app.services.mcp_service import McpServer, McpTool


@pytest.fixture(autouse=True)
def _mcp_on(monkeypatch):
    """The feature ships off, so every test here opts in explicitly."""
    monkeypatch.setattr(settings, "mcp_enabled", True)


def _tool(**overrides) -> McpTool:
    data = {
        "action": "mcp__acme__search",
        "remote_name": "search",
        "display_name": "Search",
        "description": "Search the corpus.",
        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
    }
    data.update(overrides)
    return McpTool(**data)


def _server(*tools: McpTool, **overrides) -> McpServer:
    data = {
        "id": "srv-1",
        "slug": "acme",
        "name": "Acme Tools",
        "url": "https://mcp.example.com/mcp",
        "auth_mode": "none",
        "auth_name": "",
        "headers": {},
        "timeout_seconds": 30,
        "tools": tools or (_tool(),),
    }
    data.update(overrides)
    return McpServer(**data)


class ScriptedAdapter(LLMAdapter):
    """Returns scripted replies in order; repeats the last when exhausted."""

    provider = LLMProvider.OLLAMA

    def __init__(self, replies: list[str]) -> None:
        super().__init__()
        self.replies = replies
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return LLMResponse(content=reply, model="fake", tokens_used=7)


def _directive(action: str, **args) -> str:
    return json.dumps({"action": action, "args": args})


@pytest.fixture
def mcp_calls(monkeypatch) -> list[tuple[str, dict]]:
    """Replace the executor's service call, recording what it was asked to do."""
    calls: list[tuple[str, dict]] = []

    async def fake_call(server: McpServer, tool: McpTool, args: dict) -> str:
        calls.append((tool.action, dict(args)))
        return "<mcp_result>\nfacts\n</mcp_result>"

    monkeypatch.setattr(mcp_service, "call", fake_call)
    return calls


def _mcp_domain(*servers: McpServer):
    """A custom agent that has attached every one of ``servers``."""
    return to_domain_info(
        {
            "id": "agent-1",
            "name": "Custom Agent",
            "domain": "general",
            "system_prompt": "Do the thing.",
            "tools": [],
            "mcp_server_ids": [server.id for server in servers],
        },
        (),
        (),
        servers,
    )


async def _run(adapter: LLMAdapter, *, domain_info, **ctx_kwargs):
    events: list[tuple[Any, dict]] = []

    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append((event_type, payload))

    ctx = AgentContext(
        adapter=adapter, emit=emit, domain_info=domain_info, **ctx_kwargs
    )
    result = await subagent.run_subtask(
        ctx,
        domain=domain_info.id,
        member=domain_info.team[0],
        brief="Do the thing",
        index=0,
    )
    return result, events


# --- the invariant _parse_mcp depends on ------------------------------------


def test_every_mcp_spec_sets_event_arg_to_none():
    """Write this test first; everything else in the design leans on it.

    ``_parse_mcp`` keeps nested objects and arrays in a directive's arguments,
    which ``_parse_custom_api`` deliberately flattens. That is only safe because
    ``ToolDirective.args`` reaches an Architect event payload verbatim *when
    ``event_arg`` is set*, and no MCP spec ever sets it. If this ever changes,
    model-supplied structured arguments start landing in the event stream and
    ``_parse_mcp`` must go back to stringifying.
    """
    specs = tool_directives.make_mcp_tool_specs(
        [_server(_tool(), _tool(action="mcp__acme__fetch", remote_name="fetch"))], 3
    )
    assert specs
    assert all(spec.event_arg is None for spec in specs.values())


# --- naming and namespacing -------------------------------------------------


def test_an_mcp_action_is_never_a_catalog_tool_id():
    """``TOOL_IDS`` and ``EXECUTABLE_TOOL_IDS`` are process-wide constants.

    A per-user action in either would leak one account's server names into every
    other account's validation and into the frontend parity tests.
    """
    specs = tool_directives.make_mcp_tool_specs([_server()], 3)
    for action in specs:
        assert action not in TOOL_IDS
        assert action not in EXECUTABLE_TOOL_IDS


def test_each_tool_gets_its_own_metadata_key():
    """A shared key would have the last spec in dict order clobber the rest."""
    specs = tool_directives.make_mcp_tool_specs(
        [_server(_tool(), _tool(action="mcp__acme__fetch", remote_name="fetch"))], 3
    )
    keys = {spec.metadata_key for spec in specs.values()}
    assert len(keys) == len(specs)


def test_the_process_wide_tables_are_never_mutated_by_a_per_run_tool():
    before_params = dict(tool_directives._TOOL_PARAMETERS)
    tool_directives.make_mcp_tool_specs([_server()], 3)
    assert tool_directives._TOOL_PARAMETERS == before_params


# --- gating -----------------------------------------------------------------


async def test_an_attached_server_enables_its_tools():
    server = _server()
    enabled = await tool_directives.resolve_enabled_tools(
        _mcp_domain(server), mcp_servers=(server,)
    )
    assert "mcp__acme__search" in enabled


async def test_the_operator_switch_withholds_every_mcp_tool(monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", False)
    server = _server()
    enabled = await tool_directives.resolve_enabled_tools(
        _mcp_domain(server), mcp_servers=(server,)
    )
    assert enabled == frozenset()


async def test_a_server_this_run_did_not_load_never_resolves():
    """The universe is widened by exactly what loaded, which is what stops one
    user's action name resolving for another."""
    server = _server()
    enabled = await tool_directives.resolve_enabled_tools(
        _mcp_domain(server), mcp_servers=()
    )
    assert enabled == frozenset()


async def test_an_assignment_can_only_narrow():
    server = _server(_tool(), _tool(action="mcp__acme__fetch", remote_name="fetch"))
    enabled = await tool_directives.resolve_enabled_tools(
        _mcp_domain(server),
        assigned=frozenset({"mcp__acme__search"}),
        mcp_servers=(server,),
    )
    assert enabled == frozenset({"mcp__acme__search"})


def test_an_unattached_server_is_not_offered():
    server = _server()
    info = to_domain_info(
        {
            "id": "agent-1",
            "domain": "general",
            "tools": [],
            "mcp_server_ids": [],
        },
        (),
        (),
        (server,),
    )
    assert info.tools == ()


def test_a_foreign_server_id_never_matches():
    info = to_domain_info(
        {
            "id": "agent-1",
            "domain": "general",
            "tools": [],
            "mcp_server_ids": ["someone-elses-server"],
        },
        (),
        (),
        (_server(),),
    )
    assert info.tools == ()


def test_a_builtin_domain_is_untouched_by_mcp_actions():
    assert all(not t.startswith("mcp__") for t in get_domain_info("general").tools)


# --- directive parsing ------------------------------------------------------


def test_nested_arguments_survive_parsing():
    """MCP input schemas routinely declare objects and arrays.

    Flattening them, as ``_parse_custom_api`` does, would make those tools
    uncallable on every provider without native function calling.
    """
    enabled = frozenset({"mcp__acme__search"})
    directive = tool_directives.parse_directive(
        _directive("mcp__acme__search", filter={"tags": ["a", "b"]}, n=3), enabled
    )
    assert directive.args == {"filter": {"tags": ["a", "b"]}, "n": 3}


def test_arguments_are_capped_in_depth_and_size():
    deep: Any = "x"
    for _ in range(10):
        deep = {"d": deep}
    directive = tool_directives.parse_directive(
        _directive("mcp__acme__search", deep=deep, long="y" * 10_000),
        frozenset({"mcp__acme__search"}),
    )
    assert len(directive.args["long"]) <= 2000
    assert json.dumps(directive.args).count('"d"') <= 4


def test_a_withheld_action_is_read_as_a_final_answer():
    assert (
        tool_directives.parse_directive(
            _directive("mcp__acme__search", q="x"), frozenset()
        )
        is None
    )


# --- the loop ---------------------------------------------------------------


async def test_a_directive_reaches_the_service(mcp_calls):
    server = _server()
    adapter = ScriptedAdapter(
        [_directive("mcp__acme__search", q="widgets"), "Here is the answer."]
    )
    result, _ = await _run(
        adapter, domain_info=_mcp_domain(server), mcp_servers=(server,)
    )
    assert mcp_calls == [("mcp__acme__search", {"q": "widgets"})]
    assert result.metadata["mcp_acme_search_used"] == 1


async def test_the_budget_bounds_the_calls(mcp_calls):
    server = _server()
    adapter = ScriptedAdapter([_directive("mcp__acme__search", q="x")])
    await _run(
        adapter,
        domain_info=_mcp_domain(server),
        mcp_servers=(server,),
        max_mcp_calls=2,
        max_tool_calls=6,
    )
    assert len(mcp_calls) == 2


async def test_two_servers_count_independently(mcp_calls):
    other = _server(
        _tool(action="mcp__beta__lookup", remote_name="lookup"),
        id="srv-2",
        slug="beta",
        name="Beta Tools",
    )
    server = _server()
    adapter = ScriptedAdapter(
        [
            _directive("mcp__acme__search", q="a"),
            _directive("mcp__beta__lookup", q="b"),
            "Done.",
        ]
    )
    result, _ = await _run(
        adapter,
        domain_info=_mcp_domain(server, other),
        mcp_servers=(server, other),
        max_mcp_calls=1,
    )
    assert result.metadata["mcp_acme_search_used"] == 1
    assert result.metadata["mcp_beta_lookup_used"] == 1


async def test_the_event_stream_never_carries_model_supplied_arguments(mcp_calls):
    server = _server()
    adapter = ScriptedAdapter(
        [_directive("mcp__acme__search", q="SENSITIVE-VALUE"), "Done."]
    )
    _, events = await _run(
        adapter, domain_info=_mcp_domain(server), mcp_servers=(server,)
    )
    assert "SENSITIVE-VALUE" not in json.dumps(
        [payload for _, payload in events], default=str
    )


async def test_the_event_stream_never_carries_the_server_url(mcp_calls):
    server = _server()
    adapter = ScriptedAdapter([_directive("mcp__acme__search", q="x"), "Done."])
    _, events = await _run(
        adapter, domain_info=_mcp_domain(server), mcp_servers=(server,)
    )
    assert "mcp.example.com" not in json.dumps(
        [payload for _, payload in events], default=str
    )


async def test_the_prompt_carries_the_rule_line_but_not_the_host(mcp_calls):
    server = _server()
    adapter = ScriptedAdapter(["Here is the answer."])
    await _run(adapter, domain_info=_mcp_domain(server), mcp_servers=(server,))
    system = adapter.calls[0][0].content
    assert "mcp__acme__search" in system
    assert "mcp.example.com" not in system
