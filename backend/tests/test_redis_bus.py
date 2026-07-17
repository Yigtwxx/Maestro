"""Redis-backed event bus: cross-worker fan-out for events and control.

Two ``RedisEventBus`` instances over one shared fake server stand in for two
``uvicorn`` workers: an event (or cancel/answer control message) published by the
worker running a task must reach a subscriber on the other worker (Backend v2
§4.2). Uses ``fakeredis`` — no real Redis, mirrors the rate-limiter tests.
"""

from __future__ import annotations

import asyncio

import pytest

from app.utils.events import RedisEventBus

# Give a fresh pub/sub subscription time to register before the first publish
# (pub/sub drops messages sent before the subscribe lands).
_SETTLE = 0.1
_TIMEOUT = 2.0


def _two_workers():
    fakeredis = pytest.importorskip("fakeredis")
    server = fakeredis.FakeServer()
    publisher = RedisEventBus(
        fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    )
    subscriber = RedisEventBus(
        fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    )
    return publisher, subscriber


async def test_event_is_delivered_across_workers() -> None:
    publisher, subscriber = _two_workers()
    async with subscriber.subscribe("task-x") as queue:
        await asyncio.sleep(_SETTLE)
        await publisher.publish("task-x", {"type": "node_update", "seq": 7})
        event = await asyncio.wait_for(queue.get(), timeout=_TIMEOUT)
    assert event["seq"] == 7, event
    assert event["type"] == "node_update", event


async def test_close_delivers_the_end_of_stream_sentinel() -> None:
    publisher, subscriber = _two_workers()
    async with subscriber.subscribe("task-x") as queue:
        await asyncio.sleep(_SETTLE)
        await publisher.close("task-x")
        item = await asyncio.wait_for(queue.get(), timeout=_TIMEOUT)
    # The sentinel is a non-dict marker the WS forward loop treats as end-of-stream.
    assert not isinstance(item, dict), item


async def test_control_message_is_delivered_across_workers() -> None:
    publisher, subscriber = _two_workers()
    async with subscriber.subscribe_ctrl("task-x") as queue:
        await asyncio.sleep(_SETTLE)
        await publisher.publish_ctrl("task-x", {"op": "answer", "answer": "42"})
        message = await asyncio.wait_for(queue.get(), timeout=_TIMEOUT)
    assert message["op"] == "answer", message
    assert message["answer"] == "42", message


async def test_events_and_control_channels_are_isolated() -> None:
    publisher, subscriber = _two_workers()
    async with subscriber.subscribe("task-x") as queue:
        await asyncio.sleep(_SETTLE)
        # A control message must not surface on the events channel.
        await publisher.publish_ctrl("task-x", {"op": "cancel"})
        await publisher.publish("task-x", {"type": "task_completed", "seq": 1})
        event = await asyncio.wait_for(queue.get(), timeout=_TIMEOUT)
    assert event["type"] == "task_completed", event
