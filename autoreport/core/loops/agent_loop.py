"""Agent Loop - core agent processing engine."""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from ...config.schema import AgentDefaults
from ...interfaces.types import (
    AgentType,
    AgentStatus,
    UserMessage,
    AgentResponse,
    ToolCall,
    ToolResult,
    StatusChange,
    Error,
    Message,
)
from ...interfaces.protocol import GUIAPI
from ..tools.registry import ToolRegistry
from .bus import MessageBus


class AgentLoop:
    """Agent loop for processing user messages and generating responses."""

    def __init__(
        self,
        agent_type: AgentType,
        workspace: Path,
        tools: ToolRegistry,
        bus: MessageBus,
        gui: GUIAPI,
        config: AgentDefaults,
    ):
        """Initialize agent loop.

        Args:
            agent_type: Type of this agent.
            workspace: Project workspace directory.
            tools: Tool registry for this agent.
            bus: Message bus for communication.
            gui: GUI API for sending messages.
            config: Agent configuration.
        """
        self.agent_type = agent_type
        self.workspace = Path(workspace).resolve()
        self.tools = tools
        self.bus = bus
        self.gui = gui
        self.config = config

        self._status = AgentStatus.IDLE
        self._running = False
        self._message_queue: asyncio.Queue[UserMessage] = asyncio.Queue()
        self._current_message: UserMessage | None = None

        # Subscribe to user messages for this agent type
        self.bus.subscribe(UserMessage, self._handle_user_message)

    @property
    def status(self) -> AgentStatus:
        """Get current agent status."""
        return self._status

    async def start(self) -> None:
        """Start the agent loop."""
        if self._running:
            return

        self._running = True
        logger.info("Starting agent loop for {}", self.agent_type)

        # Start processing task
        asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Stop the agent loop."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping agent loop for {}", self.agent_type)

    async def _process_loop(self) -> None:
        """Main processing loop for messages."""
        while self._running:
            try:
                # Wait for next message
                message = await self._message_queue.get()
                self._current_message = message

                await self._process_message(message)

            except Exception as e:
                logger.error("Error in agent loop for {}: {}", self.agent_type, e)
                await self.gui.show_error(
                    source=str(self.agent_type),
                    message=str(e),
                )

    async def _handle_user_message(self, message: Message) -> None:
        """Handle user message from bus.

        Args:
            message: User message.
        """
        if not isinstance(message, UserMessage):
            return

        # Check if message is for this agent
        if message.agent_type != self.agent_type:
            return

        await self._message_queue.put(message)

    async def _process_message(self, message: UserMessage) -> None:
        """Process a user message.

        Args:
            message: User message to process.
        """
        await self._set_status(AgentStatus.THINKING)

        try:
            # TODO: Implement LLM call and tool execution
            # For now, send a simple response
            response = f"Agent {self.agent_type} received: {message.content}"

            await self.gui.display_agent_message(
                agent_type=str(self.agent_type),
                content=response,
                message_id=message.message_id,
            )

            await self._set_status(AgentStatus.IDLE)

        except Exception as e:
            logger.error("Error processing message in {}: {}", self.agent_type, e)
            await self._set_status(AgentStatus.ERROR)
            await self.gui.show_error(
                source=str(self.agent_type),
                message=str(e),
            )

    async def _set_status(self, status: AgentStatus) -> None:
        """Set agent status and notify GUI.

        Args:
            status: New agent status.
        """
        self._status = status
        await self.gui.update_agent_status(
            agent_type=str(self.agent_type),
            status=str(status),
        )
