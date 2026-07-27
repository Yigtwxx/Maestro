"""Subagent: a fixed team member executing one briefed subtask via the LLM.

Subagents in domains that declare executable tools (web_search, data_fetch,
code_execution) can request them through a provider-agnostic JSON directive
loop (no native function calling required): the model replies with a directive
instead of an answer, we execute the tool and feed the result back, bounded by
per-tool budgets and a total tool-call cap.

A subagent executes the Main Agent's decomposed brief, plus (when dependencies
were declared) the finished outputs of the teammates it builds on. The user's
request travels alongside as *delimited context*, never as the member's own
instruction — the brief is what it executes, and the prompt says so before the
request is shown.

That request used to be available only on demand, behind the
``view_original_request`` directive. Small local models do not issue it: they
answer the brief without ever learning what was asked, which produced fluent,
confidently off-topic deliverables whenever planning had degraded, and left the
member with no way to know what language to reply in — every prompt and every
planner-written brief is English. The directive is still registered, and is
still how a request too long to embed gets read in full.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agents import budget
from app.agents import tools as tool_directives
from app.agents.base import (
    AgentContext,
    SubagentResult,
    format_memory_block,
    format_optional_block,
    truncate_text,
    with_current_date,
)
from app.agents.prompts import (
    SUBAGENT_EMPTY_ANSWER_NUDGE,
    SUBAGENT_NO_RETRIEVAL_NUDGE,
    SUBAGENT_OBJECTIVE_HEADER,
    SUBAGENT_SYSTEM,
    SUBAGENT_TOOLS_RULE,
    SUBAGENT_UPSTREAM_HEADER,
    TOOL_RULE_LINES,
)
from app.agents.registry import SubagentSpec
from app.agents.tools import ToolDirective, ToolSpec
from app.core.constants import (
    COMPACTION_KEEP_CHARS,
    COMPACTION_THRESHOLD_TOKENS,
    EMPTY_SUBAGENT_ANSWER,
    OBJECTIVE_MAX_CHARS,
    ORIGINAL_REQUEST_CLOSE,
    ORIGINAL_REQUEST_OPEN,
    RETRIEVAL_TOOL_IDS,
    SUBAGENT_MAX_TOKENS,
    SUBAGENT_SUMMARY_MAX_CHARS,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
    UPSTREAM_OUTPUT_MAX_CHARS,
    VIEW_ORIGINAL_REQUEST_ACTION,
    AgentRole,
    EventType,
    SubagentStatus,
)
from app.services.llm_service import ChatMessage, LLMError, LLMResponse

logger = logging.getLogger(__name__)


def _format_upstream(upstream: list[tuple[str, str]]) -> str:
    """Render teammates' outputs, each capped so small models keep headroom."""
    sections = [
        f"--- {name} ---\n{truncate_text(output.strip(), UPSTREAM_OUTPUT_MAX_CHARS)}"
        for name, output in upstream
        if output.strip()
    ]
    return "\n".join(sections)


def _tool_budget(ctx: AgentContext, action: str, specs: dict[str, ToolSpec]) -> int:
    spec = specs.get(action)
    return getattr(ctx, spec.budget_attr) if spec else 0


def _tools_rule(ctx: AgentContext, specs: dict[str, ToolSpec]) -> str:
    """Compose the tools prompt rule from this run's available directives."""
    lines = [
        TOOL_RULE_LINES[action].format(budget=_tool_budget(ctx, action, specs))
        for action in sorted(specs)
        if action in TOOL_RULE_LINES
    ]
    if not lines:
        return ""
    return SUBAGENT_TOOLS_RULE.format(
        tool_lines="\n".join(lines), max_tool_calls=ctx.max_tool_calls
    )


