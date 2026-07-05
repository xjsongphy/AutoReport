"""Agent Loop - core agent processing engine."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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
    AgentResponse,
    AgentStatus,
    AgentType,
    ApiDebugMessage,
    Error,
    Message,
    QueueUpdateMessage,
    ReportMessage,
    StatusChange,
    SystemNotice,
    TaskStatus,
    TaskUpdateMessage,
    ToolCallMessage,
    UserMessage,
)
from ...interfaces.types import (
    ToolResult as ToolResultMsg,
)
from ...utils.agent_labels import get_agent_badge
from ..tools import SkillLoader
from ..tools.manifest_tool import ManifestManager, ManifestTool
from ..tools.registry import ToolRegistry
from .bus import MessageBus

# Tokens per char heuristic (cl100k_base averages ~0.25 tokens/char for code, ~0.3 for text)
_TOKENS_PER_CHAR = 0.3
_SAFETY_BUFFER = 1024  # Extra buffer for tool definitions and overhead


def _estimate_tokens(messages: list[LLMMessage]) -> int:
    """Rough token count — ~4 chars per token, plus per-message overhead."""
    total = 0
    for m in messages:
        total += 4  # Per-message overhead
        if m.content:
            total += int(len(m.content) * _TOKENS_PER_CHAR)
        if getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                total += 20  # Tool call overhead
                if hasattr(tc, "arguments") and tc.arguments:
                    total += int(len(str(tc.arguments)) * _TOKENS_PER_CHAR)
        if getattr(m, "thinking", None) and m.thinking:
            total += int(len(m.thinking) * _TOKENS_PER_CHAR)
    return total


def _trim_messages_to_budget(
    messages: list[LLMMessage],
    context_window: int = 128000,
    max_output: int = 4096,
) -> list[LLMMessage]:
    """Trim oldest messages to stay within context budget.

    Inspired by nanobot's SnipHistory: walk from the end, keep messages
    that fit within the budget, preserve user-turn boundaries.
    """
    budget = context_window - max_output - _SAFETY_BUFFER
    estimated = _estimate_tokens(messages)
    if estimated <= budget:
        return messages

    logger.info(
        "Context auto-compact: {} tokens exceed budget {} → trimming",
        estimated,
        budget,
    )

    # Always keep system message (index 0)
    system_msg = messages[0]
    rest = messages[1:]

    # Walk backwards, accumulate tokens
    kept = []
    kept_tokens = 0
    for m in reversed(rest):
        mt = _estimate_tokens([m])
        if kept_tokens + mt <= budget:
            kept.insert(0, m)
            kept_tokens += mt
        else:
            break

    # Ensure the boundary is legal.
    # 1. Strip orphan 'tool' messages whose 'assistant(tool_calls)' was trimmed.
    # 2. Strip orphan 'assistant' messages whose preceding 'user' was trimmed.
    # 3. The first real message after system must be 'user'.
    # 4. Anthropic-style tool results (role="user", is_tool_result=True) whose
    #    'assistant(tool_calls)' was trimmed.
    while kept:
        role = kept[0].role
        is_tool_result = getattr(kept[0], "is_tool_result", False)
        if role == "tool":
            logger.debug("Stripping orphan tool message at trim boundary")
            kept.pop(0)
        elif role == "assistant":
            logger.debug("Stripping orphan assistant message at trim boundary")
            kept.pop(0)
        elif role == "user" and is_tool_result:
            # Anthropic-style orphan: tool result disguised as user message.
            # Without its preceding assistant(tool_calls), this would cause
            # an API error (tool result without tool_use).
            logger.debug("Stripping orphan user/tool_result message at trim boundary")
            kept.pop(0)
        else:
            break

    # Always prepend system prompt
    result = [system_msg] + kept

    logger.info(
        "Context compacted: {} → {} messages ({} → ~{} tokens)",
        len(messages),
        len(result),
        estimated,
        _estimate_tokens(result),
    )
    return result


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
        skill_loader: SkillLoader | None = None,
        manifest_manager: ManifestManager | None = None,
        task_board=None,
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
            skill_loader: Optional SkillLoader for skill injection.
        """
        self.agent_type = agent_type
        self.workspace = Path(workspace).resolve()
        self.tools = tools
        self.bus = bus
        self.config = config
        self.llm_provider = llm_provider
        self._loop_manager = loop_manager
        self._skill_loader = skill_loader
        self._manifest_manager = manifest_manager
        # Shared task board — used by the loop guards (must-report, main-blocked).
        self._task_board = task_board

        self._prompt_loader = prompt_loader or PromptLoader()
        self._cached_system_prompt: str | None = None
        self._cached_system_prompt_signature: tuple[Any, ...] | None = None

        self._status = AgentStatus.IDLE
        self._running = False
        self._message_queue: asyncio.Queue[UserMessage] = asyncio.Queue()
        self._current_message: UserMessage | None = None
        # Set True when this agent emits a ReportMessage during the current
        # turn. The turn-end guard checks it to enforce that a Main-dispatched
        # task ends with an explicit report.
        self._turn_reported: bool = False
        # Guard retry counters (reset each turn in _process_message).
        self._report_retries: int = 0
        self._main_block_retries: int = 0
        self._conversation_history: list[LLMMessage] = []
        self._current_session_id: str | None = None
        self._manifest_dirty = False
        self._cancel_event = asyncio.Event()
        self._consecutive_errors = 0

        # Debug mode
        self._debug_mode = False
        self._bus_callback = self._handle_user_message

        # Task update batching — coalesce rapid-fire notifications into one queue message
        self._task_batch: list[str] = []
        self._task_batch_timer: asyncio.TimerHandle | None = None

        # Subscribe to user messages for this agent type
        self.bus.subscribe(UserMessage, self._bus_callback)
        # Subscribe to task updates
        self.bus.subscribe(TaskUpdateMessage, self._handle_task_update)
        # All agents track their own report emissions (turn-reported flag).
        self.bus.subscribe(ReportMessage, self._handle_report_message)
        # Manifest tool is only for sub-agents
        if self.agent_type != AgentType.MAIN and self._manifest_manager is not None:
            self.tools.register(ManifestTool(self._manifest_manager, self._get_agent_type_str()))

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
        await self._publish_queue_update()

        # Start processing task
        asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Stop the agent loop."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping agent loop for {}", self.agent_type)

    def cancel_current(self) -> None:
        """Cancel the currently processing message (if any)."""
        self._cancel_event.set()
        logger.info("Cancel requested for agent {}", self.agent_type)

    async def _process_loop(self) -> None:
        """Main processing loop for messages."""
        while self._running:
            try:
                # Wait for next message with timeout so stop() can break out
                try:
                    message = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                self._current_message = message
                await self._publish_queue_update()
                await self._process_message(message)

            except Exception as e:
                logger.error("Error in agent loop for {}: {}", self.agent_type, str(e))
                await self.bus.publish(
                    Error(
                        source=str(self.agent_type),
                        message=str(e),
                    )
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
        await self._publish_queue_update()

    async def _handle_task_update(self, message: Message) -> None:
        """Handle TaskUpdateMessage from the message bus.

        Task notifications are always delivered, even in debug mode.
        They are wrapped into a UserMessage(source="system") for LLM processing.

        Notification text is perspective-aware:
        - Agent as source (waiting): "等待 <target>：<description>"
        - Agent as target (todo): "完成 <source> 的任务：<description>"
        - Main agent: "<source> 等待 <target> 的 <description>"
        """
        if not isinstance(message, TaskUpdateMessage):
            return

        # use_enum_values=True may store enums as strings
        src_val = (
            message.source_agent.value
            if isinstance(message.source_agent, Enum)
            else str(message.source_agent)
        )
        tgt_val = (
            message.target_agent.value
            if isinstance(message.target_agent, Enum)
            else str(message.target_agent)
        )
        src_enum = AgentType(src_val) if src_val in [e.value for e in AgentType] else None
        tgt_enum = AgentType(tgt_val) if tgt_val in [e.value for e in AgentType] else None

        # Only process if relevant to this agent
        if self.agent_type not in (src_enum, tgt_enum):
            return

        am_source = self.agent_type == src_enum
        am_target = self.agent_type == tgt_enum
        is_local = src_enum == tgt_enum

        if is_local:
            logger.debug(
                "Local task update kept out of {} LLM queue: {}",
                self.agent_type,
                message.task_id,
            )
            return

        if message.action == "created":
            if am_source and self.agent_type == AgentType.MAIN:
                notification_text = f"[等待] {src_val} 等待 {tgt_val} 的：{message.brief}"
            elif am_source:
                notification_text = f"[等待] 等待 {tgt_val} 完成：{message.brief}"
            elif am_target and is_local:
                notification_text = f"[待办] 本地任务：{message.brief}"
            elif am_target:
                notification_text = f"[待办] 完成 {src_val} 的任务：{message.brief}"
            else:
                notification_text = f"[新任务] {src_val} → {tgt_val}：{message.brief}"

        elif message.action == "completed":
            if am_source:
                notification_text = f"[完成] {tgt_val} 已完成：{message.brief}。请检查其输出。"
            elif am_target:
                notification_text = f"[完成] 已完成 {src_val} 的任务：{message.brief}"
            elif self.agent_type == AgentType.MAIN:
                notification_text = f"[完成] {src_val} 等待 {tgt_val} 的任务已完成：{message.brief}"
            else:
                notification_text = f"[完成] {src_val} 完成了 {tgt_val} 的任务：{message.brief}"

        elif message.action == "started":
            if am_source:
                notification_text = f"[开始] {tgt_val} 已开始：{message.brief}"
            elif self.agent_type == AgentType.MAIN:
                notification_text = f"[开始] {tgt_val} 开始了 {src_val} 的任务：{message.brief}"
            else:
                notification_text = f"[开始] {src_val} 开始了：{message.brief}"

        elif message.action == "failed":
            if am_source:
                notification_text = (
                    f"[失败] {tgt_val} 失败：{message.brief}。请检查并决定如何处理。"
                )
            elif am_target:
                notification_text = f"[失败] 来自 {src_val} 的任务失败：{message.brief}"
            elif self.agent_type == AgentType.MAIN:
                notification_text = f"[失败] {src_val} 等待 {tgt_val} 的任务失败：{message.brief}"
            else:
                notification_text = f"[失败] {src_val} 任务失败 ({tgt_val})：{message.brief}"

        elif message.action == "cancelled":
            if am_source:
                notification_text = f"[取消] {tgt_val} 已取消：{message.brief}"
            elif self.agent_type == AgentType.MAIN:
                notification_text = f"[取消] {src_val} 等待 {tgt_val} 的任务已取消：{message.brief}"
            else:
                notification_text = f"[取消] {src_val} 任务已取消 ({tgt_val})：{message.brief}"

        else:
            notification_text = f"任务更新 {message.action}: {message.brief}"

        await self._message_queue.put(
            UserMessage(
                content=notification_text,
                agent_type=self.agent_type,
                source="system",
            )
        )
        await self._publish_queue_update()
        logger.debug("Task update delivered to {}: {}", self.agent_type, message.task_id)

    async def _handle_report_message(self, message: Message) -> None:
        """Mark this turn 'reported' when this agent emits a ReportMessage.

        The turn-end guard checks _turn_reported to enforce that a
        Main-dispatched task ends with an explicit report.
        """
        if not isinstance(message, ReportMessage):
            return
        if message.agent_type != self.agent_type:
            return
        self._turn_reported = True
        logger.debug(
            "{} turn reported (task={}, type={})",
            self.agent_type,
            message.task_id,
            message.report_type,
        )

    # ------------------------------------------------------------------ #
    #  Turn-end guards (report protocol)
    # ------------------------------------------------------------------ #

    _REPORT_GUARD_MAX_RETRIES = 2

    async def _run_guard_round(self, message: UserMessage, reminder: str) -> None:
        """Run one more LLM round after injecting a guard reminder.

        Reuses _build_messages + llm_provider.chat + _handle_tool_calls so the
        agent gets a real chance to call `report` (or resolve blocked tasks).
        """
        self._conversation_history.append(LLMMessage(role="user", content=reminder))
        try:
            messages = _trim_messages_to_budget(
                await self._build_messages(),
                context_window=getattr(self.config, "context_window", 128000),
                max_output=getattr(self.config, "max_tokens", 4096),
            )
            tool_defs = self.tools.get_definitions()
            response = await self.llm_provider.chat(
                messages=messages,
                tools=tool_defs or None,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
        except Exception as e:
            logger.error("Guard re-prompt failed for {}: {}", self.agent_type, e)
            return

        if getattr(response, "tool_calls", None):

            @dataclass
            class _GuardResponse:
                content: str
                tool_calls: list
                thinking: str | None = None

            await self._handle_tool_calls(
                _GuardResponse(
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                    thinking=getattr(response, "thinking", None),
                ),
                getattr(message, "message_id", None),
            )
        elif response.content:
            self._conversation_history.append(
                LLMMessage(role="assistant", content=response.content)
            )

    async def _enforce_report_guard(self, message: UserMessage) -> bool:
        """Sub-agents must call `report` before ending a Main-dispatched turn.

        Returns True if the guard took over (caller must NOT finalize IDLE).
        Re-prompts up to _REPORT_GUARD_MAX_RETRIES times; if the agent still
        has not reported, marks the task BLOCKED so Main learns it needs action.
        """
        if self.agent_type == AgentType.MAIN:
            return False
        if getattr(message, "source", None) != "main_agent":
            return False

        reminder = (
            "[系统提醒] 你结束本轮但还没有调用 report。必须在结束前调用 "
            "report(task_id, type, content)：type='reply' 表示完成，"
            "'missing_data'/'quality' 表示卡住。请现在调用 report。"
        )
        while not self._turn_reported:
            self._report_retries += 1
            if self._report_retries > self._REPORT_GUARD_MAX_RETRIES:
                # Exhausted — mark the active Main-dispatched task BLOCKED.
                await self._mark_active_task_blocked()
                await self._set_status(AgentStatus.IDLE)
                self._report_retries = 0
                return True
            await self.bus.publish(
                SystemNotice(
                    agent_type=self.agent_type,
                    content=f"[守卫] {self.agent_type.value} 结束本轮但未调用 report，"
                    f"提醒重试 ({self._report_retries}/{self._REPORT_GUARD_MAX_RETRIES})。",
                )
            )
            await self._run_guard_round(message, reminder)

        # The agent reported during a re-prompt round — finalize normally.
        await self._flush_manifest_if_needed()
        await self._set_status(AgentStatus.IDLE)
        return True

    async def _mark_active_task_blocked(self) -> None:
        """Mark the active Main->self task BLOCKED (auto-block fallback)."""
        if self._task_board is None:
            return
        todos = self._task_board.get_todolist(self.agent_type, session_id=self._current_session_id)
        task = next((t for t in todos if t.source_agent == AgentType.MAIN), None)
        if task is None:
            return
        try:
            self._task_board.block_task(
                task.task_id, target_agent=self.agent_type, session_id=self._current_session_id
            )
        except ValueError:
            return
        await self.bus.publish(
            SystemNotice(
                agent_type=self.agent_type,
                content=f"[守卫] {self.agent_type.value} 多次未 report，"
                f"任务 {task.task_id} 标记为 blocked，交回 Main 处理。",
            )
        )

    async def _enforce_main_blocked_guard(self, message: UserMessage) -> bool:
        """Main may not go IDLE while it has BLOCKED tasks.

        Returns True if the guard took over. Re-prompts up to
        _REPORT_GUARD_MAX_RETRIES times; after that, allows IDLE and surfaces
        the unresolved blocks to the user via a SystemNotice.
        """
        if self.agent_type != AgentType.MAIN or self._task_board is None:
            return False

        reminder = (
            "[系统提醒] 你还有被阻塞的任务未处理。请用 send_to_agent 重派、"
            "转交其他 agent，或自行补齐所需输入后再结束。"
        )
        while True:
            blocked = self._task_board.get_blocked_waitlist(
                AgentType.MAIN, session_id=self._current_session_id
            )
            if not blocked:
                self._main_block_retries = 0
                return False
            self._main_block_retries += 1
            names = ", ".join(f"{t.target_agent.value}:{t.brief}" for t in blocked)
            if self._main_block_retries > self._REPORT_GUARD_MAX_RETRIES:
                await self.bus.publish(
                    SystemNotice(
                        agent_type=AgentType.MAIN,
                        content=f"[守卫] Main 多次未解决被阻塞任务，暂停以便用户介入：{names}",
                    )
                )
                self._main_block_retries = 0
                return False  # allow IDLE so the user can act
            await self.bus.publish(
                SystemNotice(
                    agent_type=AgentType.MAIN,
                    content=f"[守卫] Main 还有被阻塞的任务：{names}，"
                    f"请先解决 ({self._main_block_retries}/{self._REPORT_GUARD_MAX_RETRIES})。",
                )
            )
            await self._run_guard_round(message, reminder)

    def _queue_message_summary(self, message: UserMessage) -> str:
        content = str(message.content or "").strip()
        first_line = content.splitlines()[0].strip() if content else ""
        if message.source == "main_agent":
            return f"From Main: {first_line}" if first_line else "From Main"
        if message.source == "system":
            return first_line or "System update"
        if message.source and message.source != "user":
            sender = get_agent_badge(message.source)
            return f"From {sender}: {first_line}" if first_line else f"From {sender}"
        return first_line or "Queued message"

    async def _publish_queue_update(self) -> None:
        queued = list(self._message_queue._queue)
        summaries = [self._queue_message_summary(msg) for msg in queued]
        await self.bus.publish(
            QueueUpdateMessage(
                agent_type=self.agent_type,
                queued_messages=summaries,
            )
        )

    async def _process_message(self, message: UserMessage) -> None:
        """Process a user message.

        Creates a per-agent checkpoint before processing so the agent can
        roll back to the pre-message file state.

        Args:
            message: User message to process.
        """
        await self._set_status(AgentStatus.THINKING)

        # Reset per-turn state: this message's turn has not yet been reported.
        self._turn_reported = False
        self._report_retries = 0
        self._main_block_retries = 0
        # Reset cancel event for this message
        self._cancel_event.clear()

        # Create a pre-message checkpoint for this agent
        cp_id = None
        if self._loop_manager is not None:
            try:
                source = message.source if hasattr(message, "source") else "user"
                agent_str = self._get_agent_type_str()
                # Save conversation history to checkpoint
                history_dicts = [
                    msg.model_dump()
                    if hasattr(msg, "model_dump")
                    else {"role": msg.role, "content": msg.content}
                    for msg in self._conversation_history
                ]
                cp_id = await self._loop_manager.create_checkpoint(
                    agent_type=agent_str,
                    description=f"pre:{source}",
                    source="pre_message",
                    conversation_history=history_dicts,
                    message_id=message.message_id,
                )
                logger.debug("{} checkpoint created: {}", agent_str, cp_id)
            except Exception as e:
                logger.warning("Failed to create checkpoint for {}: {}", self.agent_type, e)

        try:
            # In debug mode, wrap message with context
            content = message.content
            if self._debug_mode:
                content = (
                    "[调试模式] 此 Agent 处于独立调试模式，不与其他 Agent 通信。\n"
                    "你可以直接测试此 Agent 的工具和输出。\n\n" + content
                )

            # Add user message to conversation history
            self._conversation_history.append(LLMMessage(role="user", content=content))

            # Build messages — system prompt always first, conversation history follows
            messages = await self._build_messages()

            # Auto-compact: trim if exceeds context budget
            messages = _trim_messages_to_budget(
                messages,
                context_window=getattr(self.config, "context_window", 128000),
                max_output=getattr(self.config, "max_tokens", 4096),
            )

            # Get tool definitions
            tool_definitions = self.tools.get_definitions()

            # Call LLM with streaming (default)
            start_time = time.time()

            accumulated_content = ""
            accumulated_tool_calls = []
            accumulated_thinking = None
            last_error = None

            try:
                async for chunk in self.llm_provider.chat_stream(
                    messages=messages,
                    tools=tool_definitions if tool_definitions else None,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                ):
                    if chunk.delta:
                        accumulated_content += chunk.delta
                        # Stream chunk to UI
                        await self.bus.publish(
                            AgentResponse(
                                agent_type=self.agent_type,
                                content=chunk.delta,
                                message_id=message.message_id,
                                streaming=True,
                            )
                        )

                    if chunk.tool_calls:
                        accumulated_tool_calls = chunk.tool_calls

                    if chunk.thinking:
                        accumulated_thinking = chunk.thinking
                        await self.bus.publish(
                            AgentResponse(
                                agent_type=self.agent_type,
                                content="",
                                message_id=message.message_id,
                                streaming=True,
                                thinking=chunk.thinking,
                            )
                        )

                    if chunk.done:
                        # Stream complete — only save to history if no tool calls.
                        # When tool calls exist, _handle_tool_calls manages history.
                        if accumulated_content and not accumulated_tool_calls:
                            self._conversation_history.append(
                                LLMMessage(role="assistant", content=accumulated_content)
                            )
                        break

                    if self._cancel_event.is_set():
                        logger.info("Stream cancelled for agent {}", self.agent_type)
                        break
            except Exception as e:
                last_error = str(e)
                raise

            finally:
                # Calculate duration and publish debug info
                duration_ms = int((time.time() - start_time) * 1000)

                # Token usage: streaming chunks (LLMStreamChunk) do not carry
                # usage, and the non-streaming LLMResponse.usage is not produced
                # on this path, so fall back to a length-based estimate
                # (~4 chars/token). Switch to real usage if a streaming usage
                # field is added to LLMStreamChunk.
                tokens_in = sum(len(m.content) // 4 for m in messages)
                tokens_out = len(accumulated_content) // 4

                await self.bus.publish(
                    ApiDebugMessage(
                        model=self.llm_provider.model or "unknown",
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        duration_ms=duration_ms,
                        status="cancelled"
                        if self._cancel_event.is_set()
                        else ("success" if last_error is None else "error"),
                        error=last_error,
                    )
                )

            # Handle cancellation — skip tool calls and send cancellation notice
            if self._cancel_event.is_set():
                if accumulated_content:
                    self._conversation_history.append(
                        LLMMessage(role="assistant", content=accumulated_content)
                    )
                await self.bus.publish(
                    AgentResponse(
                        agent_type=self.agent_type,
                        content="[已取消]",
                        message_id=message.message_id,
                        streaming=False,
                    )
                )
                await self._set_status(AgentStatus.IDLE)
                return

            # Handle tool calls if present
            if accumulated_tool_calls:

                @dataclass
                class StreamResponse:
                    content: str
                    tool_calls: list
                    thinking: str | None = None

                response = StreamResponse(
                    content=accumulated_content,
                    tool_calls=accumulated_tool_calls,
                    thinking=accumulated_thinking,
                )
                await self._handle_tool_calls(response, message.message_id)

            # Send final completion signal.
            # For tool-call paths, _handle_tool_calls already published the
            # final content — this is just a completion marker.
            # For no-tool paths, include the accumulated content so that
            # SendToAgentTool (and any other bus listener) receives the
            # full response text on the non-streaming message.
            final_content = "" if accumulated_tool_calls else accumulated_content
            await self.bus.publish(
                AgentResponse(
                    agent_type=self.agent_type,
                    content=final_content,
                    message_id=message.message_id,
                    streaming=False,
                )
            )

            await self._flush_manifest_if_needed()

            # Turn-end guards (report protocol). Each guard may re-prompt the
            # agent instead of going IDLE; if a guard takes over, it owns the
            # final status transition and we return without double-finalizing.
            if await self._enforce_report_guard(message):
                return
            if await self._enforce_main_blocked_guard(message):
                return

            await self._set_status(AgentStatus.IDLE)

        except Exception as e:
            logger.error("Error processing message in {}: {}", self.agent_type, str(e))
            self._consecutive_errors += 1

            if self._consecutive_errors >= 3:
                logger.warning(
                    "{}: 3 consecutive errors — skipping current message", self.agent_type
                )

            await self._flush_manifest_if_needed()
            await self._set_status(AgentStatus.ERROR)
            await self.bus.publish(
                Error(
                    source=str(self.agent_type),
                    message=str(e),
                )
            )

        else:
            self._consecutive_errors = 0

    async def _flush_manifest_if_needed(self) -> None:
        """Wrap up manifest at end of loop: prompt agent to update free-text notes.

        Only fires when file tools were used during this turn.  Injects a
        lightweight system instruction so the agent can decide whether the
        notes section needs updating — no extra LLM round required; the
        hint is prepended to the next turn's system prompt.
        """
        if self.agent_type == AgentType.MAIN or self._manifest_manager is None:
            self._manifest_dirty = False
            return

        if not self._manifest_dirty:
            return

        self._manifest_dirty = False

        # Inject a brief wrap-up prompt so the agent reviews the manifest
        # notes *at the start of the next turn*.  That avoids an extra LLM
        # call while still giving the agent a chance to update the free-text
        # section when it next processes a message.
        try:
            manifest = await self._manifest_manager.load(self._get_agent_type_str())
            files = manifest.get("files", [])
            notes = manifest.get("notes", "")
            # Only poke the agent when there are un-described files or the
            # notes area is empty after file changes.
            undescribed = [f for f in files if not f.get("description", "").strip()]
            if undescribed or not notes.strip():
                hint = (
                    "\n\n[Manifest 收尾提示]\n本轮的创建/修改/删除文件已自动更新到你的 manifest。"
                )
                if undescribed:
                    hint += "以下文件尚无描述，请在方便时通过 manifest 工具补全：\n" + "\n".join(
                        f"  - {f['path']}" for f in undescribed
                    )
                if not notes.strip():
                    hint += (
                        "\n自由文本区（notes）当前为空，请在方便时补充文件之间的关系、"
                        "依赖或协作说明。"
                    )
                else:
                    hint += "\n自由文本区（notes）可能需要补充。请查看并根据需要更新。"
                self._conversation_history.append(LLMMessage(role="user", content=hint))
        except Exception as e:
            logger.warning("Failed to flush manifest for {}: {}", self.agent_type, e)

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

        current_messages = await self._build_messages()

        while response.tool_calls and iteration < max_iterations:
            iteration += 1
            logger.debug(
                "Tool iteration {} for agent: {}, tool_calls: {}",
                iteration,
                self.agent_type,
                len(response.tool_calls),
            )

            # Add assistant message with tool calls as structured data
            current_messages.append(
                LLMMessage(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                    thinking=response.thinking,
                )
            )

            # Execute each tool call and add results as structured messages
            for tool_call in response.tool_calls:
                await self._set_status(AgentStatus.RUNNING_TOOL)

                await self.bus.publish(
                    ToolCallMessage(
                        agent_type=self.agent_type,
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                    )
                )

                try:
                    tool = self.tools.get(tool_call.name)
                    if tool is None:
                        raise ValueError(f"Tool not found: {tool_call.name}")

                    # Detect truncated tool calls: output hit max_tokens before arguments were complete
                    if not tool_call.arguments:
                        usage = response.usage or {}
                        output_tokens = usage.get("output_tokens", 0)
                        if output_tokens >= 8192:
                            raise ValueError(
                                f"Tool call to '{tool_call.name}' has no arguments — "
                                f"the response was truncated at {output_tokens} output tokens. "
                                f"Your output is too long. Break the file into smaller parts "
                                f"and write them one at a time using write_file, or use a shorter response."
                            )
                        else:
                            raise ValueError(
                                f"Tool call to '{tool_call.name}' has no arguments. "
                                f"Please provide the required parameters."
                            )

                    result = await tool(**tool_call.arguments)

                    if tool_call.name in ("apply_patch", "delete_file"):
                        self._manifest_dirty = True

                    await self.bus.publish(
                        ToolResultMsg(
                            agent_type=self.agent_type,
                            tool_name=tool_call.name,
                            result=result,
                        )
                    )

                    result_str = self._format_tool_result(result)

                except Exception as e:
                    logger.error(
                        "Tool execution error for {}: {} | args={}",
                        tool_call.name,
                        str(e),
                        tool_call.arguments,
                    )
                    error_msg = f"Error executing {tool_call.name}: {str(e)}"

                    await self.bus.publish(
                        ToolResultMsg(
                            agent_type=self.agent_type,
                            tool_name=tool_call.name,
                            result=None,
                            error=error_msg,
                        )
                    )
                    result_str = error_msg

                # Add tool result as structured message
                # Anthropic API doesn't support 'tool' role, use 'user' instead
                provider_class_name = self.llm_provider.__class__.__name__
                tool_result_role = "user" if provider_class_name == "AnthropicProvider" else "tool"

                current_messages.append(
                    LLMMessage(
                        role=tool_result_role,
                        content=result_str,
                        tool_call_id=tool_call.id,
                        is_tool_result=True,
                    )
                )

            # Call LLM again with updated conversation
            await self._set_status(AgentStatus.THINKING)

            tool_definitions = self.tools.get_definitions()

            # Time the API call
            start_time = time.time()
            last_error = None

            try:
                response = await self.llm_provider.chat(
                    messages=current_messages,
                    tools=tool_definitions,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
            except Exception as e:
                last_error = str(e)
                raise
            finally:
                # Calculate duration and publish debug info
                duration_ms = int((time.time() - start_time) * 1000)

                # Estimate token usage
                tokens_in = sum(len(m.content) // 4 for m in current_messages)
                tokens_out = len(response.content) // 4 if response.content else 0

                await self.bus.publish(
                    ApiDebugMessage(
                        model=self.llm_provider.model or "unknown",
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        duration_ms=duration_ms,
                        status="success" if last_error is None else "error",
                        error=last_error,
                    )
                )

            # This round is non-streaming, so thinking arrives as one block.
            # Publish it so the thinking indicator fills between tool calls —
            # without this the dots row is empty and gets removed on finish.
            if getattr(response, "thinking", None):
                await self.bus.publish(
                    AgentResponse(
                        agent_type=self.agent_type,
                        content="",
                        message_id=user_message_id,
                        streaming=True,
                        thinking=response.thinking,
                    )
                )

        # Update conversation history with final response
        if response.content:
            current_messages.append(LLMMessage(role="assistant", content=response.content))
            # Publish final content to GUI (it was generated inside the tool loop)
            await self.bus.publish(
                AgentResponse(
                    agent_type=self.agent_type,
                    content=response.content,
                    message_id=user_message_id,
                    streaming=False,
                )
            )

        # Save conversation history — strip the system prompt (index 0)
        self._conversation_history = [m for m in current_messages if m.role != "system"]

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
            filtered = {
                key: value
                for key, value in result.items()
                if not str(key).startswith("_ui_") and str(key) != "completion_summary"
            }
            return str(filtered)
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

        await self.bus.publish(
            StatusChange(
                agent_type=self.agent_type,
                status=display_status,
            )
        )

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

        await self.bus.publish(
            UserMessage(
                content=content,
                agent_type=agent_type,
                message_id=message_id,
                source="main_agent",
            )
        )
        logger.info("Main agent sent coordination message to {}", agent_type)

    async def _get_cached_system_prompt(self) -> str:
        """Return the cached system prompt, rebuilding it when sources change.

        The prompt is assembled from the agent template, shared context
        (Common.md), and — for the Report agent only — an on-demand skills
        summary. The assembled text is cached, but the cache is invalidated
        automatically when the underlying prompt files change.
        """
        agent_type_str = self._get_agent_type_str()
        logger.debug("Loading system prompt for agent: {}", self.agent_type)
        prompt_signature = self._prompt_loader.get_signature(agent_type_str)
        skills_summary = None
        if self.agent_type == AgentType.REPORT and self._skill_loader:
            skills_summary = self._skill_loader.build_skills_summary()
        current_signature = (
            agent_type_str,
            prompt_signature,
            skills_summary,
            bool(self._manifest_manager and self.agent_type != AgentType.MAIN),
        )

        if (
            self._cached_system_prompt is not None
            and self._cached_system_prompt_signature == current_signature
        ):
            return self._cached_system_prompt

        parts: list[str] = [self._prompt_loader.load_prompt(agent_type_str)]

        shared = self._prompt_loader.load_shared_context()
        if shared:
            parts.append(shared)

        # Skills summary — Report agent only (others don't need skill guidance)
        if skills_summary:
            parts.append(
                "\n## Available Skills\n\n"
                "The following skills are available. Use `load_skill` tool to get "
                "full content when needed:\n\n" + skills_summary
            )
            logger.debug("Injected skills summary for report agent")

        # Manifest hint — sub-agents only
        if self._manifest_manager and self.agent_type != AgentType.MAIN:
            parts.append(
                "\n\n[Manifest]\n"
                "你可以在需要时使用 manifest 了解当前本地提供了哪些文件。"
                "文件描述应简短，更复杂的关系、依赖、协作说明写在自由文本区。"
                "只有在本轮结束前，才重点补充 manifest 的自由文本区。"
            )

        self._cached_system_prompt = "\n\n".join(parts)
        self._cached_system_prompt_signature = current_signature
        return self._cached_system_prompt

    async def _get_system_prompt(self) -> str:
        """Return the system prompt with live task state appended.

        The base prompt is cached once; the task-state section is rebuilt
        fresh each time so it reflects the current board state.
        """
        base = await self._get_cached_system_prompt()
        task_section = self._build_task_state_section()
        if task_section:
            return base + task_section
        return base

    async def _build_messages(self) -> list[LLMMessage]:
        """Build the message list for any LLM request.

        System prompt is always first (with cache_control for Anthropic caching),
        followed by the recorded conversation history.  This single entry-point
        is used by both the initial streaming call *and* tool-call iterations, so
        the system prompt is never accidentally dropped.
        """
        sanitized_history = [
            LLMMessage(
                role=msg.role,
                content=msg.content or "",
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                is_tool_result=msg.is_tool_result,
                thinking=msg.thinking,
                cache_control=msg.cache_control,
            )
            for msg in self._conversation_history
        ]
        return [
            LLMMessage(role="system", content=await self._get_system_prompt(), cache_control=True),
            *sanitized_history,
        ]

    def _build_task_state_section(self) -> str:
        """Build current task state section for the system prompt.

        Rules:
        - Incomplete tasks: show all
        - Completed tasks: show only 10 most recently completed (by completed_at)
        """
        if self._loop_manager is None:
            return ""
        task_board = getattr(self._loop_manager, "_task_board", None)
        if task_board is None:
            return ""

        todolist = task_board.get_todolist(self.agent_type, session_id=self._current_session_id)
        waitlist = task_board.get_waitlist(self.agent_type, session_id=self._current_session_id)

        if not todolist and not waitlist:
            return ""

        lines = ["\n[当前任务]"]

        # Helper to format task list
        def format_task_list(tasks, is_waitlist: bool = False) -> list[str]:
            if not tasks:
                return []

            # Separate incomplete and completed
            incomplete = [t for t in tasks if t.status != TaskStatus.COMPLETED]
            completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]

            result = []

            # Show all incomplete tasks first
            for t in incomplete:
                if is_waitlist:
                    tgt = (
                        t.target_agent.value
                        if hasattr(t.target_agent, "value")
                        else str(t.target_agent)
                    )
                    result.append(f"  - 等待{tgt} {t.brief}")
                else:
                    status_map = {
                        TaskStatus.PENDING: "待处理",
                        TaskStatus.IN_PROGRESS: "进行中",
                        TaskStatus.FAILED: "失败",
                        TaskStatus.CANCELLED: "已取消",
                    }
                    s = status_map.get(t.status, t.status.value)
                    result.append(f"  - {s} {t.brief}")

            # Show 10 most recently completed tasks
            if completed:
                # Sort by completed_at descending (most recent first)
                completed_sorted = sorted(
                    completed, key=lambda t: t.completed_at or datetime.min, reverse=True
                )[:10]

                for t in completed_sorted:
                    if is_waitlist:
                        tgt = (
                            t.target_agent.value
                            if hasattr(t.target_agent, "value")
                            else str(t.target_agent)
                        )
                        result.append(f"  - 等待{tgt} {t.brief} (已完成)")
                    else:
                        result.append(f"  - 已完成 {t.brief}")

            return result

        if todolist:
            lines.append("待办:")
            lines.extend(format_task_list(todolist, is_waitlist=False))

        if waitlist:
            lines.append("等待:")
            lines.extend(format_task_list(waitlist, is_waitlist=True))

        return "\n".join(lines)

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
