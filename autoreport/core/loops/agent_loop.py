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
from ...core.providers.base import LLMProvider, Message as LLMMessage, ToolResult as LLMToolResult
from ..tools.registry import ToolRegistry
from .bus import MessageBus


class AgentLoop:
    """Agent loop for processing user messages and generating responses."""

    # System prompts for each agent type
    SYSTEM_PROMPTS = {
        AgentType.MAIN: """You are the Main Agent for an automated physics experiment report writing system.

Your role is to:
1. Coordinate the work of sub-agents (data analysis, plotting, theory, report)
2. Communicate with the user to understand requirements
3. Make decisions about which sub-agent should handle which task
4. Review and integrate the outputs from sub-agents

You have access to various tools for file operations, PDF parsing, and execution.
Use these tools to help manage the project and coordinate with sub-agents.""",

        AgentType.DATA_ANALYSIS: """You are the Data Analysis Agent for a physics experiment report writing system.

Your role is to:
1. Read experimental data from CSV/Excel files
2. Process and analyze the data
3. Perform statistical calculations
4. Generate summary results for the report

You have access to file operations and Python execution tools.
Focus on accurate data analysis and clear presentation of results.""",

        AgentType.PLOTTING: """You are the Plotting Agent for a physics experiment report writing system.

Your role is to:
1. Create data visualizations based on analysis results
2. Generate charts and graphs using matplotlib
3. Save plots as image files for the report
4. Ensure plots are properly labeled and formatted

You have access to file operations, Python execution, and image creation tools.
Focus on clear, publication-quality visualizations.""",

        AgentType.THEORY: """You are the Theory Agent for a physics experiment report writing system.

Your role is to:
1. Analyze reference materials and experimental requirements
2. Derive relevant theoretical formulas and explanations
3. Provide theoretical background for the experiment
4. Ensure theoretical accuracy and completeness

You have access to file operations and PDF reference materials.
Focus on clear, accurate theoretical explanations.""",

        AgentType.REPORT: """You are the Report Writing Agent for a physics experiment report writing system.

Your role is to:
1. Integrate all outputs from other agents
2. Write complete LaTeX report sections
3. Ensure proper formatting and structure
4. Compile LaTeX to generate final PDF

You have access to file operations, LaTeX compilation, and all project outputs.
Focus on producing a well-structured, professional report.""",
    }

    def __init__(
        self,
        agent_type: AgentType,
        workspace: Path,
        tools: ToolRegistry,
        bus: MessageBus,
        gui: GUIAPI,
        config: AgentDefaults,
        llm_provider: LLMProvider,
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
        """
        self.agent_type = agent_type
        self.workspace = Path(workspace).resolve()
        self.tools = tools
        self.bus = bus
        self.gui = gui
        self.config = config
        self.llm_provider = llm_provider

        self._status = AgentStatus.IDLE
        self._running = False
        self._message_queue: asyncio.Queue[UserMessage] = asyncio.Queue()
        self._current_message: UserMessage | None = None
        self._conversation_history: list[LLMMessage] = []

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
            # Add user message to conversation history
            self._conversation_history.append(
                LLMMessage(role="user", content=message.content)
            )

            # Get system prompt
            system_prompt = self.SYSTEM_PROMPTS.get(
                self.agent_type,
                "You are a helpful assistant."
            )

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

        current_messages = self._conversation_history.copy()

        while response.tool_calls and iteration < max_iterations:
            iteration += 1
            logger.debug(
                "Tool iteration {} for agent: {}, tool_calls: {}",
                iteration,
                self.agent_type,
                len(response.tool_calls),
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

            # Call LLM again with tool results
            await self._set_status(AgentStatus.THINKING)

            # Get tool definitions again
            tool_definitions = self.tools.get_definitions()

            # Call LLM with tool results
            response = await self.llm_provider.chat_with_tools(
                messages=current_messages,
                tool_results=tool_results,
                tools=tool_definitions,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            # Update messages for next iteration
            # (In a full implementation, we'd track assistant messages with tool calls)

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
        """Set agent status and notify GUI.

        Args:
            status: New agent status.
        """
        self._status = status
        await self.gui.update_agent_status(
            agent_type=str(self.agent_type),
            status=str(status),
        )
