"""A registered endpoint becoming a callable directive inside the subagent loop.

Three things are load-bearing and none is visible from ``custom_api_service``:

* **Visibility.** A tool absent from the prompt rules is invisible to every model
  driving the JSON directive protocol rather than native function calling. The
  built-in tools get that from ``TOOL_RULE_LINES``; a per-user tool cannot, so
  it carries its own line and ``rule_line_for`` is the single lookup.
* **Isolation.** The action name is built from the *loaded* endpoints, so one
  user's slug never resolves for another, and neither the schema nor the prompt
  text may be written into the process-wide tables.
* **Bounds.** CLAUDE.md §9.2: every tool carries an iteration bound, and each
  endpoint must count separately in the result metadata.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents import subagent
from app.agents import tools as tool_directives
from app.agents.base import AgentContext
from app.agents.prompts import TOOL_RULE_LINES
from app.agents.registry import get_domain_info, to_domain_info
from app.core.config import settings
from app.core.constants import (
    CUSTOM_API_ACTION_PREFIX,
    REPO_INTEL_ACTION,
    TOOL_IDS,
    LLMProvider,
)
from app.services import custom_api_service
from app.services.custom_api_service import CustomApiTool
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse
from app.services.service_key_service import ServiceCredentials


@pytest.fixture(autouse=True)
def _custom_api_tools_on(monkeypatch):
    """The feature ships off (CUSTOM_API_TOOLS_ENABLED=false, see config.py).

    These tests exercise it, so they opt in explicitly — which also keeps the
    one test that asserts the *disabled* behaviour honest, since it has to turn
    the switch back off itself.
    """
    monkeypatch.setattr(settings, "custom_api_tools_enabled", True)


NO_KEYS = ServiceCredentials()
FINAL_ANSWER = "Final answer."


def _tool(slug: str = "crm_lookup", tool_id: str = "t1", **overrides) -> CustomApiTool:
    base: dict[str, Any] = {
        "id": tool_id,
        "slug": slug,
        "name": f"Tool {slug}",
        "description": "Look something up.",
        "method": "GET",
        "base_url": "https://api.example.com",
        "path_template": "/v1/things/{thing_id}",
        "query_template": {},
        "headers": {},
        "auth_mode": "none",
        "auth_name": "",
        "parameters": [{"name": "thing_id", "type": "string", "required": True}],
        "body_template": None,
        "response_json_path": "",
        "response_max_chars": 8000,
        "timeout_seconds": 15,
        "secret": None,
    }
    return CustomApiTool(**{**base, **overrides})


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


def _directive(slug: str, **args) -> str:
    return json.dumps({"action": f"{CUSTOM_API_ACTION_PREFIX}{slug}", "args": args})


@pytest.fixture
def api_calls(monkeypatch) -> list[tuple[str, dict]]:
    """Replace the executor's service call, recording what it was asked to do."""
    calls: list[tuple[str, dict]] = []

    async def fake_call(tool: CustomApiTool, args: dict[str, str]) -> str:
        calls.append((tool.slug, dict(args)))
        return "<custom_api_result>\nfacts\n</custom_api_result>"

    monkeypatch.setattr(custom_api_service, "call", fake_call)
    return calls


async def _run(adapter: LLMAdapter, *, domain_info, **ctx_kwargs):
    events: list[tuple[Any, dict]] = []

    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append((event_type, payload))

    ctx = AgentContext(
        adapter=adapter, emit=emit, domain_info=domain_info, **ctx_kwargs
    )
    member = domain_info.team[0]
    result = await subagent.run_subtask(
        ctx, domain=domain_info.id, member=member, brief="Do the thing", index=0
    )
    return result, events


def _custom_domain(*tools: CustomApiTool):
    """A custom agent that has attached every one of ``tools``."""
    return to_domain_info(
        {
            "id": "agent-1",
            "name": "Custom Agent",
            "domain": "general",
            "system_prompt": "Do the thing.",
            "tools": [],
            "custom_api_tool_ids": [tool.id for tool in tools],
        },
        tools,
    )


# --- Registry: attaching an endpoint to an agent ---------------------------


def test_attached_endpoints_reach_the_domain_info() -> None:
    tool = _tool()
    info = _custom_domain(tool)
    assert info.tools == (f"{CUSTOM_API_ACTION_PREFIX}crm_lookup",), info.tools


def test_an_unattached_endpoint_is_not_offered() -> None:
    """Owning an endpoint is not the same as this agent using it."""
    info = to_domain_info(
        {
            "id": "agent-1",
            "name": "Custom Agent",
            "domain": "general",
            "system_prompt": "x",
            "tools": [],
            "custom_api_tool_ids": [],
        },
        (_tool(),),
    )
    assert info.tools == (), info.tools


def test_a_foreign_endpoint_id_never_matches() -> None:
    """The runtime backstop: tools are loaded per user, so a stray id resolves
    to nothing even if it somehow reached the document."""
    info = to_domain_info(
        {
            "id": "agent-1",
            "name": "Custom Agent",
            "domain": "general",
            "system_prompt": "x",
            "tools": [],
            "custom_api_tool_ids": ["someone-elses-id"],
        },
        (_tool(tool_id="t1"),),
    )
    assert info.tools == (), info.tools


