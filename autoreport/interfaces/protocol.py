"""Communication protocol between GUI and backend."""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from .types import Message


class MessageChannel(ABC):
    """Abstract message channel for GUI-backend communication."""

    @abstractmethod
    async def send(self, message: Message) -> None:
        """Send a message through the channel."""

    @abstractmethod
    def subscribe(
        self,
        message_type: type[Message],
        callback: Callable[[Message], Awaitable[None]]
    ) -> None:
        """Subscribe to a specific message type."""


class BackendAPI(ABC):
    """Abstract backend API for GUI to call."""

    @abstractmethod
    async def send_user_message(
        self,
        content: str,
        agent_type: str,
        message_id: str | None = None,
        source: str = "user",
    ) -> None:
        """Send a user message to an agent.

        Args:
            content: Message content.
            agent_type: Target agent type.
            message_id: Optional message ID for tracking.
            source: "user" for direct input, "main_agent" for coordination.
        """

    @abstractmethod
    async def interrupt_current_message(self, agent_type: str) -> None:
        """Interrupt the currently processing message for an agent."""

    @abstractmethod
    async def restart_agents(self, reason: str) -> None:
        """Restart the agent system."""

    @abstractmethod
    async def switch_provider(self, provider: str) -> None:
        """Switch to a different provider."""

    @abstractmethod
    async def switch_model(self, model: str) -> None:
        """Switch to a different model."""

    @abstractmethod
    async def rollback_to_checkpoint(self, checkpoint_id: str) -> None:
        """Rollback to a specific checkpoint."""

    @abstractmethod
    def set_agent_debug_mode(self, agent_type: str, enabled: bool) -> None:
        """Enable or disable debug mode for an agent."""

    @abstractmethod
    def subscribe_to_messages(
        self,
        callback: Callable[[Message], Awaitable[None]]
    ) -> None:
        """Subscribe to all backend messages."""


class GUIAPI(ABC):
    """Abstract GUI API for backend to call."""

    @abstractmethod
    async def display_agent_message(
        self,
        agent_type: str,
        content: str,
        message_id: str | None = None
    ) -> None:
        """Display an agent message in GUI."""

    @abstractmethod
    async def show_tool_call(
        self,
        agent_type: str,
        tool_name: str,
        arguments: dict
    ) -> None:
        """Show a tool being executed."""

    @abstractmethod
    async def show_tool_result(
        self,
        agent_type: str,
        tool_name: str,
        result: any,
        error: str | None = None
    ) -> None:
        """Show a tool result."""

    @abstractmethod
    async def update_agent_status(
        self,
        agent_type: str,
        status: str,
        extra: dict | None = None
    ) -> None:
        """Update agent status display."""

    @abstractmethod
    async def show_error(
        self,
        source: str,
        message: str,
        details: dict | None = None
    ) -> None:
        """Show an error in GUI."""

    @abstractmethod
    async def add_checkpoint(
        self,
        checkpoint_id: str,
        description: str,
        file_states: dict
    ) -> None:
        """Add a checkpoint to the timeline."""
