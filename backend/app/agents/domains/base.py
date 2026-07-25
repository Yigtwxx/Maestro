"""Shared dataclasses for built-in domain agent definitions.

Kept separate from the domain modules and the registry so each domain module
can import these types without circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import (
    NOT_FOUND_PREFIX,
    UNCERTAINTY_CLOSE,
    UNCERTAINTY_OPEN,
)


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
class ReviewCriterion:
    """One weighted acceptance criterion for structured review (Backend v2 §4.6).

    The reviewer scores each 0-2; approval is a weighted threshold. A
    ``hard_fail`` criterion scored 0 rejects regardless of the weighted total.
    """

    id: str
    description: str
    weight: int = 1
    hard_fail: bool = False


# Prepended to every domain's ``review_criteria`` by the reviewer, so grounding
# is judged in all domains rather than only the five that happen to declare
# criteria of their own. Deliberately not ``hard_fail``: on a small local model
# the 0-2 scores are noisy, and a single mis-scored criterion rejecting an
# otherwise good deliverable costs a full retry.
#
# Both descriptions state the "everything was sourced" case explicitly. Without
# that, a clean output with nothing to mark reads as failing the criterion and
# scores 0.
UNIVERSAL_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="sourced_specifics",
        description=(
            "Every date, number, name, version and URL is either traceable to "
            "the provided context or a tool result, marked as uncertain with "
            f"{UNCERTAINTY_OPEN} ... {UNCERTAINTY_CLOSE}, or reported on a "
            f'"{NOT_FOUND_PREFIX}" line. An output that sourced everything it '
            "states meets this criterion."
        ),
    ),
    ReviewCriterion(
        id="uncertainty_marked",
        description=(
            "Inference is presented as inference, not as measurement: guessed "
            "spans are marked and sourced facts are left unmarked. An output "
            "with nothing to guess at, or one that openly reports what it could "
            "not find, meets this criterion."
        ),
    ),
)


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
    # Optional structured criteria (Backend v2 §4.6). When set, the reviewer also
    # renders them as a scored checklist and computes a weighted approval; when
    # empty, the string ``review_rubric`` path above is used unchanged.
    review_criteria: tuple[ReviewCriterion, ...] = ()
