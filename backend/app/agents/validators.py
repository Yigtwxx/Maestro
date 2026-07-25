"""Deterministic pre-review validators (Backend v2 §4.6).

Cheap, LLM-free checks the Reviewer runs *before* its model call. A failure
short-circuits the review with synthetic retry hints — an obviously deficient
output (empty, missing its declared sections, no JSON where JSON is required)
is rejected without spending a review iteration's LLM round-trip.

Validators are pure and synchronous. Each returns a retry-hint string when the
output fails its check, else ``None``. They are conservative by design: a check
only fires on an unambiguous miss, so a good output is never wrongly rejected.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.agents.base import extract_json
from app.agents.domains.base import SubagentSpec
from app.core.constants import (
    REVIEW_MIN_OUTPUT_CHARS,
    UNCERTAINTY_CLOSE,
    UNCERTAINTY_OPEN,
)

# Fenced blocks and inline spans, stripped before counting uncertainty markers:
# ``[?`` is ordinary regex syntax (a character class) and a software deliverable
# that contains one is correct, not malformed.
_CODE_SPAN_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)

Validator = Callable[[str, "SubagentSpec | None"], "str | None"]


def nonempty_min_length(output: str, member: SubagentSpec | None) -> str | None:
    """Fail an empty or trivially short deliverable."""
    if len(output.strip()) < REVIEW_MIN_OUTPUT_CHARS:
        return (
            "The output is empty or too short to be a complete deliverable; "
            "produce the full result your brief asks for."
        )
    return None


def output_format_sections_present(
    output: str, member: SubagentSpec | None
) -> str | None:
    """Fail when the member declared ``Label:`` sections and none appear.

    Only explicit ``Something:`` labels count, and the check fires only when the
    output contains *none* of them — a deliberately low-false-positive rule.
    """
    if member is None or not member.output_format.strip():
        return None
    labels = [
        line.split(":", 1)[0].strip()
        for line in member.output_format.splitlines()
        if line.strip().endswith(":") or ":" in line
    ]
    labels = [label for label in labels if label]
    if not labels:
        return None
    lowered = output.lower()
    if any(label.lower() in lowered for label in labels):
        return None
    return (
        "The output does not follow the required structure; include the "
        f"declared sections: {', '.join(labels[:6])}."
    )


def uncertainty_markers_balanced(
    output: str, member: SubagentSpec | None
) -> str | None:
    """Fail an output that opens an uncertainty marker and never closes it.

    An unclosed marker reaches the user as literal ``[?`` in the rendered answer
    and leaves the guess it was meant to flag unmarked — the exact failure the
    marker exists to prevent. Only the open-without-close direction fires; a
    stray close is harmless punctuation.
    """
    prose = _CODE_SPAN_RE.sub("", output)
    if prose.count(UNCERTAINTY_OPEN) <= prose.count(UNCERTAINTY_CLOSE):
        return None
    return (
        f"An uncertainty marker was opened with {UNCERTAINTY_OPEN} but never "
        f"closed with {UNCERTAINTY_CLOSE}; close every marker you open, or drop "
        "it if the statement is sourced."
    )


def json_parses(output: str, member: SubagentSpec | None) -> str | None:
    """Fail a data-domain output that carries no parseable JSON object."""
    try:
        extract_json(output)
    except ValueError:
        return (
            "No parseable JSON object was found in the output; return the data "
            "as a valid JSON object."
        )
    return None


def code_blocks_present(output: str, member: SubagentSpec | None) -> str | None:
    """Fail a software-domain output that contains no fenced code block."""
    if "```" not in output:
        return (
            "The output contains no fenced code block; include the code inside a "
            "```language ... ``` block."
        )
    return None


# Run on every review, regardless of domain. Deliberately conservative: only
# checks that fire on an *unambiguous* miss are wired, so a good free-form
# deliverable is never wrongly rejected. ``output_format_sections_present`` is
# intentionally left out of the active set — matching declared "Label:" headings
# against a paraphrased-but-correct deliverable is too false-positive-prone; it
# stays defined for a future structured-output-format contract.
UNIVERSAL_VALIDATORS: tuple[Validator, ...] = (
    nonempty_min_length,
    uncertainty_markers_balanced,
)

# Extra checks keyed by domain id.
DOMAIN_VALIDATORS: dict[str, tuple[Validator, ...]] = {
    "data": (json_parses,),
    "software": (code_blocks_present,),
}


def validate(domain: str, member: SubagentSpec | None, output: str) -> list[str]:
    """Return every failing validator's retry hint (empty when all pass)."""
    checks = UNIVERSAL_VALIDATORS + DOMAIN_VALIDATORS.get(domain, ())
    hints = [hint for check in checks if (hint := check(output, member)) is not None]
    return hints
