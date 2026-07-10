"""In-process pub/sub event bus for live task/architect streaming.

Agents publish structured events per task; WebSocket connections subscribe by
``task_id`` and forward events to the client. This is a single-process bus
(fine for the current build); a Redis/broker backend can replace it later
without changing publishers or subscribers.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

# Sentinel pushed to every subscriber queue when a task stream ends.
_STREAM_END = object()


class EventBus:
    """Fan-out event bus keyed by task id."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, task_id: str, event: dict[str, Any]) -> None:
        """Deliver an event to all subscribers of a task."""
        async with self._lock:
            queues = list(self._subscribers.get(task_id, ()))
        for queue in queues:
            queue.put_nowait(event)

    async def close(self, task_id: str) -> None:
        """Signal end-of-stream to all subscribers of a task."""
        async with self._lock:
            queues = list(self._subscribers.get(task_id, ()))
        for queue in queues:
            queue.put_nowait(_STREAM_END)

    @asynccontextmanager
    async def subscribe(self, task_id: str) -> AsyncIterator[asyncio.Queue]:
        """Subscribe to a task's events for the duration of the context."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(task_id, set()).add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                subs = self._subscribers.get(task_id)
                if subs is not None:
                    subs.discard(queue)
                    if not subs:
                        self._subscribers.pop(task_id, None)

    async def stream(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield events for a task until the stream is closed."""
        async with self.subscribe(task_id) as queue:
            while True:
                item = await queue.get()
                if item is _STREAM_END:
                    return
                yield item


# Shared process-wide bus.
event_bus = EventBus()
