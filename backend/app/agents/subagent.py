"""Subagent: a fixed team member executing one briefed subtask via the LLM.

Subagents in domains that declare the ``web_search`` tool can request real
DuckDuckGo searches through a provider-agnostic JSON directive loop (no native
function calling required): the model replies with a directive instead of an
answer, we execute the search and feed the results back, bounded by
``ctx.max_web_searches``.
"""

from __future__ import annotations

import time

from app.agents.base import (
    AgentContext,
    SubagentResult,
    extract_json,
    format_memory_block,
    format_optional_block,
    with_current_date,
)
from app.agents.prompts import SUBAGENT_SYSTEM, SUBAGENT_WEB_SEARCH_RULE
from app.agents.registry import SubagentSpec, get_domain_info
from app.core.config import settings
from app.core.constants import (
    WEB_SEARCH_ACTION,
    WEB_SEARCH_CATEGORIES,
    WEB_SEARCH_DEFAULT_CATEGORY,
    AgentRole,
    EventType,
    SubagentStatus,
)
from app.services import web_search_service
from app.services.llm_service import ChatMessage, LLMError, LLMResponse


async def run_subtask(
    ctx: AgentContext,
    *,
    domain: str,
    member: SubagentSpec,
    brief: str,
    index: int,
    review_hints: list[str] | None = None,
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

    search_enabled = (
        settings.web_search_enabled
        and WEB_SEARCH_ACTION in get_domain_info(domain).tools
    )
    system_prompt = SUBAGENT_SYSTEM.format(
        name=member.name,
        domain=domain,
        role=member.role,
        instructions=format_optional_block("How you work:", member.instructions),
        output_format=format_optional_block(
            "Format your output as:", member.output_format
        ),
        review_hints=hints_block,
        memory_context=format_memory_block(ctx.memory_context),
    )
    if search_enabled:
        system_prompt += SUBAGENT_WEB_SEARCH_RULE.format(
            max_searches=ctx.max_web_searches
        )
    messages = [
        ChatMessage("system", with_current_date(system_prompt)),
        ChatMessage("user", brief),
    ]
    started = time.perf_counter()
    try:
        response, tokens_used, searches_used = await _chat_with_search(
            ctx, messages, member=member, index=index, search_enabled=search_enabled
        )
    except LLMError as exc:
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
    if search_enabled:
        metadata["searches_used"] = searches_used
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


async def _chat_with_search(
    ctx: AgentContext,
    messages: list[ChatMessage],
    *,
    member: SubagentSpec,
    index: int,
    search_enabled: bool,
) -> tuple[LLMResponse, int, int]:
    """Chat with the LLM, executing bounded web-search directives.

    Any reply that is not a valid directive is treated as the final answer, so
    models that answer directly are unaffected. Hard bound:
    ``max_web_searches + 2`` LLM calls per run.
    Returns ``(final_response, total_tokens, searches_used)``.
    """
    total_tokens = 0
    searches_used = 0
    while True:
        response = await ctx.adapter.chat(messages, temperature=0.3)
        total_tokens += response.tokens_used
        directive = (
            _parse_search_directive(response.content) if search_enabled else None
        )
        if directive is None:
            return response, total_tokens, searches_used

        messages.append(ChatMessage("assistant", response.content))
        if searches_used >= ctx.max_web_searches:
            messages.append(
                ChatMessage(
                    "user", "Search budget exhausted. Give your final answer now."
                )
            )
            response = await ctx.adapter.chat(messages, temperature=0.3)
            total_tokens += response.tokens_used
            return response, total_tokens, searches_used

        query, category = directive
        searches_used += 1
        await _emit_search(ctx, member=member, index=index, query=query)
        results = await web_search_service.search(query, category=category)
        await _emit_search(
            ctx, member=member, index=index, query=query, result_count=len(results)
        )
        messages.append(
            ChatMessage("user", web_search_service.format_results_block(query, results))
        )


def _parse_search_directive(content: str) -> tuple[str, str] | None:
    """Return ``(query, category)`` if the reply is a web_search directive."""
    try:
        parsed = extract_json(content)
    except ValueError:
        return None
    if parsed.get("action") != WEB_SEARCH_ACTION:
        return None
    query = str(parsed.get("query", "")).strip()
    if not query:
        return None
    category = str(parsed.get("category", WEB_SEARCH_DEFAULT_CATEGORY)).strip().lower()
    if category not in WEB_SEARCH_CATEGORIES:
        category = WEB_SEARCH_DEFAULT_CATEGORY
    return query, category


async def _emit_search(
    ctx: AgentContext,
    *,
    member: SubagentSpec,
    index: int,
    query: str,
    result_count: int | None = None,
) -> None:
    """Surface search activity in the live Architect stream."""
    if result_count is None:
        content = f"Searching the web for: {query}"
    else:
        content = f"Web search returned {result_count} results."
    payload = {
        "role": AgentRole.SUBAGENT.value,
        "index": index,
        "member": member.name,
        "member_id": member.id,
        "action": WEB_SEARCH_ACTION,
        "query": query,
        "content": content,
    }
    if result_count is not None:
        payload["result_count"] = result_count
    await ctx.emit(EventType.AGENT_MESSAGE, payload)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