def test_a_custom_action_is_never_a_catalog_tool_id() -> None:
    """TOOL_IDS is process-wide; a per-user id there would break three things."""
    assert f"{CUSTOM_API_ACTION_PREFIX}crm_lookup" not in TOOL_IDS


# --- resolve_enabled_tools -------------------------------------------------


async def test_an_attached_endpoint_is_enabled() -> None:
    tool = _tool()
    enabled = await tool_directives.resolve_enabled_tools(
        _custom_domain(tool), credentials=NO_KEYS, custom_api_tools=(tool,)
    )
    assert tool.action in enabled, sorted(enabled)


async def test_the_operator_switch_withholds_every_custom_endpoint(
    monkeypatch,
) -> None:
    tool = _tool()
    monkeypatch.setattr(settings, "custom_api_tools_enabled", False)
    enabled = await tool_directives.resolve_enabled_tools(
        _custom_domain(tool), credentials=NO_KEYS, custom_api_tools=(tool,)
    )
    assert tool.action not in enabled, sorted(enabled)


async def test_an_assignment_can_still_narrow_a_custom_endpoint_away() -> None:
    """A grant can only narrow — the same rule as every other tool."""
    tool = _tool()
    enabled = await tool_directives.resolve_enabled_tools(
        _custom_domain(tool),
        credentials=NO_KEYS,
        assigned=frozenset({REPO_INTEL_ACTION}),
        custom_api_tools=(tool,),
    )
    assert enabled == frozenset(), sorted(enabled)


async def test_an_endpoint_the_run_did_not_load_is_never_enabled() -> None:
    """The isolation property: the universe is widened only by loaded tools."""
    tool = _tool()
    enabled = await tool_directives.resolve_enabled_tools(
        _custom_domain(tool), credentials=NO_KEYS, custom_api_tools=()
    )
    assert enabled == frozenset(), sorted(enabled)


# --- specs_for and the two lookup tables -----------------------------------


def test_specs_for_merges_custom_endpoints() -> None:
    tool = _tool()
    specs = tool_directives.specs_for(
        frozenset({tool.action}), NO_KEYS, custom_api_tools=(tool,)
    )
    assert set(specs) == {tool.action}
    assert specs[tool.action].budget_attr == "max_custom_api_calls"


def test_each_endpoint_gets_its_own_metadata_key() -> None:
    """A shared key would have the last spec clobber every other tool's count."""
    first, second = _tool("alpha", "t1"), _tool("beta", "t2")
    specs = tool_directives.make_custom_api_tool_specs((first, second), budget=3)
    keys = {spec.metadata_key for spec in specs.values()}
    assert len(keys) == 2, keys


def test_a_custom_endpoint_has_a_native_function_schema() -> None:
    """Providers with native tool calling never see a tool without a schema."""
    tool = _tool()
    specs = tool_directives.make_custom_api_tool_specs((tool,), budget=3)
    defs = tool_directives.tool_defs_for(specs)
    assert len(defs) == 1
    assert defs[0].name == tool.action
    assert defs[0].parameters["properties"]["args"]["properties"], defs[0].parameters


def test_a_custom_endpoint_has_a_prompt_rule() -> None:
    """The analogue of the connected-tool rule test.

    A tool with no line is invisible to every model that is not using native
    function calling — it would be offered and never called.
    """
    tool = _tool()
    specs = tool_directives.make_custom_api_tool_specs((tool,), budget=3)
    line = tool_directives.rule_line_for(tool.action, specs[tool.action], 3)
    assert line, "a custom endpoint reached the loop with no usage rule"
    assert tool.action in line


def test_the_process_wide_tables_are_never_mutated() -> None:
    """Per-user data in a shared dict is a cross-user leak in a multi-worker
    server, which is why the schema and rule live on the spec instead."""
    before = dict(TOOL_RULE_LINES)
    tool_directives.make_custom_api_tool_specs((_tool(),), budget=3)
    assert TOOL_RULE_LINES == before
    assert not any(k.startswith(CUSTOM_API_ACTION_PREFIX) for k in TOOL_RULE_LINES)


def test_the_rule_line_is_never_run_through_format() -> None:
    """The line is built from user text; ``str.format`` over it would expose
    attribute traversal (``{0.__class__}``), not merely raise KeyError."""
    tool = _tool(name="Tool {0.__class__} {oops}")
    specs = tool_directives.make_custom_api_tool_specs((tool,), budget=3)
    line = tool_directives.rule_line_for(tool.action, specs[tool.action], 3)
    assert "{0.__class__}" in line, line


def test_the_rule_line_never_names_the_endpoint_host() -> None:
    tool = _tool()
    specs = tool_directives.make_custom_api_tool_specs((tool,), budget=3)
    line = tool_directives.rule_line_for(tool.action, specs[tool.action], 3)
    assert "api.example.com" not in line


