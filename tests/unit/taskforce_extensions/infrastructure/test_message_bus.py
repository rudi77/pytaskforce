import asyncio

import pytest

from taskforce.infrastructure.messaging import InMemoryMessageBus


@pytest.mark.asyncio
async def test_in_memory_message_bus_publish_subscribe() -> None:
    bus = InMemoryMessageBus()

    await bus.publish("tasks", {"job": "alpha"})

    subscriber = bus.subscribe("tasks")
    message = await asyncio.wait_for(subscriber.__anext__(), timeout=1)

    assert message.topic == "tasks"
    assert message.payload == {"job": "alpha"}

    await bus.ack(message.message_id)


@pytest.mark.asyncio
async def test_in_memory_message_bus_nack_requeue() -> None:
    bus = InMemoryMessageBus()

    await bus.publish("tasks", {"job": "beta"})

    subscriber = bus.subscribe("tasks")
    message = await asyncio.wait_for(subscriber.__anext__(), timeout=1)

    await bus.nack(message.message_id, requeue=True)

    subscriber_retry = bus.subscribe("tasks")
    message_retry = await asyncio.wait_for(subscriber_retry.__anext__(), timeout=1)

    assert message_retry.message_id == message.message_id