async def run_subtask(
    ctx: AgentContext,
    *,
    domain: str,
    member: SubagentSpec,
    brief: str,
    index: int,
    review_hints: list[str] | None = None,
    objective: str = "",
    upstream: list[tuple[str, str]] | None = None,
    assigned_tools: frozenset[str] | None = None,
) -> SubagentResult:
    """Execute one brief as a team member, wrapped in an ``agent:{id}`` trace
    span (Backend v2 §4.5). The span records failure without raising: a subtask
    error is returned as a structured result, so the span is flagged here."""
    from app.core.constants import SpanKind, SpanStatus
    from app.utils import tracing

    async with tracing.tracer.span(
        f"agent:{member.id}",
        SpanKind.AGENT,
        **{
            "maestro.role": AgentRole.SUBAGENT.value,
            "maestro.member_id": member.id,
            "maestro.domain": domain,
            "maestro.index": index,
        },
    ) as span:
        result = await _run_subtask(
            ctx,
            domain=domain,
            member=member,
            brief=brief,
            index=index,
            review_hints=review_hints,
            objective=objective,
            upstream=upstream,
            assigned_tools=assigned_tools,
        )
        if result.status == SubagentStatus.ERROR:
            span.set_status(
                SpanStatus.ERROR.value, str(result.data.get("error", ""))[:200]
            )
        return result


async def _run_subtask(
    ctx: AgentContext,
    *,
    domain: str,
    member: SubagentSpec,
    brief: str,
    index: int,
    review_hints: list[str] | None = None,
    objective: str = "",
    upstream: list[tuple[str, str]] | None = None,
    assigned_tools: frozenset[str] | None = None,
) -> SubagentResult:
    """Execute one brief as a team member; structured result (CLAUDE.md §5.4)."""
    hints_block = ""
    if review_hints:
        hints_block = "Address this reviewer feedback:\n- " + "\n- ".join(review_hints)

    await ctx.emit(
        EventType.NODE_UPDATE,
        {
            "role": AgentRole.SUBAGENT.value,
            "index": index,
            "state": "running",
            "subtask": brief,
            "member": member.name,
            "member_id": member.id,
        },
    )

    enabled = await tool_directives.resolve_enabled_tools(
        domain, credentials=ctx.service_credentials, assigned=assigned_tools
    )
    # Per-run directive registry: domain tools plus the built-in original-
    # request viewer (available whenever this run carries an objective, even
    # in domains with no executable tools). ``specs_for`` merges the stateless
    # built-ins with the connected-API specs, whose executors close over this
    # user's decrypted service keys.
    specs = tool_directives.specs_for(enabled, ctx.service_credentials)
    if objective.strip():
        specs[VIEW_ORIGINAL_REQUEST_ACTION] = (
            tool_directives.make_view_original_request_spec(objective)
        )
    upstream_block = format_optional_block(
        SUBAGENT_UPSTREAM_HEADER, _format_upstream(upstream or [])
    )
    # The request travels with the brief instead of waiting behind a tool call.
    # Delimited and labelled as context, so the brief stays the instruction.
    objective_block = format_optional_block(
        SUBAGENT_OBJECTIVE_HEADER,
        f"{ORIGINAL_REQUEST_OPEN}\n"
        f"{truncate_text(objective.strip(), OBJECTIVE_MAX_CHARS)}\n"
        f"{ORIGINAL_REQUEST_CLOSE}"
        if objective.strip()
        else "",
    )
    system_prompt = SUBAGENT_SYSTEM.format(
        name=member.name,
        domain=domain,
        role=member.role,
        instructions=format_optional_block("How you work:", member.instructions),
        output_format=format_optional_block(
            "Format your output as:", member.output_format
        ),
        objective=objective_block,
        upstream=upstream_block,
        review_hints=hints_block,
        memory_context=format_memory_block(ctx.memory_context),
    )
    system_prompt += _tools_rule(ctx, specs)
    messages = [
        ChatMessage("system", with_current_date(system_prompt)),
        ChatMessage("user", brief),
    ]
    started = time.perf_counter()
    try:
        response, tokens_used, usage = await _chat_with_tools(
            ctx, messages, member=member, index=index, specs=specs
        )
    except LLMError as exc:
        logger.warning("subtask failed: member=%s error=%s", member.id, exc)
        return await _fail(
            ctx,
            member=member,
            index=index,
            brief=brief,
            error=str(exc),
            metadata={"execution_time_ms": _elapsed_ms(started)},
        )

    metadata = {
        "tokens_used": tokens_used,
        "execution_time_ms": _elapsed_ms(started),
        "model_used": response.model,
    }
    if enabled:
        # Only executable domain tools count; the built-in viewer is tracked
        # under its own metadata key below.
        metadata["tool_calls_used"] = sum(usage.get(action, 0) for action in enabled)
    for action, spec in specs.items():
        metadata[spec.metadata_key] = usage.get(action, 0)

    # An empty answer is a failure, not a success with nothing in it. A model
    # that spends its whole output budget reasoning (or returns only a <think>
    # block) leaves this blank, and calling that SUCCESS is corrosive: the
    # member's card goes green, synthesis merges an empty string, and a task
    # where every member came back blank reports `completed` instead of
    # `failed` — because `all_subtasks_failed` in main_agent counts ERROR
    # results, and there were none. Failing here is what makes that signal
    # honest, and it feeds the existing partial-failure path: some members
    # blank -> completed_with_warnings plus a "Known gaps" section.
    if not response.content.strip():
        logger.warning(
            "subtask produced an empty answer: member=%s tokens=%s",
            member.id,
            tokens_used,
            extra={"member_id": member.id},
        )
        return await _fail(
            ctx,
            member=member,
            index=index,
            brief=brief,
            error=EMPTY_SUBAGENT_ANSWER,
            metadata=metadata,
        )

    result = SubagentResult(
        status=SubagentStatus.SUCCESS,
        data={
            "subtask": brief,
            "output": response.content,
            "member": member.id,
            # A concise view handed to dependent members (Backend v2 §4.6); the
            # full output stays in ``output`` for synthesis.
            "summary": truncate_text(response.content, SUBAGENT_SUMMARY_MAX_CHARS),
        },
        metadata=metadata,
    )
    await ctx.emit(
        EventType.NODE_UPDATE,
        {
            "role": AgentRole.SUBAGENT.value,
            "index": index,
            "state": "done",
            "member": member.name,
            "member_id": member.id,
        },
    )
    return result