def test_builtin_tools_still_read_their_rule_from_the_shared_table() -> None:
    """rule_line_for must not have changed behaviour for the built-ins."""
    specs = tool_directives.make_connected_tool_specs(NO_KEYS)
    for action, spec in specs.items():
        expected = TOOL_RULE_LINES[action].format(budget=4)
        assert tool_directives.rule_line_for(action, spec, 4) == expected


# --- parse_directive -------------------------------------------------------


def test_a_custom_directive_parses_when_enabled() -> None:
    tool = _tool()
    directive = tool_directives.parse_directive(
        _directive("crm_lookup", thing_id="42"), frozenset({tool.action})
    )
    assert directive is not None
    assert directive.action == tool.action
    assert directive.args == {"thing_id": "42"}


def test_a_custom_directive_is_a_final_answer_when_withheld() -> None:
    directive = tool_directives.parse_directive(
        _directive("crm_lookup", thing_id="42"), frozenset()
    )
    assert directive is None


def test_missing_args_still_parse_so_the_service_can_explain() -> None:
    """Returning None would make the loop read the JSON as the final answer;
    the service answers with a sentence the model can act on instead."""
    tool = _tool()
    directive = tool_directives.parse_directive(
        _directive("crm_lookup"), frozenset({tool.action})
    )
    assert directive is not None
    assert directive.args == {}


def test_nested_and_oversized_args_are_sanitized() -> None:
    tool = _tool()
    content = json.dumps(
        {
            "action": tool.action,
            "args": {"thing_id": "x" * 5000, "nested": {"a": 1}, "list": [1, 2]},
        }
    )
    directive = tool_directives.parse_directive(content, frozenset({tool.action}))
    assert directive is not None
    assert "nested" not in directive.args and "list" not in directive.args
    assert len(directive.args["thing_id"]) <= 500


# --- Inside the loop -------------------------------------------------------


async def test_the_loop_calls_the_endpoint_and_reports_its_usage(api_calls) -> None:  # noqa: ANN001
    tool = _tool()
    adapter = ScriptedAdapter([_directive("crm_lookup", thing_id="42"), FINAL_ANSWER])

    result, _ = await _run(
        adapter,
        domain_info=_custom_domain(tool),
        custom_api_tools=(tool,),
        user_id=None,
    )

    assert api_calls == [("crm_lookup", {"thing_id": "42"})], api_calls
    assert result.metadata["custom_api_crm_lookup_used"] == 1, result.metadata


async def test_the_budget_bounds_the_calls(api_calls) -> None:  # noqa: ANN001
    """CLAUDE.md §9.2: every tool carries an iteration bound."""
    tool = _tool()
    adapter = ScriptedAdapter([_directive("crm_lookup", thing_id="42")])

    await _run(
        adapter,
        domain_info=_custom_domain(tool),
        custom_api_tools=(tool,),
        max_custom_api_calls=2,
        user_id=None,
    )

    assert len(api_calls) == 2, f"budget of 2 allowed {len(api_calls)} calls"


async def test_two_endpoints_count_independently(api_calls) -> None:  # noqa: ANN001
    first, second = _tool("alpha", "t1"), _tool("beta", "t2")
    adapter = ScriptedAdapter(
        [
            _directive("alpha", thing_id="1"),
            _directive("beta", thing_id="2"),
            FINAL_ANSWER,
        ]
    )

    result, _ = await _run(
        adapter,
        domain_info=_custom_domain(first, second),
        custom_api_tools=(first, second),
        user_id=None,
    )

    assert result.metadata["custom_api_alpha_used"] == 1, result.metadata
    assert result.metadata["custom_api_beta_used"] == 1, result.metadata


async def test_the_prompt_offers_the_endpoint_by_name(api_calls) -> None:  # noqa: ANN001
    tool = _tool()
    adapter = ScriptedAdapter([FINAL_ANSWER])

    await _run(
        adapter,
        domain_info=_custom_domain(tool),
        custom_api_tools=(tool,),
        user_id=None,
    )

    system = adapter.calls[0][0].content
    assert tool.action in system, "the endpoint never reached the subagent prompt"
    assert "api.example.com" not in system, "the prompt named the endpoint's host"


async def test_the_event_stream_never_carries_the_arguments(api_calls) -> None:  # noqa: ANN001
    """Model-supplied argument values would otherwise land verbatim in the
    Architect payload."""
    tool = _tool()
    secretish = "an-argument-value-that-should-not-be-broadcast"
    adapter = ScriptedAdapter(
        [_directive("crm_lookup", thing_id=secretish), FINAL_ANSWER]
    )

    _, events = await _run(
        adapter,
        domain_info=_custom_domain(tool),
        custom_api_tools=(tool,),
        user_id=None,
    )

    assert secretish not in json.dumps([payload for _, payload in events], default=str)


def test_get_domain_info_is_untouched_by_custom_actions() -> None:
    """A built-in domain must not gain a custom action from anywhere."""
    for domain in ("software", "opensource", "general"):
        tools = get_domain_info(domain).tools
        assert not any(t.startswith(CUSTOM_API_ACTION_PREFIX) for t in tools), domain
