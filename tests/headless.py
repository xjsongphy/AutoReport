"""Headless test harness — runs agent backend without Qt/GUI.

Provides:
- HeadlessBackend: starts LoopManager + MessageBus without any GUI
- MessageCollector: subscribes to bus and collects all messages for assertions
- Helper fixtures for pytest integration

Usage in tests::

    from tests.headless import HeadlessBackend, MessageCollector

    async def test_something():
        async with HeadlessBackend(workspace) as backend:
            collector = MessageCollector(backend.bus)
            await backend.send("main", "Hello agent")
            await collector.wait_for(AgentResponse, timeout=30)
            assert collector.agent_responses
"""

import asyncio
from pathlib import Path

from loguru import logger

from autoreport.config import ConfigManager
from autoreport.core.loops import LoopManager, MessageBus
from autoreport.interfaces.types import (
    AgentFeedback,
    AgentResponse,
    AgentType,
    Error,
    Message,
    StatusChange,
    ToolCall,
    ToolResult,
    UserMessage,
)


class MessageCollector:
    """Subscribe to MessageBus and collect messages for test assertions."""

    def __init__(self, bus: MessageBus):
        self._bus = bus
        self._messages: list[Message] = []
        self._events: dict[type, list[asyncio.Event]] = {}
        self._subscribed = False

    def start(self) -> None:
        """Subscribe to all message types."""
        if self._subscribed:
            return
        for msg_type in (
            AgentResponse,
            ToolCall,
            ToolResult,
            StatusChange,
            Error,
            UserMessage,
            AgentFeedback,
        ):
            self._bus.subscribe(msg_type, self._on_message)
        self._subscribed = True

    async def _on_message(self, msg: Message) -> None:
        self._messages.append(msg)
        # Notify any waiters
        for event in self._events.get(type(msg), []):
            event.set()

    async def wait_for(
        self,
        msg_type: type,
        timeout: float = 30.0,
        count: int = 1,
    ) -> list[Message]:
        """Wait until `count` messages of `msg_type` have been collected.

        Args:
            msg_type: Message subclass to wait for.
            timeout: Max seconds to wait.
            count: How many messages to wait for.

        Returns:
            List of collected messages of the requested type.

        Raises:
            TimeoutError: If not enough messages arrive in time.
        """
        event = asyncio.Event()
        self._events.setdefault(msg_type, []).append(event)

        existing = [m for m in self._messages if isinstance(m, msg_type)]
        if len(existing) >= count:
            return existing[:count]

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            collected = [m for m in self._messages if isinstance(m, msg_type)]
            raise TimeoutError(
                f"Timed out waiting for {count} {msg_type.__name__}(s). "
                f"Got {len(collected)} after {timeout}s. "
                f"All messages: {[type(m).__name__ for m in self._messages]}"
            ) from None

        return [m for m in self._messages if isinstance(m, msg_type)][:count]

    @property
    def all_messages(self) -> list[Message]:
        return list(self._messages)

    @property
    def agent_responses(self) -> list[AgentResponse]:
        return [m for m in self._messages if isinstance(m, AgentResponse)]

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [m for m in self._messages if isinstance(m, ToolCall)]

    @property
    def tool_results(self) -> list[ToolResult]:
        return [m for m in self._messages if isinstance(m, ToolResult)]

    @property
    def errors(self) -> list[Error]:
        return [m for m in self._messages if isinstance(m, Error)]

    @property
    def status_changes(self) -> list[StatusChange]:
        return [m for m in self._messages if isinstance(m, StatusChange)]

    def get_full_agent_text(self, agent_type: AgentType | str = AgentType.MAIN) -> str:
        """Concatenate all non-streaming agent responses for a given agent."""
        at = agent_type if isinstance(agent_type, AgentType) else AgentType(agent_type)
        parts = []
        for m in self.agent_responses:
            if m.agent_type == at:
                parts.append(m.content)
        return "".join(parts)

    def clear(self) -> None:
        self._messages.clear()


class HeadlessBackend:
    """Run the full agent backend without Qt/GUI.

    Usage::

        async with HeadlessBackend(workspace_path) as backend:
            collector = MessageCollector(backend.bus)
            await backend.send("main", "Hello")
            await collector.wait_for(AgentResponse, timeout=30)
    """

    def __init__(
        self,
        workspace: Path,
        config_path: Path | None = None,
        debug_agents: list[str] | None = None,
    ):
        self.workspace = Path(workspace).resolve()
        self.config_manager = ConfigManager(config_path)
        self.bus = MessageBus()
        self._loop_manager: LoopManager | None = None
        self._debug_agents = debug_agents or []
        self._started = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()

    async def start(self) -> None:
        """Start the backend: bus, providers, agent loops."""
        if self._started:
            return

        self._ensure_project_structure()

        self._loop_manager = LoopManager(
            workspace=self.workspace,
            config_manager=self.config_manager,
            bus=self.bus,
        )

        # Start message bus processing
        asyncio.create_task(self.bus.process_queue())

        # Start all agent loops
        await self._loop_manager.start()

        # Activate debug mode for specified agents
        for agent in self._debug_agents:
            self._loop_manager.set_agent_debug_mode(agent, True)
            logger.info("Debug mode activated for {}", agent)

        self._started = True
        logger.info("HeadlessBackend started for workspace: {}", self.workspace)

    async def stop(self) -> None:
        """Stop the backend gracefully."""
        if not self._started:
            return

        self.bus.shutdown()

        if self._loop_manager:
            await self._loop_manager.stop()

        await asyncio.sleep(0.3)

        # Cancel remaining tasks
        loop = asyncio.get_event_loop()
        for task in asyncio.all_tasks(loop):
            if task is not asyncio.current_task():
                task.cancel()

        self._started = False
        logger.info("HeadlessBackend stopped")

    async def send(
        self,
        agent_type: str,
        content: str,
        source: str = "user",
    ) -> None:
        """Send a user message to an agent.

        Args:
            agent_type: "main", "data_analysis", "plotting", "theory", "report"
            content: Message text
            source: "user" or "main_agent"
        """
        agent_type_map = {
            "main": AgentType.MAIN,
            "data_analysis": AgentType.DATA_ANALYSIS,
            "plotting": AgentType.PLOTTING,
            "theory": AgentType.THEORY,
            "report": AgentType.REPORT,
        }
        at = agent_type_map.get(agent_type, AgentType.MAIN)

        await self.bus.publish(UserMessage(
            content=content,
            agent_type=at,
            source=source,
        ))

    @property
    def loop_manager(self) -> LoopManager:
        assert self._loop_manager is not None, "Backend not started"
        return self._loop_manager

    def _ensure_project_structure(self) -> None:
        """Create project directories if they don't exist."""
        for d in [
            self.workspace / "data",
            self.workspace / "data" / "processed",
            self.workspace / "references",
            self.workspace / "theory",
            self.workspace / "code",
            self.workspace / "tex",
        ]:
            d.mkdir(parents=True, exist_ok=True)
