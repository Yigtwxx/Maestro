"""Domain rubrics and producer context reach the reviewer prompt (no I/O)."""

from __future__ import annotations

from app.agents import reviewer
from app.agents.base import AgentContext, SubagentResult
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
    assert "Domain-specific review criteria:" in system, system
    assert rubric in system, "Software rubric missing from reviewer prompt"


async def test_review_without_domain_omits_rubric_header():
    adapter = CaptureAdapter()
    ctx = AgentContext(adapter=adapter)
    await reviewer.review(ctx, subtask="s", result=_result())

    system = adapter.messages[0].content
    assert "Domain-specific review criteria:" not in system, system


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
