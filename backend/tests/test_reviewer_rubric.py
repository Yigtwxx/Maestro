"""Domain rubrics and producer context reach the reviewer prompt (no I/O)."""

from __future__ import annotations

from app.agents import reviewer
from app.agents.base import AgentContext, SubagentResult
from app.agents.domains.base import UNIVERSAL_CRITERIA
from app.agents.registry import get_domain_info
from app.core.constants import EventType, LLMProvider, SubagentStatus
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

APPROVE = '{"approved": true, "issues": [], "retry_hints": []}'


class CaptureAdapter(LLMAdapter):
    """Approves everything; records the messages it was sent."""

    provider = LLMProvider.OLLAMA

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[ChatMessage] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.messages = list(messages)
        return LLMResponse(content=APPROVE, model="fake", tokens_used=1)


def _result() -> SubagentResult:
    # A realistic deliverable that clears the deterministic pre-review validators
    # (non-trivial length + a fenced code block for the software domain), so the
    # reviewer's LLM path — what these tests exercise — actually runs.
    return SubagentResult(
        status=SubagentStatus.SUCCESS,
        data={"output": "Here is the implementation:\n```python\nprint('done')\n```"},
    )


async def test_review_domain_rubric_injected_into_system_prompt():
    adapter = CaptureAdapter()
    ctx = AgentContext(adapter=adapter)
    await reviewer.review(ctx, domain="software", subtask="s", result=_result())

    system = adapter.messages[0].content
    rubric = get_domain_info("software").review_rubric
    assert "Acceptance criteria:" in system, system
    assert rubric in system, "Software rubric missing from reviewer prompt"


async def test_review_without_domain_omits_domain_rubric_but_keeps_universal():
    adapter = CaptureAdapter()
    ctx = AgentContext(adapter=adapter)
    await reviewer.review(ctx, subtask="s", result=_result())

    system = adapter.messages[0].content
    software_rubric = get_domain_info("software").review_rubric
    assert software_rubric not in system, "A domain rubric leaked into this review"
    # The universal grounding criteria are not domain-scoped: they must be
    # scored even when the review carries no domain at all.
    for criterion in UNIVERSAL_CRITERIA:
        assert f"[{criterion.id}]" in system, f"{criterion.id} missing: {system}"


async def test_review_member_context_reaches_user_message():
    adapter = CaptureAdapter()
    ctx = AgentContext(adapter=adapter)
    member = get_domain_info("software").team[1]  # coder
    await reviewer.review(
        ctx, domain="software", subtask="s", result=_result(), member=member
    )

    user = adapter.messages[1].content
    assert f'Produced by "{member.name}"' in user, user


async def test_review_events_carry_subtask_index():
    events: list[tuple[EventType, dict]] = []

    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append((event_type, payload))

    ctx = AgentContext(adapter=CaptureAdapter(), emit=emit)
    await reviewer.review(
        ctx, domain="software", subtask="s", result=_result(), index=3
    )

    indexes = [p.get("index") for _, p in events]
    assert indexes == [3, 3], f"Both reviewer events must carry the index: {indexes}"


async def test_review_contract_asks_for_the_scores_the_gate_grades_on():
    """The JSON contract must request ``scores``, not just the criteria list.

    ``_criteria_block`` renders a scored checklist, but the authoritative
    "respond with a strict JSON object and nothing else" line used to specify
    only approved/issues/retry_hints. A model that obeyed the contract returned
    no scores, and ``_weighted_approved`` falls open to the boolean ``approved``
    when scores are absent — so every weighted threshold and every ``hard_fail``
    criterion silently did nothing.
    """
    adapter = CaptureAdapter()
    ctx = AgentContext(adapter=adapter)
    await reviewer.review(
        ctx, domain="opensource", subtask="s", result=_result(), member=None
    )

    system = adapter.messages[0].content
    contract = system.split("Respond with a strict JSON object")[-1]
    assert '"scores"' in contract, f"scores absent from the contract: {contract}"
    # The worked examples are what a small model actually copies, so a contract
    # that mentions scores but demonstrates output without them is still broken.
    examples = contract.split("Examples:")[-1]
    assert '"scores"' in examples, f"no example shows scores: {examples}"
    # And the hard-fail criterion whose enforcement this restores must be one of
    # the ids the reviewer was asked to score.
    assert "[data_coverage]" in system, system


async def test_weighted_gate_enforces_hard_fail_once_scores_arrive():
    """A zero on a hard_fail criterion rejects even when the model says approved.

    This is the behaviour the missing contract made unreachable; it is asserted
    directly so the gate cannot regress to fail-open without a test failing.
    """
    criteria = get_domain_info("opensource").review_criteria
    hard = next(c for c in criteria if c.hard_fail)
    full = UNIVERSAL_CRITERIA + criteria

    scores = {c.id: 2 for c in full}
    assert reviewer._weighted_approved(True, scores, full) is True

    scores[hard.id] = 0
    assert reviewer._weighted_approved(True, scores, full) is False, (
        f"{hard.id} is hard_fail; a zero must reject regardless of the boolean"
    )