async def _fail(
    ctx: AgentContext,
    *,
    member: SubagentSpec,
    index: int,
    brief: str,
    error: str,
    metadata: dict[str, Any],
) -> SubagentResult:
    """Close a subtask as failed: node update plus an ERROR result.

    The node update is not optional. It closes the "running" state opened at the
    start of the run — without it the card stays mid-run until the task ends,
    and a partial failure then freezes it to "done", rendering a failed member
    as a success.
    """
    await ctx.emit(
        EventType.NODE_UPDATE,
        {
            "role": AgentRole.SUBAGENT.value,
            "index": index,
            "state": "error",
            "member": member.name,
            "member_id": member.id,
            "error": error,
        },
    )
    return SubagentResult(
        status=SubagentStatus.ERROR,
        data={"error": error, "subtask": brief, "member": member.id},
        metadata=metadata,
    )


async def _chat_with_tools(
    ctx: AgentContext,
    messages: list[ChatMessage],
    *,
    member: SubagentSpec,
    index: int,
    specs: dict[str, ToolSpec],
) -> tuple[LLMResponse, int, dict[str, int]]:
    """Run the tool loop, then insist on an answer when the reply comes back blank.

    Providers with real function calling take the native path; everyone else
    (Ollama/qwen by default) uses the provider-agnostic directive loop. Either
    way a blank final reply earns exactly one nudge before the caller fails it
    as ``EMPTY_SUBAGENT_ANSWER``: a small model that spent its output budget
    reasoning — or that came back from a fruitless search judging it had nothing
    worth writing — usually answers on the second ask, and one extra call is far
    cheaper than a dead member. A second blank still fails, so the honest
    all-members-blank signal the task layer depends on is unchanged.
    Returns ``(final_response, total_tokens, usage_per_tool)``.
    """
    native = bool(specs) and getattr(
        ctx.role_adapter("subagent").capabilities, "native_tools", False
    )
    loop = _native_tool_loop if native else _directive_tool_loop
    response, total_tokens, usage, messages = await loop(
        ctx, messages, member=member, index=index, specs=specs
    )
    # The budget guard inside the loop has already forced a final answer once
    # the task's cap is spent; nudging past it would be spend nobody authorized.
    if budget.budget_exceeded(ctx):
        return response, total_tokens, usage

    if response.content.strip():
        return await _nudge_if_nothing_retrieved(
            ctx,
            messages,
            member=member,
            index=index,
            specs=specs,
            loop=loop,
            response=response,
            total_tokens=total_tokens,
            usage=usage,
        )

    logger.warning(
        "subtask answer was blank; asking once more: member=%s",
        member.id,
        extra={"member_id": member.id},
    )
    # The blank reply itself is deliberately not appended: an empty assistant
    # turn is rejected outright by some providers, and every provider we target
    # accepts consecutive user messages.
    messages.append(ChatMessage("user", SUBAGENT_EMPTY_ANSWER_NUDGE))
    retry = await ctx.role_adapter("subagent").chat(
        messages, temperature=0.3, max_tokens=SUBAGENT_MAX_TOKENS
    )
    return retry, total_tokens + retry.tokens_used, usage


