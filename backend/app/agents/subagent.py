"""Subagent: a fixed team member executing one briefed subtask via the LLM.

Subagents in domains that declare executable tools (web_search, data_fetch,
code_execution) can request them through a provider-agnostic JSON directive
loop (no native function calling required): the model replies with a directive
instead of an answer, we execute the tool and feed the result back, bounded by
per-tool budgets and a total tool-call cap.

Subagents never receive the raw user message in their prompt: they work from
the Main Agent's decomposed brief, plus (when dependencies were declared) the
finished outputs of the teammates they build on. A subagent that needs more
context can fetch the original user request on demand via the built-in
``view_original_request`` directive.
"""

from __future__ import annotations

import logging
import time

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
    SUBAGENT_SYSTEM,
    SUBAGENT_TOOLS_RULE,
    SUBAGENT_UPSTREAM_HEADER,
    TOOL_RULE_LINES,
)
from app.agents.registry import SubagentSpec
from app.agents.tools import TOOL_SPECS, ToolDirective, ToolSpec
from app.core.constants import (
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

    enabled = await tool_directives.resolve_enabled_tools(domain)
    # Per-run directive registry: domain tools plus the built-in original-
    # request viewer (available whenever this run carries an objective, even
    # in domains with no executable tools).
    specs = {action: TOOL_SPECS[action] for action in enabled}
    if objective.strip():
        specs[VIEW_ORIGINAL_REQUEST_ACTION] = (
            tool_directives.make_view_original_request_spec(objective)
        )
    upstream_block = format_optional_block(
        SUBAGENT_UPSTREAM_HEADER, _format_upstream(upstream or [])
    )
    system_prompt = SUBAGENT_SYSTEM.format(
        name=member.name,
        domain=domain,
        role=member.role,
        instructions=format_optional_block("How you work:", member.instructions),
        output_format=format_optional_block(
            "Format your output as:", member.output_format
        ),
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
        return SubagentResult(
            status=SubagentStatus.ERROR,
            data={"error": str(exc), "subtask": brief, "member": member.id},
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
    result = SubagentResult(
        status=SubagentStatus.SUCCESS,
        data={"subtask": brief, "output": response.content, "member": member.id},
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


async def _chat_with_tools(
    ctx: AgentContext,
    messages: list[ChatMessage],
    *,
    member: SubagentSpec,
    index: int,
    specs: dict[str, ToolSpec],
) -> tuple[LLMResponse, int, dict[str, int]]:
    """Chat with the LLM, executing bounded tool directives.

    Any reply that is not a valid directive is treated as the final answer, so
    models that answer directly are unaffected. Hard bound:
    ``max_tool_calls + max_original_request_views + 2`` LLM calls per run.
    Returns ``(final_response, total_tokens, usage_per_tool)``.
    """
    enabled = frozenset(specs)
    total_tokens = 0
    usage: dict[str, int] = {}
    while True:
        response = await ctx.adapter.chat(messages, temperature=0.3)
        total_tokens += response.tokens_used
        directive = (
            tool_directives.parse_directive(response.content, enabled)
            if specs
            else None
        )
        if directive is None:
            return response, total_tokens, usage

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
            response = await ctx.adapter.chat(messages, temperature=0.3)
            total_tokens += response.tokens_used
            return response, total_tokens, usage

        usage[directive.action] = usage.get(directive.action, 0) + 1
        await _emit_tool(
            ctx, member=member, index=index, directive=directive, specs=specs
        )
        feedback = await _execute(directive, specs)
        await _emit_tool(
            ctx, member=member, index=index, directive=directive, specs=specs, done=True
        )
        messages.append(ChatMessage("user", feedback))


async def _execute(directive: ToolDirective, specs: dict[str, ToolSpec]) -> str:
    """Run one directive and return the prompt block to feed back."""
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
    """Surface tool activity in the live Architect stream."""
    spec = specs[directive.action]
    payload = {
        "role": AgentRole.SUBAGENT.value,
        "index": index,
        "member": member.name,
        "member_id": member.id,
        "action": directive.action,
        "content": spec.describe(directive, done),
    }
    if spec.event_arg:
        payload[spec.event_arg] = directive.args[spec.event_arg]
    await ctx.emit(EventType.AGENT_MESSAGE, payload)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
