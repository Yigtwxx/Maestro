"""Connected-API tools inside the subagent directive loop.

Three things are load-bearing here and none is obvious from the services alone:

* **The availability gate.** A tool whose credential is missing must not reach
  the prompt at all — offering it guarantees a wasted tool call, the same
  reasoning ``code_execution`` already uses for Docker. ``repo_intel`` is the
  deliberate exception: GitHub serves anonymous reads.
* **The event payload.** The Architect rail cannot draw a live edge without
  ``done`` (the two events per call otherwise differ only in prose) or place it
  without ``provider``.
* **Directive parsing.** A required arg missing means "not a tool call"; a bad
  optional arg must degrade instead, because returning None makes the loop read
  the JSON as the subagent's final answer.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents import subagent
from app.agents import tools as tool_directives
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info
from app.core.constants import (
    COMMUNITY_READ_ACTION,
    PLACES_INTEL_ACTION,
    REPO_INTEL_ACTION,
    SOCIAL_SEARCH_ACTION,
    LLMProvider,
)
from app.services import (
    community_read_service,
    places_intel_service,
    repo_intel_service,
    social_search_service,
)
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse
from app.services.service_key_service import ServiceCredentials

OSS_DOMAIN = "opensource"  # declares repo_intel
SOCIAL_DOMAIN = "social"  # declares social_search
COMMUNITY_DOMAIN = "community"  # declares community_read
LOCAL_DOMAIN = "local"  # declares places_intel

REPO_DIRECTIVE = json.dumps(
    {"action": "repo_intel", "repo": "psf/requests", "aspect": "activity"}
)
FINAL_ANSWER = "Final answer."

GITHUB_KEY = ServiceCredentials({"github": "gh-token"})
X_KEY = ServiceCredentials({"x": "x-token"})
NO_KEYS = ServiceCredentials()


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


@pytest.fixture
def repo_calls(monkeypatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def fake_fetch(repo: str, *, aspect: str, credentials: Any) -> str:
        calls.append((repo, aspect))
        return "<repo_intel_result>\nfacts\n</repo_intel_result>"

    monkeypatch.setattr(repo_intel_service, "fetch", fake_fetch)
    return calls


async def _run(adapter: LLMAdapter, *, domain: str, **ctx_kwargs):
    events: list[tuple[Any, dict]] = []

    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append((event_type, payload))

    ctx = AgentContext(adapter=adapter, emit=emit, **ctx_kwargs)
    member = get_domain_info(domain).team[0]
    result = await subagent.run_subtask(
        ctx, domain=domain, member=member, brief="Do the thing", index=0
    )
    return result, events


# --- availability gate -----------------------------------------------------


async def test_repo_intel_is_offered_without_any_credential():
    """The keyless exception: GitHub serves anonymous reads at 60/hour."""
    enabled = await tool_directives.resolve_enabled_tools(
        OSS_DOMAIN, credentials=NO_KEYS
    )

    assert REPO_INTEL_ACTION in enabled, (
        f"repo_intel must survive a missing key, got {sorted(enabled)}"
    )


@pytest.mark.parametrize(
    ("domain", "action"),
    [
        (SOCIAL_DOMAIN, SOCIAL_SEARCH_ACTION),
        (COMMUNITY_DOMAIN, COMMUNITY_READ_ACTION),
        (LOCAL_DOMAIN, PLACES_INTEL_ACTION),
    ],
)
async def test_a_credentialed_tool_is_withheld_without_its_key(domain, action):
    enabled = await tool_directives.resolve_enabled_tools(domain, credentials=NO_KEYS)

    assert action not in enabled, (
        f"{action} must be withheld with no key, got {sorted(enabled)}"
    )
    assert "web_search" in enabled, (
        f"The squad must still work from web_search, got {sorted(enabled)}"
    )


async def test_a_credentialed_tool_is_offered_once_its_key_exists():
    enabled = await tool_directives.resolve_enabled_tools(
        SOCIAL_DOMAIN, credentials=X_KEY
    )

    assert SOCIAL_SEARCH_ACTION in enabled, (
        f"A stored X key must unlock social_search, got {sorted(enabled)}"
    )


@pytest.mark.parametrize("platform", ["discord", "slack", "telegram"])
async def test_community_read_needs_only_one_connected_platform(platform):
    enabled = await tool_directives.resolve_enabled_tools(
        COMMUNITY_DOMAIN, credentials=ServiceCredentials({platform: "token"})
    )

    assert COMMUNITY_READ_ACTION in enabled, (
        f"Any one platform should enable the tool, {platform} did not"
    )


async def test_disabled_setting_withholds_the_tool_even_with_a_key(monkeypatch):
    """The per-tool rollback switch must beat a present credential."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "repo_intel_enabled", False)

    enabled = await tool_directives.resolve_enabled_tools(
        OSS_DOMAIN, credentials=GITHUB_KEY
    )

    assert REPO_INTEL_ACTION not in enabled, "A disabled tool must never be offered"