async def _nudge_if_nothing_retrieved(
    ctx: AgentContext,
    messages: list[ChatMessage],
    *,
    member: SubagentSpec,
    index: int,
    specs: dict[str, ToolSpec],
    loop: Any,
    response: LLMResponse,
    total_tokens: int,
    usage: dict[str, int],
) -> tuple[LLMResponse, int, dict[str, int]]:
    """Ask once more when a member holding retrieval tools never used one.

    Only fires when the member *could* have retrieved and did not: a domain with
    no retrieval tool, or a run that already made a call, is left alone. The loop
    is re-entered rather than a bare chat issued, so a directive the model emits
    in response is actually executed.

    The model is explicitly allowed to repeat its answer unchanged, because for a
    genuine general-knowledge question ("why do batteries wear out") not
    searching is correct — the nudge is there to catch the case where it is not,
    and one wasted turn is a cheap price for that. If the second attempt comes
    back blank or errors, the first answer stands: this must never turn a
    usable answer into a failed subtask.
    """
    retrievable = {action for action in specs if action in RETRIEVAL_TOOL_IDS}
    external_calls = sum(
        count
        for action, count in usage.items()
        if action != VIEW_ORIGINAL_REQUEST_ACTION
    )
    if not retrievable or external_calls:
        return response, total_tokens, usage

    logger.info(
        "subtask answered without retrieving; nudging once: member=%s",
        member.id,
        extra={"member_id": member.id},
    )
    messages.append(ChatMessage("assistant", response.content))
    messages.append(ChatMessage("user", SUBAGENT_NO_RETRIEVAL_NUDGE))
    try:
        retry, retry_tokens, retry_usage, _ = await loop(
            ctx, messages, member=member, index=index, specs=specs
        )
    except LLMError as exc:
        # The first answer was fine; a failed second opinion must not lose it.
        logger.warning("retrieval nudge failed: member=%s error=%s", member.id, exc)
        return response, total_tokens, usage

    if not retry.content.strip():
        return response, total_tokens + retry_tokens, usage
    merged = dict(usage)
    for action, count in retry_usage.items():
        merged[action] = merged.get(action, 0) + count
    return retry, total_tokens + retry_tokens, merged


