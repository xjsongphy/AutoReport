"""Tests for async message bus."""

import asyncio

import pytest

from autoreport.interfaces.types import (
    AgentResponse,
    AgentType,
    Error,
    Message,
    MessageType,
    UserMessage,
)
from autoreport.core.loops.bus import MessageBus


@pytest.fixture
def bus():
    return MessageBus()


@pytest.mark.asyncio
async def test_publish_and_subscribe(bus):
    received = []

    async def callback(msg):
        received.append(msg)

    bus.subscribe(UserMessage, callback)

    msg = UserMessage(content="Hello")
    await bus.publish(msg)
    await bus._notify_subscribers(msg)

    assert len(received) == 1
    assert received[0].content == "Hello"


@pytest.mark.asyncio
async def test_sync_callback(bus):
    received = []

    def callback(msg):
        received.append(msg)

    bus.subscribe(UserMessage, callback)

    msg = UserMessage(content="Sync test")
    await bus._notify_subscribers(msg)

    assert len(received) == 1


@pytest.mark.asyncio
async def test_unsubscribe(bus):
    received = []

    async def callback(msg):
        received.append(msg)

    bus.subscribe(UserMessage, callback)
    bus.unsubscribe(UserMessage, callback)

    msg = UserMessage(content="Should not receive")
    await bus._notify_subscribers(msg)

    assert len(received) == 0


@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    received_a = []
    received_b = []

    async def callback_a(msg):
        received_a.append(msg)

    async def callback_b(msg):
        received_b.append(msg)

    bus.subscribe(UserMessage, callback_a)
    bus.subscribe(UserMessage, callback_b)

    msg = UserMessage(content="Broadcast")
    await bus._notify_subscribers(msg)

    assert len(received_a) == 1
    assert len(received_b) == 1


@pytest.mark.asyncio
async def test_type_specific_delivery(bus):
    received = []

    async def callback(msg):
        received.append(msg)

    bus.subscribe(AgentResponse, callback)

    msg = UserMessage(content="Wrong type")
    await bus._notify_subscribers(msg)

    assert len(received) == 0


@pytest.mark.asyncio
async def test_cross_type_delivery_for_base_message(bus):
    """Subscribers to Message base class should receive all message types."""
    received = []

    async def callback(msg):
        received.append(msg)

    bus.subscribe(Message, callback)

    msg = UserMessage(content="Any message")
    await bus._notify_subscribers(msg)

    # UserMessage inherits from Message
    assert len(received) == 1


@pytest.mark.asyncio
async def test_callback_error_does_not_crash_bus(bus):
    """An error in one callback should not prevent others from running."""

    async def bad_callback(msg):
        raise RuntimeError("Callback error")

    good_received = []

    async def good_callback(msg):
        good_received.append(msg)

    bus.subscribe(UserMessage, bad_callback)
    bus.subscribe(UserMessage, good_callback)

    msg = UserMessage(content="Test")
    await bus._notify_subscribers(msg)

    assert len(good_received) == 1


@pytest.mark.asyncio
async def test_publish_queues_message(bus):
    msg = UserMessage(content="Queued")
    await bus.publish(msg)
    assert not bus._queue.empty()