async def test_withheld_tool_is_not_callable_from_the_subagent_prompt():
    """Gating only pays off if the model is never taught the call shape.

    The member's own instructions may still *mention* the tool by name — they
    are written conditionally ("if it is among your tools") — but the directive
    form must be absent, since that is what the model copies.
    """
    adapter = ScriptedAdapter([FINAL_ANSWER])

    await _run(adapter, domain=SOCIAL_DOMAIN, service_credentials=NO_KEYS)

    system_prompt = adapter.calls[0][0].content
    assert f'"action": "{SOCIAL_SEARCH_ACTION}"' not in system_prompt, (
        f"A withheld tool must not be callable: {system_prompt}"
    )
    assert '"action": "web_search"' in system_prompt, (
        "The squad must still be taught its fallback tool"
    )


async def test_offered_tool_appears_in_the_subagent_prompt(repo_calls):
    """The mirror case — a missing TOOL_RULE_LINES entry fails silently."""
    adapter = ScriptedAdapter([FINAL_ANSWER])

    await _run(adapter, domain=OSS_DOMAIN, service_credentials=GITHUB_KEY)

    system_prompt = adapter.calls[0][0].content
    assert f'"action": "{REPO_INTEL_ACTION}"' in system_prompt, (
        f"An enabled tool must be taught to the model: {system_prompt}"
    )


# --- execution and events --------------------------------------------------


async def test_repo_intel_directive_round_trips_into_the_next_call(repo_calls):
    adapter = ScriptedAdapter([REPO_DIRECTIVE, FINAL_ANSWER])

    result, _ = await _run(adapter, domain=OSS_DOMAIN, service_credentials=GITHUB_KEY)

    assert repo_calls == [("psf/requests", "activity")], (
        f"The directive args must reach the service, got {repo_calls}"
    )
    assert result.metadata["repo_lookups_used"] == 1, (
        f"Per-tool usage must be metered: {result.metadata}"
    )
    fed_back = adapter.calls[1][-1].content
    assert "repo_intel_result" in fed_back, "The result must return to the model"


async def test_tool_events_carry_done_and_provider(repo_calls):
    """Without these two fields the canvas rail cannot draw a live edge."""
    adapter = ScriptedAdapter([REPO_DIRECTIVE, FINAL_ANSWER])

    _, events = await _run(adapter, domain=OSS_DOMAIN, service_credentials=GITHUB_KEY)

    tool_events = [p for _, p in events if p.get("action") == REPO_INTEL_ACTION]
    assert len(tool_events) == 2, f"One start and one completion, got {tool_events}"
    assert [e["done"] for e in tool_events] == [False, True], (
        f"The pair must be distinguishable on the wire: {tool_events}"
    )
    assert {e["provider"] for e in tool_events} == {LLMProvider.GITHUB.value}, (
        f"Every event must name its provider: {tool_events}"
    )
    assert tool_events[0]["repo"] == "psf/requests", (
        f"The event_arg must be surfaced: {tool_events[0]}"
    )


async def test_community_read_reports_the_platform_as_its_provider():
    """This tool's provider is chosen per call, not fixed by the registry."""
    specs = tool_directives.make_connected_tool_specs(NO_KEYS)
    directive = tool_directives.ToolDirective(
        COMMUNITY_READ_ACTION, {"platform": "slack", "channel": "C1", "window": "7d"}
    )

    provider_of = specs[COMMUNITY_READ_ACTION].provider_of

    assert provider_of is not None, "community_read must declare a provider resolver"
    assert provider_of(directive) == "slack", (
        "The platform argument is the provider for this tool"
    )


async def test_keyless_tools_declare_no_provider():
    """web_search and data_fetch get no rail lane, by design."""
    for action, spec in tool_directives.TOOL_SPECS.items():
        assert spec.provider_of is None, (
            f"{action} is keyless and must not claim a rail lane"
        )


async def test_repo_lookup_budget_is_enforced(repo_calls):
    adapter = ScriptedAdapter([REPO_DIRECTIVE, REPO_DIRECTIVE, FINAL_ANSWER])

    await _run(
        adapter,
        domain=OSS_DOMAIN,
        service_credentials=GITHUB_KEY,
        max_repo_lookups=1,
        max_tool_calls=5,
    )

    assert len(repo_calls) == 1, f"The per-tool budget must bind, got {repo_calls}"


