"""Phase A: the Main Agent assigns a tool subset to each subagent.

An assignment can only ever *narrow* a member's tool set — it is intersected
with the domain/switch/credential universe, never unioned. Absence of an
assignment (``None``) preserves the pre-assignment domain-global behaviour
byte-for-byte, which the backward-compat test below pins.
"""

from __future__ import annotations

import pytest

from app.agents import tools as tool_directives
from app.agents.main_agent import Assignment, _parse_assignments
from app.agents.registry import get_domain_info, to_domain_info
from app.agents.schemas import PlanAssignment
from app.core.constants import (
    DATA_FETCH_ACTION,
    DOCUMENT_SEARCH_ACTION,
    MEMORY_RECALL_ACTION,
    REPO_INTEL_ACTION,
    WEB_SEARCH_ACTION,
)

# ``searching`` declares web_search + data_fetch (+ the native summarize, which
# is not executable and so never reaches the enabled set).
DOMAIN = "searching"


async def test_resolve_unassigned_matches_domain_global() -> None:
    """``assigned=None`` yields exactly the domain-global enabled set."""
    baseline = await tool_directives.resolve_enabled_tools(DOMAIN)
    unassigned = await tool_directives.resolve_enabled_tools(DOMAIN, assigned=None)
    assert (
        unassigned == baseline == frozenset({WEB_SEARCH_ACTION, DATA_FETCH_ACTION})
    ), f"unassigned should equal domain-global, got {unassigned}"


async def test_assignment_narrows_to_subset() -> None:
    """An assignment restricts the member to the named subset."""
    enabled = await tool_directives.resolve_enabled_tools(
        DOMAIN, assigned=frozenset({WEB_SEARCH_ACTION})
    )
    assert enabled == frozenset({WEB_SEARCH_ACTION}), enabled


async def test_empty_assignment_grants_no_tools() -> None:
    """An explicit empty frozenset is a real grant of nothing, not unassigned."""
    enabled = await tool_directives.resolve_enabled_tools(DOMAIN, assigned=frozenset())
    assert enabled == frozenset(), enabled


async def test_assignment_cannot_widen_past_domain() -> None:
    """A tool the domain never declares can never be assigned into the set."""
    enabled = await tool_directives.resolve_enabled_tools(
        # code_execution is not in the searching domain's tools.
        DOMAIN,
        assigned=frozenset({WEB_SEARCH_ACTION, "code_execution"}),
    )
    assert enabled == frozenset({WEB_SEARCH_ACTION}), enabled


@pytest.mark.parametrize(
    "raw,expected",
    [
        (["web_search"], ["web_search"]),
        ("web_search", ["web_search"]),  # bare string — small models do this
        (None, []),  # null
        ("", []),  # empty string
    ],
)
def test_plan_assignment_tools_coercion(raw: object, expected: list[str]) -> None:
    """PlanAssignment coerces a bare string / null tools field into a list."""
    parsed = PlanAssignment(member="m", brief="b", tools=raw)
    assert parsed.tools == expected, parsed.tools


def test_parse_assignments_reads_tools_into_frozenset() -> None:
    """A planner-named tool list becomes the member's ``assigned_tools``."""
    team = get_domain_info(DOMAIN).team
    member_id = team[0].id
    proposed = [
        PlanAssignment(member=member_id, brief="do it", tools=["web_search"]),
    ]
    assignments = _parse_assignments(proposed, team, "prompt")
    match = next(a for a in assignments if a.member.id == member_id)
    assert match.assigned_tools == frozenset({"web_search"}), match.assigned_tools


def test_parse_assignments_no_tools_is_unassigned() -> None:
    """A member the planner named no tools for stays ``None`` (domain-global)."""
    team = get_domain_info(DOMAIN).team
    member_id = team[0].id
    proposed = [PlanAssignment(member=member_id, brief="do it")]
    assignments = _parse_assignments(proposed, team, "prompt")
    match = next(a for a in assignments if a.member.id == member_id)
    assert match.assigned_tools is None, match.assigned_tools


def test_assignment_default_is_none() -> None:
    """A freshly constructed Assignment is unassigned by default."""
    member = get_domain_info(DOMAIN).team[0]
    assert Assignment(member=member, brief="b").assigned_tools is None


# --- Custom agents: the resolved DomainInfo is the source of truth -----------


def _custom_doc(tools: list[str]) -> dict:
    """A stored custom-agent document declaring ``tools``."""
    return {
        "id": "abc123",
        "name": "Repo Watcher",
        "domain": "general",
        "system_prompt": "Watch a repository.",
        "tools": tools,
    }


async def test_custom_domain_info_keeps_its_declared_tools() -> None:
    """A custom agent's declared tools survive to the runtime set.

    Regression: ``resolve_enabled_tools`` used to take only the selector string.
    A ``custom:{id}`` selector has no catalog entry, so it fell back to
    ``general`` — whose tools are web_search/document_search/memory_recall — and
    the repo_intel this agent declared was silently withheld at execution while
    the planner (reading the same run's ``DomainInfo``) advertised it.
    """
    info = to_domain_info(_custom_doc([REPO_INTEL_ACTION]))
    enabled = await tool_directives.resolve_enabled_tools(info)
    # repo_intel is the keyless connected tool, so no credentials are needed.
    assert REPO_INTEL_ACTION in enabled, enabled
    # The ``general`` fallback's tools must not leak in: this agent declared none
    # of them, and their presence is exactly what the bug looked like.
    assert not enabled & {DOCUMENT_SEARCH_ACTION, MEMORY_RECALL_ACTION}, enabled


async def test_custom_domain_info_still_narrows_by_assignment() -> None:
    """The assignment gate applies to a DomainInfo exactly as to a selector."""
    info = to_domain_info(_custom_doc([REPO_INTEL_ACTION, WEB_SEARCH_ACTION]))
    enabled = await tool_directives.resolve_enabled_tools(
        info, assigned=frozenset({WEB_SEARCH_ACTION})
    )
    assert enabled == frozenset({WEB_SEARCH_ACTION}), enabled


async def test_domain_info_and_selector_agree_for_builtin_domains() -> None:
    """Passing the object or the string is identical for a catalog domain."""
    by_string = await tool_directives.resolve_enabled_tools(DOMAIN)
    by_object = await tool_directives.resolve_enabled_tools(get_domain_info(DOMAIN))
    assert by_object == by_string, (by_object, by_string)
