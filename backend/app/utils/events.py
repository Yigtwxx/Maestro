"""Pub/sub event bus for live task/architect streaming.

Agents publish structured events per task; WebSocket connections subscribe by
``task_id`` and forward events to the client. Two interchangeable backends share
one interface (``publish`` / ``close`` / ``subscribe`` / ``stream`` and the
cross-worker ``publish_ctrl`` / ``subscribe_ctrl``):

* :class:`EventBus` — in-process fan-out. The default; correct for a single
  worker (dev, tests) with zero extra services.
* :class:`RedisEventBus` — Redis pub/sub, selected when ``REDIS_URL`` is set, so
  ``uvicorn --workers N`` works: an event published by the worker running a task
  reaches a WebSocket subscribed on any other worker (Backend v2 §4.2).

Pub/sub is fire-and-forget: an event published with no subscriber is dropped.
That is fine because ``agent_logs`` is the durable, seq-ordered source of truth —
a late or reconnecting subscriber replays the snapshot first, then joins live.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Sentinel pushed to every subscriber queue when a task stream ends.
_STREAM_END = object()

# Wire marker for end-of-stream on Redis (the sentinel object cannot cross a
# process boundary, so it is encoded as an event and rebuilt on the far side).
_STREAM_END_TYPE = "stream_end"


def _events_channel(task_id: str) -> str:
    return f"maestro:events:{task_id}"


def _ctrl_channel(task_id: str) -> str:
    return f"maestro:ctrl:{task_id}"


class EventBus:
    """In-process fan-out event bus keyed by task id."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._ctrl_subscribers: dict[str, set[asyncio.Queue]] = {}
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

    # --- control channel (cross-worker cancel / HITL answer) --------------

    async def publish_ctrl(self, task_id: str, message: dict[str, Any]) -> None:
        """Deliver a control message (cancel/answer) to the owning worker."""
        async with self._lock:
            queues = list(self._ctrl_subscribers.get(task_id, ()))
        for queue in queues:
            queue.put_nowait(message)

    @asynccontextmanager
    async def subscribe_ctrl(self, task_id: str) -> AsyncIterator[asyncio.Queue]:
        """Subscribe to a task's control channel (owning worker only)."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._ctrl_subscribers.setdefault(task_id, set()).add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                subs = self._ctrl_subscribers.get(task_id)
                if subs is not None:
                    subs.discard(queue)
                    if not subs:
                        self._ctrl_subscribers.pop(task_id, None)


class RedisEventBus:
    """Redis pub/sub event bus with the same interface as :class:`EventBus`.

    Publish is best-effort: a Redis outage degrades liveness (no live updates),
    never correctness — durable state lives in Postgres/Mongo, so a dropped
    publish only means a client misses a live tick and recovers on reconnect.
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def _publish(self, channel: str, payload: dict[str, Any]) -> None:
        try:
            await self._redis.publish(channel, json.dumps(payload))
        except Exception:  # noqa: BLE001 - liveness only; state is elsewhere
            logger.warning("event publish failed on %s", channel, exc_info=True)

    async def publish(self, task_id: str, event: dict[str, Any]) -> None:
        await self._publish(_events_channel(task_id), event)

    async def close(self, task_id: str) -> None:
        await self._publish(_events_channel(task_id), {"type": _STREAM_END_TYPE})

    async def publish_ctrl(self, task_id: str, message: dict[str, Any]) -> None:
        await self._publish(_ctrl_channel(task_id), message)

    @asynccontextmanager
    async def _subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue()
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        reader = asyncio.create_task(self._read(pubsub, queue))
        try:
            yield queue
        finally:
            reader.cancel()
            try:  # noqa: SIM105 - suppress needs the CancelledError re-check
                await reader
            except asyncio.CancelledError:
                pass
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:  # noqa: BLE001 - teardown of a best-effort channel
                logger.debug("pubsub teardown failed on %s", channel, exc_info=True)

    async def _read(self, pubsub: Any, queue: asyncio.Queue) -> None:
        """Forward decoded pub/sub messages into the queue until cancelled."""
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue  # subscribe/unsubscribe acks
            try:
                event = json.loads(message["data"])
            except (ValueError, TypeError):
                logger.warning("dropping malformed event payload")
                continue
            if isinstance(event, dict) and event.get("type") == _STREAM_END_TYPE:
                queue.put_nowait(_STREAM_END)
            else:
                queue.put_nowait(event)

    def subscribe(self, task_id: str):  # noqa: ANN201 - async context manager
        return self._subscribe(_events_channel(task_id))

    def subscribe_ctrl(self, task_id: str):  # noqa: ANN201
        return self._subscribe(_ctrl_channel(task_id))

    async def stream(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
        async with self._subscribe(_events_channel(task_id)) as queue:
            while True:
                item = await queue.get()
                if item is _STREAM_END:
                    return
                yield item


def _build_event_bus() -> EventBus | RedisEventBus:
    """Pick the Redis bus when configured, else the in-process bus."""
    if settings.redis_url:
        from app.core.database import get_redis_client

        client = get_redis_client()
        if client is not None:
            return RedisEventBus(client)
    return EventBus()


# Shared process-wide bus.
event_bus: EventBus | RedisEventBus = _build_event_bus()
