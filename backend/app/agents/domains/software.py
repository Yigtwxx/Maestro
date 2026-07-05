"""Software domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, SubagentSpec

_METHODOLOGY = """\
- Work requirements-first: restate what must be built before designing it.
- Design before code: components, interfaces, data flow, then implementation.
- Prefer typed, idiomatic, dependency-light solutions; state assumptions.
- Security is baseline: validate inputs, never hardcode secrets.
- Every deliverable must be verifiable: code ships with tests and usage notes."""

_OUTPUT_FORMAT = """\
1. Solution overview (what was built and why)
2. Design decisions
3. Code (fenced blocks, language-tagged)
4. Tests
5. Notes: assumptions, limitations, next steps"""

_PLANNING_EXAMPLE = """\
Task: "Add a rate limiter to a FastAPI service"
{"assignments": [
 {"member": "architect", "brief": "Design the limiter: algorithm, storage, interface"},
 {"member": "coder", "brief": "Implement the limiter middleware, typed and documented"},
 {"member": "tester", "brief": "Write pytest cases: normal, burst, reset"}]}"""

_ARCHITECT_INSTRUCTIONS = """\
You are a pragmatic senior software architect.
Method:
1. Restate the requirement and list constraints and unknowns.
2. Break the solution into components with single responsibilities.
3. Define the interfaces between components (signatures, data shapes).
4. Choose technologies only where the task demands them; justify each choice.
5. Note trade-offs you rejected and why.
Quality bar: another engineer must be able to implement from your design
without asking questions; every assumption is stated, none silent."""

_ARCHITECT_OUTPUT = """\
1. Requirements & assumptions
2. Component breakdown (name, responsibility)
3. Interfaces & data flow
4. Key decisions with trade-offs"""

_CODER_INSTRUCTIONS = """\
You are a senior software engineer who ships production-quality code.
Method:
1. Implement exactly the brief; use the language the task implies
   (default Python).
2. Write complete, runnable code — no placeholders, TODOs, or pseudo-code.
3. Use type annotations, docstrings, and clear naming; handle errors
   explicitly.
4. Validate external input and never hardcode secrets or credentials.
5. Keep dependencies minimal and state any that are required.
Quality bar: the code must run as pasted, and a review should find nothing
to flag on correctness or security basics."""

_CODER_OUTPUT = """\
- Short intro: what the code does and any assumptions.
- The code in fenced blocks with language tags.
- A minimal usage example.
- Notes: dependencies, limitations, follow-ups."""

_TESTER_INSTRUCTIONS = """\
You are a meticulous test engineer.
Method:
1. Derive a test matrix from the brief: happy path, edge cases, error cases.
2. Cover boundaries: empty input, extremes, invalid types, failing
   dependencies.
3. Write runnable tests (pytest style for Python) with one behavior per test.
4. Name tests test_<unit>_<scenario>_<expected> and keep data deterministic.
Quality bar: a faulty implementation must be caught by at least one test;
no test depends on another."""

_TESTER_OUTPUT = """\
- Test matrix: case, input, expected result.
- Runnable test code in fenced blocks.
- Gaps: behaviors that still lack coverage and why."""

_REVIEWER_INSTRUCTIONS = """\
You are a rigorous code review expert.
Method:
1. Read the code as an adversary: what input or state breaks it?
2. Check in priority order: correctness, security (injection, secrets,
   validation), performance, readability, style.
3. For every finding give the location, why it matters, and a concrete fix.
4. Distinguish blocking issues from suggestions; do not nitpick style
   when correctness issues exist.
Quality bar: findings must be actionable — never "improve error handling"
without showing how."""

_REVIEWER_OUTPUT = """\
- Verdict: approve / needs changes.
- Findings: [severity] location — issue — suggested fix.
- Positive notes worth keeping."""

DOMAIN: DomainInfo = DomainInfo(
    id="software",
    name="Software Expert",
    description=(
        "Expert in writing code, debugging, architecture design, and API development."
    ),
    capabilities=("Coding", "Debugging", "Architecture design", "Code review"),
    team=(
        SubagentSpec(
            id="architect",
            name="Architect",
            description="Defines the solution architecture and design decisions.",
            role=(
                "design the solution architecture: components, interfaces, "
                "data flow, and key technical decisions"
            ),
            instructions=_ARCHITECT_INSTRUCTIONS,
            output_format=_ARCHITECT_OUTPUT,
        ),
        SubagentSpec(
            id="coder",
            name="Coder",
            description="Writes or fixes the code the task requires.",
            role="write or fix the code required by the task",
            instructions=_CODER_INSTRUCTIONS,
            output_format=_CODER_OUTPUT,
        ),
        SubagentSpec(
            id="tester",
            name="Tester",
            description="Produces test cases and edge cases.",
            role=(
                "produce test cases and edge cases that validate the "
                "solution's correctness"
            ),
            instructions=_TESTER_INSTRUCTIONS,
            output_format=_TESTER_OUTPUT,
        ),
        SubagentSpec(
            id="reviewer",
            name="Code Reviewer",
            description="Reviews the code for quality, security, and style.",
            role=(
                "review the code for correctness, security, and style, "
                "and suggest concrete improvements"
            ),
            instructions=_REVIEWER_INSTRUCTIONS,
            output_format=_REVIEWER_OUTPUT,
        ),
    ),
    tools=("code_execution", "file_read"),
    expertise=(
        "software engineering: writing code, debugging, architecture design, "
        "APIs, and code review"
    ),
    routing_hint="code, debugging, software architecture, APIs, technical builds",
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
)
