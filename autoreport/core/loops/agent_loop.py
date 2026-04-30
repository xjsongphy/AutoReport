"""Agent Loop - core agent processing engine."""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from ...config.schema import AgentDefaults
from ...core.prompts import PromptLoader
from ...core.providers.base import LLMProvider
from ...core.providers.base import Message as LLMMessage
from ...core.providers.base import ToolResult as LLMToolResult
from ...interfaces.protocol import GUIAPI
from ...interfaces.types import (
    AgentStatus,
    AgentType,
    Message,
    UserMessage,
)
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
        llm_provider: LLMProvider,
        prompt_loader: PromptLoader | None = None,
    ):
        """Initialize agent loop.

        Args:
            agent_type: Type of this agent.
            workspace: Project workspace directory.
            tools: Tool registry for this agent.
            bus: Message bus for communication.
            gui: GUI API for sending messages.
            config: Agent configuration.
            llm_provider: LLM provider for generating responses.
            prompt_loader: Optional custom PromptLoader instance.
        """
        self.agent_type = agent_type
        self.workspace = Path(workspace).resolve()
        self.tools = tools
        self.bus = bus
        self.gui = gui
        self.config = config
        self.llm_provider = llm_provider

        # Initialize prompt loader
        self._prompt_loader = prompt_loader or PromptLoader()
        self._identity_prompt: str | None = None
        self._full_prompt_loaded = False

        self._status = AgentStatus.IDLE
        self._running = False
        self._message_queue: asyncio.Queue[UserMessage] = asyncio.Queue()
        self._current_message: UserMessage | None = None
        self._conversation_history: list[LLMMessage] = []

        # Debug mode
        self._debug_mode = False

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

            # Call LLM
            response = await self.llm_provider.chat(
                messages=messages,
                tools=tool_definitions if tool_definitions else None,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            # Handle tool calls if present
            if response.tool_calls:
                await self._handle_tool_calls(response, message.message_id)

            # Handle text response
            if response.content:
                self._conversation_history.append(
                    LLMMessage(role="assistant", content=response.content)
                )

                await self.gui.display_agent_message(
                    agent_type=str(self.agent_type),
                    content=response.content,
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

    async def _handle_tool_calls(
        self,
        response,
        user_message_id: str | None,
    ) -> None:
        """Handle tool calls from LLM response.

        Args:
            response: LLM response with tool calls.
            user_message_id: Original user message ID.
        """
        max_iterations = self.config.max_tool_iterations
        iteration = 0

        # Start with current conversation history
        current_messages = list(self._conversation_history)

        while response.tool_calls and iteration < max_iterations:
            iteration += 1
            logger.debug(
                "Tool iteration {} for agent: {}, tool_calls: {}",
                iteration,
                self.agent_type,
                len(response.tool_calls),
            )

            # Add assistant message with tool calls to conversation
            # This creates a placeholder for the assistant's tool call response
            tool_call_content = self._format_tool_calls_for_conversation(response.tool_calls)
            current_messages.append(
                LLMMessage(role="assistant", content=tool_call_content)
            )

            # Track pending tool calls
            tool_results = []

            # Execute each tool call
            for tool_call in response.tool_calls:
                await self._set_status(AgentStatus.RUNNING_TOOL)

                # Notify GUI about tool call
                await self.gui.show_tool_call(
                    agent_type=str(self.agent_type),
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                )

                # Execute tool
                try:
                    tool = self.tools.get(tool_call.name)
                    if tool is None:
                        raise ValueError(f"Tool not found: {tool_call.name}")

                    result = await tool(**tool_call.arguments)

                    # Notify GUI about result
                    await self.gui.show_tool_result(
                        agent_type=str(self.agent_type),
                        tool_name=tool_call.name,
                        result=result,
                    )

                    # Format result for LLM
                    result_str = self._format_tool_result(result)
                    tool_results.append(
                        LLMToolResult(
                            tool_call_id=tool_call.id,
                            content=result_str,
                        )
                    )

                except Exception as e:
                    logger.error("Tool execution error: {}", e)
                    error_msg = f"Error executing {tool_call.name}: {str(e)}"

                    await self.gui.show_tool_result(
                        agent_type=str(self.agent_type),
                        tool_name=tool_call.name,
                        result=None,
                        error=error_msg,
                    )

                    tool_results.append(
                        LLMToolResult(
                            tool_call_id=tool_call.id,
                            content=error_msg,
                        )
                    )

            # Add tool results as user message to conversation
            tool_results_content = self._format_tool_results_for_conversation(tool_results)
            current_messages.append(
                LLMMessage(role="user", content=tool_results_content)
            )

            # Call LLM again with updated conversation
            await self._set_status(AgentStatus.THINKING)

            # Get tool definitions again
            tool_definitions = self.tools.get_definitions()

            # Call LLM with current conversation history (now includes tool calls and results)
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

        # Save the complete conversation back to history
        self._conversation_history = current_messages

        if iteration >= max_iterations:
            logger.warning("Max tool iterations reached for agent: {}", self.agent_type)

    def _format_tool_calls_for_conversation(self, tool_calls: list) -> str:
        """Format tool calls for conversation history.

        Args:
            tool_calls: List of tool calls.

        Returns:
            Formatted string describing tool calls.
        """
        parts = []
        for tc in tool_calls:
            args_str = ", ".join(f"{k}={v}" for k, v in tc.arguments.items())
            parts.append(f"[Tool Call: {tc.name}({args_str})]")
        return " | ".join(parts)

    def _format_tool_results_for_conversation(self, tool_results: list) -> str:
        """Format tool results for conversation history.

        Args:
            tool_results: List of tool results.

        Returns:
            Formatted string describing tool results.
        """
        parts = []
        for tr in tool_results:
            # Truncate long results
            result = tr.content
            if len(result) > 500:
                result = result[:497] + "..."
            parts.append(f"[Tool Result for {tr.tool_call_id}: {result}]")
        return "\n".join(parts)

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
        """Set agent status and notify GUI.

        Args:
            status: New agent status.
        """
        self._status = status

        # In debug mode, use DEBUG_MODE status
        display_status = AgentStatus.DEBUG_MODE if self._debug_mode else status

        await self.gui.update_agent_status(
            agent_type=str(self.agent_type),
            status=str(display_status),
        )

    def set_debug_mode(self, enabled: bool) -> None:
        """Enable or disable debug mode.

        Args:
            enabled: Whether debug mode is enabled.
        """
        self._debug_mode = enabled

        if enabled:
            logger.info("Debug mode enabled for agent: {}", self.agent_type)
        else:
            logger.info("Debug mode disabled for agent: {}", self.agent_type)

    @property
    def debug_mode(self) -> bool:
        """Check if debug mode is enabled.

        Returns:
            True if debug mode is enabled.
        """
        return self._debug_mode

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
            # Combine identity and full prompts
            complete_prompt = f"{self._identity_prompt}\n\n{full_prompt}"
            self._full_prompt_loaded = True
            return complete_prompt

        # Return cached complete prompt
        return f"{self._identity_prompt}\n\n{self._prompt_loader.load_full(agent_type_str)}"

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
