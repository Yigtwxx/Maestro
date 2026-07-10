"""Shared dataclasses for built-in domain agent definitions.

Kept separate from the domain modules and the registry so each domain module
can import these types without circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubagentSpec:
    """A fixed team member of a domain agent."""

    id: str
    # English display name; the frontend localizes it for the UI.
    name: str
    description: str
    # English prompt fragment: the member's specialization, injected into the
    # subagent system prompt and the Main Agent's team roster.
    role: str
    # Multi-line prompt block: expertise persona, working methodology and
    # quality bar. Injected only into this member's subagent system prompt.
    instructions: str = ""
    # Deliverable structure this member's output must follow.
    output_format: str = ""


@dataclass(frozen=True)
class DomainInfo:
    """A built-in domain agent (Main Agent) definition."""

    id: str
    # English display name; the frontend localizes it for the UI.
    name: str
    description: str
    capabilities: tuple[str, ...]
    # The fixed subagent team the Main Agent manages (never invented per task).
    team: tuple[SubagentSpec, ...]
    # Declared tool ids from ``TOOL_CATALOG``. Ids in ``EXECUTABLE_TOOL_IDS``
    # (web_search, data_fetch, code_execution) are executed via the subagent
    # directive loop; the rest are declared metadata for this tier.
    tools: tuple[str, ...]
    # English prompt fragments (all system prompts are English).
    expertise: str
    routing_hint: str
    # Domain working principles injected into the Main Agent planning prompt.
    methodology: str = ""
    # Final deliverable structure injected into the synthesis prompt.
    output_format: str = ""
    # Compact one-shot planning example (task + assignments JSON with real
    # member ids) injected into the Main Agent planning prompt; teaches small
    # models the exact id vocabulary and JSON shape.
    planning_example: str = ""
    # Domain-specific acceptance criteria injected into the Reviewer prompt
    # (3-6 concrete, checkable bullets).
    review_rubric: str = ""
