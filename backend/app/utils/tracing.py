"""Own execution-trace infrastructure (Backend v2 §4.5).

OTel GenAI-shaped spans are recorded into the Mongo ``trace_spans`` collection
and surfaced by our own trace/cost endpoints — no new service, no OTLP exporter
(the attribute names match the OTel GenAI semantic conventions, so one can be
added later without renaming anything).

Design guarantees kept here:

* **Best-effort.** Spans are buffered and flushed with ``insert_many``; a Mongo
  failure is logged and swallowed — it never propagates into a task.
* **No prompt/response bodies.** Spans carry token counts and a request-side
  preview capped at ``SPAN_PREVIEW_CHARS`` only (CLAUDE.md §9.4 / §15.1).
* **Zero cost when off.** With ``settings.tracing_enabled`` false, ``span`` is a
  no-op context manager: nothing is buffered and Mongo is never touched.

Parent/child nesting rides a ``contextvars.ContextVar``: a span opened inside
another becomes its child, and because asyncio copies the context when it
schedules a task, spans opened in parallel subagents parent correctly to the
step span that was active when the wave was gathered.
"""

from __future__ import annotations

import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.constants import (
    MODEL_PRICING,
    PROVIDER_COST_PER_1K_TOKENS,
    TRACE_SPAN_FLUSH_INTERVAL_SECONDS,
    TRACE_SPAN_FLUSH_MAX,
    MongoCollection,
    SpanKind,
    SpanStatus,
)

logger = logging.getLogger(__name__)


def new_span_id() -> str:
    """A 16-hex span id (OTel span-id width)."""
    return uuid.uuid4().hex[:16]


def cost_usd(
    model: str | None,
    provider: str | None,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """USD cost of a completion.

    Uses the per-model ``MODEL_PRICING`` (input/output split) when the model is
    known, else the blended per-provider rate. Unknown providers cost 0.0 (e.g.
    a user's custom endpoint, whose pricing we cannot know).
    """
    rate = MODEL_PRICING.get(model or "")
    if rate is not None:
        return input_tokens / 1000 * rate[0] + output_tokens / 1000 * rate[1]
    blended = PROVIDER_COST_PER_1K_TOKENS.get(provider or "", 0.0)
    return (input_tokens + output_tokens) / 1000 * blended


@dataclass(slots=True)
class Span:
    """One node of a trace. Serialized to a Mongo document on close."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: str
    user_id: str | None
    start_time: datetime
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = SpanStatus.OK.value
    error_message: str | None = None
    cost_usd: float = 0.0

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: str, error_message: str | None = None) -> None:
        self.status = status
        if error_message is not None:
            self.error_message = error_message


class _NullSpan:
    """No-op span handed out when tracing is disabled; safe to call on."""

    __slots__ = ()

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D102
        return None

    def set_status(self, status: str, error_message: str | None = None) -> None:  # noqa: D102
        return None


_NULL_SPAN = _NullSpan()


class Tracer:
    """Buffers spans and flushes them to Mongo in batches (best-effort)."""

    def __init__(self) -> None:
        self._current: ContextVar[Span | None] = ContextVar(
            "maestro_current_span", default=None
        )
        self._buffer: list[dict[str, Any]] = []
        self._last_flush = time.monotonic()

    def current(self) -> Span | None:
        """The span in scope on this task, or ``None``."""
        return self._current.get()

    @contextlib.asynccontextmanager
    async def span(
        self,
        name: str,
        kind: SpanKind,
        *,
        trace_id: str | None = None,
        user_id: str | None = None,
        **attributes: Any,
    ) -> AsyncIterator[Any]:
        """Open a span for the duration of the ``async with`` block.

        ``trace_id``/``user_id`` are taken from the parent when omitted, so only
        the root ``task`` span needs to pass them. A raised exception marks the
        span ``error`` (and is re-raised — tracing never swallows task errors).
        """
        if not settings.tracing_enabled:
            yield _NULL_SPAN
            return

        parent = self._current.get()
        span = Span(
            trace_id=trace_id or (parent.trace_id if parent else name),
            span_id=new_span_id(),
            parent_span_id=parent.span_id if parent else None,
            name=name,
            kind=kind.value,
            user_id=user_id or (parent.user_id if parent else None),
            start_time=datetime.now(UTC),
            attributes=dict(attributes),
        )
        token = self._current.set(span)
        try:
            yield span
        except BaseException as exc:  # noqa: BLE001 - record, then re-raise
            span.set_status(SpanStatus.ERROR.value, str(exc)[:200])
            raise
        finally:
            self._current.reset(token)
            self._finish(span)

    def _finish(self, span: Span) -> None:
        end = datetime.now(UTC)
        duration_ms = int((end - span.start_time).total_seconds() * 1000)
        self._buffer.append(
            {
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "name": span.name,
                "kind": span.kind,
                "user_id": span.user_id,
                "start_time": span.start_time,
                "end_time": end,
                "duration_ms": duration_ms,
                "status": span.status,
                "error_message": span.error_message,
                "attributes": span.attributes,
                "cost_usd": round(span.cost_usd, 6),
                "created_at": end,
            }
        )

    async def _maybe_flush(self) -> None:
        if len(self._buffer) >= TRACE_SPAN_FLUSH_MAX or (
            self._buffer
            and time.monotonic() - self._last_flush >= TRACE_SPAN_FLUSH_INTERVAL_SECONDS
        ):
            await self.flush()

    async def flush(self) -> None:
        """Write buffered spans to Mongo. Best-effort: errors are logged only."""
        if not self._buffer:
            return
        batch = self._buffer
        self._buffer = []
        self._last_flush = time.monotonic()
        try:
            await _spans_collection().insert_many(batch, ordered=False)
        except Exception:  # noqa: BLE001 - a trace write must never fail a task
            logger.warning("trace span flush failed (%d spans)", len(batch))


def _spans_collection():  # noqa: ANN202 - Motor collection (a seam for tests)
    from app.core.database import get_mongo_db

    return get_mongo_db()[MongoCollection.TRACE_SPANS.value]


tracer = Tracer()


async def flush_spans() -> None:
    """Flush the process-wide tracer. Buffer-aware and best-effort."""
    await tracer._maybe_flush()  # noqa: SLF001 - single owner of the buffer


async def force_flush() -> None:
    """Flush unconditionally (call at a task boundary so spans land promptly)."""
    await tracer.flush()


async def periodic_flush() -> None:
    """Flush the span buffer on a fixed interval (started by the app lifespan).

    Guarantees the design's time-based flush even for an idle-but-open buffer;
    the per-span size trigger and the task-boundary ``force_flush`` cover the
    rest. Runs only while tracing is enabled.
    """
    import asyncio

    while True:
        await asyncio.sleep(TRACE_SPAN_FLUSH_INTERVAL_SECONDS)
        await tracer.flush()