async def _directive_tool_loop(
    ctx: AgentContext,
    messages: list[ChatMessage],
    *,
    member: SubagentSpec,
    index: int,
    specs: dict[str, ToolSpec],
) -> tuple[LLMResponse, int, dict[str, int], list[ChatMessage]]:
    """Provider-agnostic loop: the model asks for tools in JSON, we execute them.

    Any reply that is not a valid directive is treated as the final answer, so
    models that answer directly are unaffected. Hard bound:
    ``max_tool_calls + max_original_request_views + 2`` LLM calls per run. The
    transcript comes back with the response so the caller can keep the
    conversation going (see the blank-answer nudge above).
    """
    enabled = frozenset(specs)
    total_tokens = 0
    usage: dict[str, int] = {}
    while True:
        # Per-call budget guard (D19): if the task's token cap is already spent,
        # force one final answer instead of another tool round-trip.
        if budget.budget_exceeded(ctx):
            messages.append(
                ChatMessage(
                    "user", "Token budget exhausted. Give your final answer now."
                )
            )
            response = await ctx.role_adapter("subagent").chat(
                messages, temperature=0.3, max_tokens=SUBAGENT_MAX_TOKENS
            )
            total_tokens += response.tokens_used
            return response, total_tokens, usage, messages
        messages = _compact_transcript(messages)
        response = await ctx.role_adapter("subagent").chat(
            messages, temperature=0.3, max_tokens=SUBAGENT_MAX_TOKENS
        )
        total_tokens += response.tokens_used
        directive = (
            tool_directives.parse_directive(response.content, enabled)
            if specs
            else None
        )
        if directive is None:
            return response, total_tokens, usage, messages

        messages.append(ChatMessage("assistant", response.content))
        over_tool_budget = usage.get(directive.action, 0) >= _tool_budget(
            ctx, directive.action, specs
        )
        # The built-in viewer is exempt from the total cap so it never crowds
        # out real tools (its own budget still applies).
        executable_calls = sum(
            count
            for action, count in usage.items()
            if action != VIEW_ORIGINAL_REQUEST_ACTION
        )
        over_total_budget = (
            directive.action != VIEW_ORIGINAL_REQUEST_ACTION
            and executable_calls >= ctx.max_tool_calls
        )
        if over_tool_budget or over_total_budget:
            messages.append(
                ChatMessage(
                    "user", "Tool budget exhausted. Give your final answer now."
                )
            )
            response = await ctx.role_adapter("subagent").chat(
                messages, temperature=0.3, max_tokens=SUBAGENT_MAX_TOKENS
            )
            total_tokens += response.tokens_used
            return response, total_tokens, usage, messages

        usage[directive.action] = usage.get(directive.action, 0) + 1
        await _emit_tool(
            ctx, member=member, index=index, directive=directive, specs=specs
        )
        feedback = await _execute(directive, specs)
        await _emit_tool(
            ctx, member=member, index=index, directive=directive, specs=specs, done=True
        )
        messages.append(ChatMessage("user", feedback))


