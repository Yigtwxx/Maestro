"""Redis-backed event bus: cross-worker fan-out for events and control.

Two ``RedisEventBus`` instances over one shared fake server stand in for two
``uvicorn`` workers: an event (or cancel/answer control message) published by the
worker running a task must reach a subscriber on the other worker (Backend v2
§4.2). Uses ``fakeredis`` — no real Redis, mirrors the rate-limiter tests.
"""

from __future__ import annotations

import asyncio

import pytest

from app.utils.events import RedisEventBus, _ctrl_channel, _events_channel

_TIMEOUT = 2.0


async def _await_subscribed(bus: RedisEventBus, channel: str) -> None:
    """Block until `channel` has a live subscriber, server-side.

    Pub/sub drops a message published before the subscribe lands, so the tests
    must not publish until the subscriber is registered. `_subscribe` awaits the
    SUBSCRIBE before yielding, so this normally returns on the first poll;
    checking `PUBSUB NUMSUB` confirms it deterministically instead of racing a
    fixed sleep against the CI scheduler.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _TIMEOUT
    while True:
        numsub = await bus._redis.pubsub_numsub(channel)
        if numsub and numsub[0][1] >= 1:
            return
        assert loop.time() < deadline, f"subscription to {channel} never registered"
        await asyncio.sleep(0)


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
        await _await_subscribed(subscriber, _events_channel("task-x"))
        await publisher.publish("task-x", {"type": "node_update", "seq": 7})
        event = await asyncio.wait_for(queue.get(), timeout=_TIMEOUT)
    assert event["seq"] == 7, event
    assert event["type"] == "node_update", event


async def test_close_delivers_the_end_of_stream_sentinel() -> None:
    publisher, subscriber = _two_workers()
    async with subscriber.subscribe("task-x") as queue:
        await _await_subscribed(subscriber, _events_channel("task-x"))
        await publisher.close("task-x")
        item = await asyncio.wait_for(queue.get(), timeout=_TIMEOUT)
    # The sentinel is a non-dict marker the WS forward loop treats as end-of-stream.
    assert not isinstance(item, dict), item


async def test_control_message_is_delivered_across_workers() -> None:
    publisher, subscriber = _two_workers()
    async with subscriber.subscribe_ctrl("task-x") as queue:
        await _await_subscribed(subscriber, _ctrl_channel("task-x"))
        await publisher.publish_ctrl("task-x", {"op": "answer", "answer": "42"})
        message = await asyncio.wait_for(queue.get(), timeout=_TIMEOUT)
    assert message["op"] == "answer", message
    assert message["answer"] == "42", message


async def test_events_and_control_channels_are_isolated() -> None:
    publisher, subscriber = _two_workers()
    async with subscriber.subscribe("task-x") as queue:
        await _await_subscribed(subscriber, _events_channel("task-x"))
        # A control message must not surface on the events channel.
        await publisher.publish_ctrl("task-x", {"op": "cancel"})
        await publisher.publish("task-x", {"type": "task_completed", "seq": 1})
        event = await asyncio.wait_for(queue.get(), timeout=_TIMEOUT)
    assert event["type"] == "task_completed", event
