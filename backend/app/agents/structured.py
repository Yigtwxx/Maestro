"""Schema-validated LLM calls (Backend v2 §4.4).

``structured_call`` replaces the bare ``Model.model_validate(extract_json(...))``
pattern at every agent decision site. When the adapter's provider supports
provider-enforced JSON (``capabilities.json_schema``), the model's JSON schema is
sent so the reply is guaranteed well-formed; otherwise the reply is parsed with
the ``extract_json`` heuristic. Either way, a validation failure is fed back to
the model and the call is retried once (the Instructor pattern) before giving up.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.agents.base import extract_json
from app.services.llm_service import ChatMessage, LLMAdapter, LLMError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# How much of a rejected reply to echo back when asking for a correction.
_ECHO_MAX_CHARS = 2000


async def structured_call(
    adapter: LLMAdapter,
    messages: list[ChatMessage],
    model_cls: type[T],
    *,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    max_attempts: int = 2,
) -> T:
    """Call the model and return a validated ``model_cls`` instance.

    Retries on both a transient provider failure (``LLMError``) and a parse /
    validation failure, feeding the error back on the latter. Raises the last
    ``LLMError`` if every attempt hit the provider, else ``ValueError`` if output
    never validated — callers already treat both as a fall-back trigger.
    """
    schema = model_cls.model_json_schema() if adapter.capabilities.json_schema else None
    convo = list(messages)
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        extra = {"response_schema": schema} if schema is not None else {}
        try:
            response = await adapter.chat(
                convo, temperature=temperature, max_tokens=max_tokens, **extra
            )
        except LLMError as exc:
            # Provider failure, not a parse issue: retry with the original prompt.
            last_error = exc
            logger.warning(
                "structured call failed (attempt %d/%d): %s",
                attempt + 1,
                max_attempts,
                exc,
            )
            convo = list(messages)
            continue
        try:
            return model_cls.model_validate(extract_json(response.content))
        except (ValueError, ValidationError) as exc:
            last_error = exc
            logger.warning(
                "structured output invalid (attempt %d/%d): %s",
                attempt + 1,
                max_attempts,
                exc,
            )
            # Feed the error back so the model can self-correct on the next pass.
            convo = [
                *messages,
                ChatMessage("assistant", response.content[:_ECHO_MAX_CHARS]),
                ChatMessage(
                    "user",
                    "Your previous reply could not be parsed as the required "
                    f"JSON object ({exc}). Reply with ONLY the corrected JSON "
                    "object and no other text.",
                ),
            ]

    if isinstance(last_error, LLMError):
        raise last_error
    raise ValueError(
        f"structured output invalid after {max_attempts} attempts: {last_error}"
    )
