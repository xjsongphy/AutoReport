"""Agent Loop - core agent processing engine."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .manager import LoopManager

from loguru import logger

from ...config.schema import AgentDefaults
from ...core.prompts import PromptLoader
from ...core.providers.base import LLMProvider
from ...core.providers.base import Message as LLMMessage
from ...interfaces.types import (
    AgentFeedback,
    AgentResponse,
    AgentStatus,
    AgentType,
    Error,
    Message,
    StatusChange,
    UserMessage,
)
from ...interfaces.types import (
    ToolCall as ToolCallMsg,
)
from ...interfaces.types import (
    ToolResult as ToolResultMsg,
)
from ..tools.registry import ToolRegistry
from .bus import MessageBus


class AgentLoop:
    """Agent loop for processing user messages and generating responses.

    All GUI communication goes through the MessageBus as typed messages.
    The GUI subscribes to the bus and handles them.
    """

    def __init__(
        self,
        agent_type: AgentType,
        workspace: Path,
        tools: ToolRegistry,
        bus: MessageBus,
        config: AgentDefaults,
        llm_provider: LLMProvider,
        prompt_loader: PromptLoader | None = None,
        loop_manager: LoopManager | None = None,
    ):
        """Initialize agent loop.

        Args:
            agent_type: Type of this agent.
            workspace: Project workspace directory.
            tools: Tool registry for this agent.
            bus: Message bus for communication.
            config: Agent configuration.
            llm_provider: LLM provider for generating responses.
            prompt_loader: Optional custom PromptLoader instance.
            loop_manager: Optional LoopManager reference for coordination.
        """
        self.agent_type = agent_type
        self.workspace = Path(workspace).resolve()
        self.tools = tools
        self.bus = bus
        self.config = config
        self.llm_provider = llm_provider
        self._loop_manager = loop_manager

        self._prompt_loader = prompt_loader or PromptLoader()
        self._identity_prompt: str | None = None
        self._full_prompt_loaded = False
        self._cached_full_prompt: str | None = None

        self._status = AgentStatus.IDLE
        self._running = False
        self._message_queue: asyncio.Queue[UserMessage] = asyncio.Queue()
        self._current_message: UserMessage | None = None
        self._conversation_history: list[LLMMessage] = []

        # Debug mode
        self._debug_mode = False
        self._bus_callback = self._handle_user_message

        # Subscribe to user messages for this agent type
        self.bus.subscribe(UserMessage, self._bus_callback)

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
                # Wait for next message with timeout so stop() can break out
                try:
                    message = await asyncio.wait_for(
                        self._message_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                self._current_message = message
                await self._process_message(message)

            except Exception as e:
                logger.error("Error in agent loop for {}: {}", self.agent_type, e)
                await self.bus.publish(Error(
                    source=str(self.agent_type),
                    message=str(e),
                ))

    async def _handle_user_message(self, message: Message) -> None:
        """Handle user message from bus.

        In debug mode, only direct user input is accepted;
        main-agent coordination commands are silently dropped.

        Args:
            message: User message.
        """
        if not isinstance(message, UserMessage):
            return

        # Check if message is for this agent
        if message.agent_type != self.agent_type:
            return

        # Debug mode: ignore main-agent coordination
        if self._debug_mode and message.source == "main_agent":
            logger.debug(
                "Debug mode: ignoring main-agent message for {}: {}",
                self.agent_type,
                message.content[:80],
            )
            return

        await self._message_queue.put(message)

    async def _process_message(self, message: UserMessage) -> None:
        """Process a user message.

        Args:
            message: User message to process.
        """
        await self._set_status(AgentStatus.THINKING)

        try:
            # In debug mode, wrap message with context
            content = message.content
            if self._debug_mode:
                content = (
                    "[调试模式] 此 Agent 处于独立调试模式，不与其他 Agent 通信。\n"
                    "你可以直接测试此 Agent 的工具和输出。\n\n"
                    + content
                )

            # Add user message to conversation history
            self._conversation_history.append(
                LLMMessage(role="user", content=content)
            )

            # Get system prompt with progressive loading
            system_prompt = await self._get_system_prompt()

            # Prepare messages with system prompt
            messages = [LLMMessage(role="system", content=system_prompt)]
            messages.extend(self._conversation_history)

            # Get tool definitions
            tool_definitions = self.tools.get_definitions()

            # Call LLM with streaming (default)
            accumulated_content = ""
            accumulated_tool_calls = []

            async for chunk in self.llm_provider.chat_stream(
                messages=messages,
                tools=tool_definitions if tool_definitions else None,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            ):
                if chunk.delta:
                    accumulated_content += chunk.delta
                    # Stream chunk to UI
                    await self.bus.publish(AgentResponse(
                        agent_type=self.agent_type,
                        content=chunk.delta,
                        message_id=message.message_id,
                        streaming=True,
                    ))

                if chunk.tool_calls:
                    accumulated_tool_calls = chunk.tool_calls

                if chunk.done:
                    # Stream complete
                    if accumulated_content:
                        self._conversation_history.append(
                            LLMMessage(role="assistant", content=accumulated_content)
                        )
                    break

            # Handle tool calls if present
            if accumulated_tool_calls:
                @dataclass
                class StreamResponse:
                    content: str
                    tool_calls: list

                response = StreamResponse(
                    content=accumulated_content,
                    tool_calls=accumulated_tool_calls,
                )
                await self._handle_tool_calls(response, message.message_id)

            # Send final completion signal (empty content, streaming=False)
            await self.bus.publish(AgentResponse(
                agent_type=self.agent_type,
                content="",  # Empty to signal completion
                message_id=message.message_id,
                streaming=False,  # Final message
            ))

            await self._set_status(AgentStatus.IDLE)

        except Exception as e:
            logger.error("Error processing message in {}: {}", self.agent_type, e)
            await self._set_status(AgentStatus.ERROR)
            await self.bus.publish(Error(
                source=str(self.agent_type),
                message=str(e),
            ))

    async def _handle_tool_calls(
        self,
        response,
        user_message_id: str | None,
    ) -> None:
        """Handle tool calls from LLM response.

        Stores structured messages (not formatted text) so each provider
        can convert them to the correct API format.
        """
        max_iterations = self.config.max_tool_iterations
        iteration = 0

        current_messages = list(self._conversation_history)

        while response.tool_calls and iteration < max_iterations:
            iteration += 1
            logger.debug(
                "Tool iteration {} for agent: {}, tool_calls: {}",
                iteration,
                self.agent_type,
                len(response.tool_calls),
            )

            # Add assistant message with tool calls as structured data
            current_messages.append(LLMMessage(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls,
            ))

            # Execute each tool call and add results as structured messages
            for tool_call in response.tool_calls:
                await self._set_status(AgentStatus.RUNNING_TOOL)

                await self.bus.publish(ToolCallMsg(
                    agent_type=self.agent_type,
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                ))

                try:
                    tool = self.tools.get(tool_call.name)
                    if tool is None:
                        raise ValueError(f"Tool not found: {tool_call.name}")

                    result = await tool(**tool_call.arguments)

                    await self.bus.publish(ToolResultMsg(
                        agent_type=self.agent_type,
                        tool_name=tool_call.name,
                        result=result,
                    ))

                    result_str = self._format_tool_result(result)

                except Exception as e:
                    logger.error("Tool execution error: {}", e)
                    error_msg = f"Error executing {tool_call.name}: {str(e)}"

                    await self.bus.publish(ToolResultMsg(
                        agent_type=self.agent_type,
                        tool_name=tool_call.name,
                        result=None,
                        error=error_msg,
                    ))
                    result_str = error_msg

                # Add tool result as structured message
                current_messages.append(LLMMessage(
                    role="tool",
                    content=result_str,
                    tool_call_id=tool_call.id,
                    is_tool_result=True,
                ))

            # Call LLM again with updated conversation
            await self._set_status(AgentStatus.THINKING)

            tool_definitions = self.tools.get_definitions()

            response = await self.llm_provider.chat(
                messages=current_messages,
                tools=tool_definitions,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

        # Update conversation history with final response
        if response.content:
            current_messages.append(
                LLMMessage(role="assistant", content=response.content)
            )

        self._conversation_history = current_messages

        if iteration >= max_iterations:
            logger.warning("Max tool iterations reached for agent: {}", self.agent_type)

    def _format_tool_result(self, result: Any) -> str:
        """Format tool result for LLM.

        Args:
            result: Tool result.

        Returns:
            Formatted result string.
        """
        if isinstance(result, dict):
            # Format dictionary result
            return str(result)
        elif isinstance(result, str):
            return result
        else:
            return str(result)

    async def _set_status(self, status: AgentStatus) -> None:
        """Set agent status and notify GUI via bus.

        Args:
            status: New agent status.
        """
        self._status = status

        # In debug mode, use DEBUG_MODE status
        display_status = AgentStatus.DEBUG_MODE if self._debug_mode else status

        await self.bus.publish(StatusChange(
            agent_type=self.agent_type,
            status=display_status,
        ))

    def set_debug_mode(self, enabled: bool) -> None:
        """Enable or disable debug mode.

        When enabled, unsubscribes from the MessageBus entirely so the
        agent only processes direct user input (no Main Agent coordination).
        When disabled, re-subscribes to the bus.

        Args:
            enabled: Whether debug mode is enabled.
        """
        self._debug_mode = enabled

        if enabled:
            self.bus.unsubscribe(UserMessage, self._bus_callback)
            logger.info("Debug mode enabled for agent: {} (unsubscribed from bus)", self.agent_type)
        else:
            self.bus.subscribe(UserMessage, self._bus_callback)
            logger.info("Debug mode disabled for agent: {} (re-subscribed to bus)", self.agent_type)

    @property
    def debug_mode(self) -> bool:
        """Check if debug mode is enabled.

        Returns:
            True if debug mode is enabled.
        """
        return self._debug_mode

    async def send_to_sub_agent(
        self,
        agent_type: AgentType,
        content: str,
        message_id: str | None = None,
    ) -> None:
        """Send coordination message from main agent to sub-agent.

        Only main agent can send coordination messages. Target agents in
        debug mode will not receive coordination messages.

        Args:
            agent_type: Target sub-agent type.
            content: Message content to send.
            message_id: Optional message ID for tracking.

        Raises:
            RuntimeError: If called from a non-main agent.
        """
        if self.agent_type != AgentType.MAIN:
            raise RuntimeError("Only main agent can send coordination messages")

        if self._loop_manager is None:
            logger.warning("Loop manager not available, cannot send coordination message")
            return

        # Check if target agent is in debug mode
        target_loop = self._loop_manager.get_loop(agent_type)
        if target_loop and target_loop.debug_mode:
            logger.debug(
                "Target agent {} is in debug mode, skipping coordination",
                agent_type,
            )
            return

        await self.bus.publish(UserMessage(
            content=content,
            agent_type=agent_type,
            message_id=message_id,
            source="main_agent",
        ))
        logger.info("Main agent sent coordination message to {}", agent_type)

    async def send_feedback(
        self,
        content: str,
        feedback_type: str = "issue_report",
    ) -> None:
        """Send structured feedback from sub-agent to main agent.

        Sub-agents use this to report issues, completion status, or queries
        that require main agent intervention. Only sub-agents can send
        feedback.

        Args:
            content: Feedback message content.
            feedback_type: Type of feedback — "issue_report", "completion",
                or "query".

        Raises:
            RuntimeError: If called from the main agent.
        """
        if self.agent_type == AgentType.MAIN:
            raise RuntimeError("Main agent cannot send feedback to itself")

        await self.bus.publish(AgentFeedback(
            agent_type=self.agent_type,
            content=content,
            feedback_type=feedback_type,
        ))
        logger.info(
            "{} sent feedback to main agent (type={}): {}",
            self.agent_type,
            feedback_type,
            content[:80],
        )

    async def _get_system_prompt(self) -> str:
        """Get system prompt with progressive loading.

        Returns:
            Complete system prompt (identity + full instructions).

        Progressive loading strategy:
        - First call: Load identity (fast startup)
        - Subsequent calls: Load full prompt (detailed instructions)
        """
        agent_type_str = self._get_agent_type_str()

        # First call: load identity only
        if self._identity_prompt is None:
            logger.debug("Loading identity prompt for agent: {}", self.agent_type)
            self._identity_prompt = self._prompt_loader.load_identity(agent_type_str)
            return self._identity_prompt

        # Check if we need to load full prompt
        if not self._full_prompt_loaded:
            logger.debug("Loading full prompt for agent: {}", self.agent_type)
            full_prompt = self._prompt_loader.load_full(agent_type_str)
            self._cached_full_prompt = f"{self._identity_prompt}\n\n{full_prompt}"
            self._full_prompt_loaded = True
            return self._cached_full_prompt

        # Return cached complete prompt
        return self._cached_full_prompt

    def _get_agent_type_str(self) -> str:
        """Convert AgentType to string for prompt loading.

        Returns:
            Agent type string identifier.
        """
        type_mapping = {
            AgentType.MAIN: "main",
            AgentType.DATA_ANALYSIS: "data_analysis",
            AgentType.PLOTTING: "plotting",
            AgentType.THEORY: "theory",
            AgentType.REPORT: "report",
        }
        return type_mapping.get(self.agent_type, str(self.agent_type).lower())