async def _native_tool_loop(
    ctx: AgentContext,
    messages: list[ChatMessage],
    *,
    member: SubagentSpec,
    index: int,
    specs: dict[str, ToolSpec],
) -> tuple[LLMResponse, int, dict[str, int], list[ChatMessage]]:
    """Native function-calling variant of the directive loop.

    Passes the tools as :class:`ToolDef`s and reacts to ``response.tool_calls``;
    a reply with no tool calls is the final answer. The same per-tool and total
    budgets as the directive loop apply, and the token-budget guard forces a
    final answer when the task cap is spent. Tool results are fed back as ``tool``
    messages. Falls back to the directive path implicitly (the caller only routes
    here when the adapter advertises ``native_tools``).
    """
    tool_defs = tool_directives.tool_defs_for(specs)
    total_tokens = 0
    usage: dict[str, int] = {}

    async def _final() -> tuple[LLMResponse, int, dict[str, int], list[ChatMessage]]:
        response = await ctx.role_adapter("subagent").chat(
            messages, temperature=0.3, max_tokens=SUBAGENT_MAX_TOKENS
        )
        return response, total_tokens + response.tokens_used, usage, messages

    while True:
        if budget.budget_exceeded(ctx):
            messages.append(
                ChatMessage(
                    "user", "Token budget exhausted. Give your final answer now."
                )
            )
            return await _final()
        messages = _compact_transcript(messages)
        response = await ctx.role_adapter("subagent").chat(
            messages, temperature=0.3, max_tokens=SUBAGENT_MAX_TOKENS, tools=tool_defs
        )
        total_tokens += response.tokens_used
        if not response.tool_calls:
            return response, total_tokens, usage, messages
        messages.append(ChatMessage("assistant", response.content))
        for call in response.tool_calls:
            spec = specs.get(call.name)
            if spec is None:
                messages.append(ChatMessage("tool", f"Unknown tool: {call.name}"))
                continue
            executable_calls = sum(
                count
                for action, count in usage.items()
                if action != VIEW_ORIGINAL_REQUEST_ACTION
            )
            over_tool = usage.get(call.name, 0) >= _tool_budget(ctx, call.name, specs)
            over_total = (
                call.name != VIEW_ORIGINAL_REQUEST_ACTION
                and executable_calls >= ctx.max_tool_calls
            )
            if over_tool or over_total:
                messages.append(ChatMessage("tool", "Tool budget exhausted."))
                continue
            directive = ToolDirective(action=call.name, args=call.arguments)
            usage[call.name] = usage.get(call.name, 0) + 1
            await _emit_tool(
                ctx, member=member, index=index, directive=directive, specs=specs
            )
            feedback = await _execute(directive, specs)
            await _emit_tool(
                ctx,
                member=member,
                index=index,
                directive=directive,
                specs=specs,
                done=True,
            )
            messages.append(ChatMessage("tool", feedback))


def _compact_transcript(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Collapse older tool exchanges once the transcript grows too large (§4.6).

    Keeps the system prompt, the original brief, and the two most recent turns;
    the middle is replaced by one truncated summary note. Deterministic (no LLM
    call), so a subagent's token accounting is unaffected. A no-op below the
    threshold and for short transcripts (nothing to collapse).
    """
    limit = COMPACTION_THRESHOLD_TOKENS * TOKEN_ESTIMATE_CHARS_PER_TOKEN
    if len(messages) <= 4 or sum(len(m.content) for m in messages) <= limit:
        return messages
    head, tail = messages[:2], messages[-2:]
    middle = "\n".join(m.content for m in messages[2:-2])
    note = ChatMessage(
        "system",
        "[Earlier tool exchanges, summarized to save space]:\n"
        + truncate_text(middle, COMPACTION_KEEP_CHARS),
    )
    return [*head, note, *tail]


async def _execute(directive: ToolDirective, specs: dict[str, ToolSpec]) -> str:
    """Run one directive and return the prompt block to feed back."""
    from app.core.constants import SpanKind
    from app.utils import tracing

    async with tracing.tracer.span(
        f"tool:{directive.action}",
        SpanKind.TOOL,
        **{"maestro.tool.action": directive.action},
    ):
        return await specs[directive.action].executor(directive)


async def _emit_tool(
    ctx: AgentContext,
    *,
    member: SubagentSpec,
    index: int,
    directive: ToolDirective,
    specs: dict[str, ToolSpec],
    done: bool = False,
) -> None:
    """Surface tool activity in the live Architect stream.

    Fired twice per call, before and after. ``done`` is on the payload because
    without it the two events differ only in the ``content`` prose, which the
    frontend does not parse — so a client could not tell an in-flight call from
    a finished one, and the Architect rail could never show a live edge.
    """
    spec = specs[directive.action]
    payload: dict[str, object] = {
        "role": AgentRole.SUBAGENT.value,
        "index": index,
        "member": member.name,
        "member_id": member.id,
        "action": directive.action,
        "done": done,
        "content": spec.describe(directive, done),
    }
    if spec.event_arg:
        payload[spec.event_arg] = directive.args.get(spec.event_arg, "")
    # Only the connected-API tools carry a provider; the keyless ones report
    # None and get no lane on the canvas.
    if spec.provider_of is not None:
        payload["provider"] = spec.provider_of(directive)
    await ctx.emit(EventType.AGENT_MESSAGE, payload)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