# --- directive parsing -----------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected_aspect"),
    [
        ({"repo": "a/b"}, "profile"),
        ({"repo": "a/b", "aspect": "issues"}, "issues"),
        ({"repo": "a/b", "aspect": "NONSENSE"}, "profile"),
        ({"repo": "a/b", "aspect": "RELEASES"}, "releases"),
    ],
)
def test_parse_directive_repo_intel_aspect_degrades_instead_of_failing(
    payload, expected_aspect
):
    """A bad optional arg must not turn the directive into a final answer."""
    content = json.dumps({"action": REPO_INTEL_ACTION, **payload})

    directive = tool_directives.parse_directive(content, frozenset({REPO_INTEL_ACTION}))

    assert directive is not None, f"The directive must survive: {content}"
    assert directive.args["aspect"] == expected_aspect, (
        f"Expected {expected_aspect}, got {directive.args['aspect']}"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"platform": "discord"},  # no channel
        {"channel": "123"},  # no platform
        {"platform": "reddit", "channel": "123"},  # unsupported platform
    ],
)
def test_parse_directive_community_read_requires_both_platform_and_channel(payload):
    """Neither has a safe default — guessing would read the wrong community."""
    content = json.dumps({"action": COMMUNITY_READ_ACTION, **payload})

    directive = tool_directives.parse_directive(
        content, frozenset({COMMUNITY_READ_ACTION})
    )

    assert directive is None, f"Incomplete directive must be rejected: {content}"


@pytest.mark.parametrize("window", ["24h", "30d", "nonsense", "", None])
def test_parse_directive_normalizes_the_lookback_window(window):
    content = json.dumps(
        {"action": SOCIAL_SEARCH_ACTION, "query": "pricing", "window": window}
    )

    directive = tool_directives.parse_directive(
        content, frozenset({SOCIAL_SEARCH_ACTION})
    )

    assert directive is not None, "A bad window must not kill the directive"
    assert directive.args["window"] in {"24h", "7d", "30d"}, (
        f"Window must normalize, got {directive.args['window']}"
    )


def test_parse_directive_places_intel_keeps_an_optional_location():
    content = json.dumps(
        {"action": PLACES_INTEL_ACTION, "query": "coffee", "location": "Kadikoy"}
    )

    directive = tool_directives.parse_directive(
        content, frozenset({PLACES_INTEL_ACTION})
    )

    assert directive is not None, "The directive must parse"
    assert directive.args["location"] == "Kadikoy", (
        f"Location must be preserved: {directive.args}"
    )


def test_parse_directive_rejects_a_connected_tool_that_is_not_enabled():
    """A withheld tool's directive must read as a final answer, not a call."""
    content = json.dumps({"action": SOCIAL_SEARCH_ACTION, "query": "pricing"})

    directive = tool_directives.parse_directive(content, frozenset({REPO_INTEL_ACTION}))

    assert directive is None, "A disabled action must never parse as a directive"


def test_every_connected_tool_has_a_prompt_rule():
    """A tool missing from TOOL_RULE_LINES is silently invisible to the model."""
    from app.agents.prompts import TOOL_RULE_LINES

    specs = tool_directives.make_connected_tool_specs(NO_KEYS)
    missing = set(specs) - set(TOOL_RULE_LINES)

    assert not missing, f"Connected tools with no prompt rule: {sorted(missing)}"


def test_every_connected_tool_has_a_native_function_schema():
    """Providers with native tool calling never see a tool without a schema."""
    specs = tool_directives.make_connected_tool_specs(NO_KEYS)
    defs = tool_directives.tool_defs_for(specs)

    assert len(defs) == len(specs), f"Expected one ToolDef per spec, got {len(defs)}"
    for definition in defs:
        assert definition.parameters.get("properties"), (
            f"{definition.name} has an empty parameter schema"
        )


async def test_services_are_untouched_when_no_directive_is_issued(monkeypatch):
    """A squad that never calls out must not reach any provider."""
    touched: list[str] = []
    for module, name in (
        (social_search_service, "social"),
        (community_read_service, "community"),
        (places_intel_service, "places"),
    ):

        async def fake(*args: Any, _name: str = name, **kwargs: Any) -> str:
            touched.append(_name)
            return ""

        monkeypatch.setattr(module, "fetch", fake)

    await _run(
        ScriptedAdapter([FINAL_ANSWER]),
        domain=SOCIAL_DOMAIN,
        service_credentials=X_KEY,
    )

    assert touched == [], f"No provider may be contacted, touched {touched}"
