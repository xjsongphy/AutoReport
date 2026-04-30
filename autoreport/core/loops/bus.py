"""Message bus for async communication between components."""

import asyncio
from typing import Callable, Awaitable
from loguru import logger

from ...interfaces.types import Message


class MessageBus:
    """Async message bus for pub/sub communication."""

    def __init__(self) -> None:
        """Initialize message bus."""
        self._subscribers: dict[type[Message], list[Callable]] = {}
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[Message] = asyncio.Queue()

    async def publish(self, message: Message) -> None:
        """Publish a message to all subscribers.

        Args:
            message: Message to publish.
        """
        await self._queue.put(message)
        logger.debug("Published message: {}", message.type)

    async def process_queue(self) -> None:
        """Process messages from queue and notify subscribers."""
        while True:
            message = await self._queue.get()
            await self._notify_subscribers(message)

    async def _notify_subscribers(self, message: Message) -> None:
        """Notify all subscribers for a message type."""
        message_type = type(message)
        callbacks = []

        async with self._lock:
            # Get callbacks for exact message type
            callbacks.extend(self._subscribers.get(message_type, []))

            # Also check parent classes for inheritance
            for msg_type, subs in self._subscribers.items():
                if msg_type != message_type and isinstance(message, msg_type):
                    callbacks.extend(subs)

        # Notify all callbacks
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error("Error in subscriber callback: {}", e)

    def subscribe(
        self,
        message_type: type[Message],
        callback: Callable[[Message], Awaitable[None] | None]
    ) -> None:
        """Subscribe to a message type.

        Args:
            message_type: Type of message to subscribe to.
            callback: Callback function for messages.
        """
        # Note: This is not async, so we can't use async with
        # For simplicity in this implementation, we're not locking here
        # In production, you'd want to use threading.Lock or restructure
        if message_type not in self._subscribers:
            self._subscribers[message_type] = []
        self._subscribers[message_type].append(callback)
        logger.debug("Subscribed to message type: {}", message_type.__name__)

    def unsubscribe(
        self,
        message_type: type[Message],
        callback: Callable[[Message], Awaitable[None] | None]
    ) -> None:
        """Unsubscribe from a message type.

        Args:
            message_type: Type of message to unsubscribe from.
            callback: Callback to remove.
        """
        if message_type in self._subscribers:
            try:
                self._subscribers[message_type].remove(callback)
                logger.debug("Unsubscribed from message type: {}", message_type.__name__)
            except ValueError:
                pass
