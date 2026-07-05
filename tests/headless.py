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
import importlib.util
import os
from pathlib import Path

from loguru import logger
import pytest

from autoreport.config import ConfigManager
from autoreport.core.loops import LoopManager, MessageBus
from autoreport.core.project_structure import ensure_project_structure
from autoreport.core.providers.factory import ProviderFactory
from autoreport.interfaces.types import (
    AgentResponse,
    AgentType,
    Error,
    Message,
    StatusChange,
    ToolCallMessage,
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
            ToolCallMessage,
            ToolResult,
            StatusChange,
            Error,
            UserMessage,
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
    def tool_calls(self) -> list[ToolCallMessage]:
        return [m for m in self._messages if isinstance(m, ToolCallMessage)]

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

    async def wait_for_idle(
        self,
        agent_type: AgentType | str = AgentType.MAIN,
        timeout: float = 120.0,
    ) -> None:
        """Wait until ``agent_type`` returns to IDLE status.

        The first ``AgentResponse`` is usually a streaming chunk that arrives
        before the final non-streaming content. Waiting for IDLE guarantees the
        agent loop has finished processing and the final content has been
        published, so ``get_full_agent_text`` returns the complete text.
        """
        at = agent_type if isinstance(agent_type, AgentType) else AgentType(agent_type)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            # Scan status changes from most recent backwards for this agent.
            statuses = [
                s.status for s in self.status_changes if s.agent_type == at
            ]
            if statuses and statuses[-1] == "idle":
                return
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"{at.value} did not return to idle within {timeout}s. "
                    f"Last statuses: {statuses[-5:]}. "
                    f"Messages: {[type(m).__name__ for m in self._messages]}"
                )
            await asyncio.sleep(0.2)

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
        self._bus_task: asyncio.Task | None = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()

    async def start(self) -> None:
        """Start the backend: bus, providers, agent loops."""
        if self._started:
            return

        self._require_usable_provider()
        self._ensure_project_structure()

        self._loop_manager = LoopManager(
            workspace=self.workspace,
            config_manager=self.config_manager,
            bus=self.bus,
        )

        # Start all agent loops
        await self._loop_manager.start()
        self._bus_task = asyncio.create_task(self.bus.process_queue())

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

        if self._bus_task is not None:
            self._bus_task.cancel()
            await asyncio.gather(self._bus_task, return_exceptions=True)
            self._bus_task = None

        await asyncio.sleep(0.3)

        # Cancel remaining tasks
        loop = asyncio.get_event_loop()
        for task in asyncio.all_tasks(loop):
            if task is not asyncio.current_task():
                task.cancel()

        self._started = False
        logger.info("HeadlessBackend stopped")

    def _require_usable_provider(self) -> None:
        """Skip integration tests when no configured provider can be constructed."""
        config = self.config_manager.config
        candidates = [
            cfg for cfg in config.providers.configurations
            if cfg.enabled and cfg.api_key
        ]
        socks_issue = self._socks_proxy_issue()
        if candidates and socks_issue:
            pytest.skip(
                "No usable LLM provider for integration tests: "
                f"{socks_issue}"
            )

        errors: list[str] = []

        for cfg in candidates:
            try:
                ProviderFactory.create_provider(
                    cfg.provider,
                    cfg.api_key,
                    cfg.api_base,
                    cfg.default_model,
                )
            except Exception as exc:
                errors.append(f"{cfg.name} ({cfg.provider}): {exc}")
                continue
            return

        if errors:
            detail = "; ".join(errors)
            pytest.skip(f"No usable LLM provider for integration tests: {detail}")

        pytest.skip(
            "No usable LLM provider for integration tests: "
            "configure at least one enabled provider with a working API key."
        )

    def _socks_proxy_issue(self) -> str | None:
        """Return a skip reason when SOCKS proxy support is missing."""
        proxies = [
            os.getenv("ALL_PROXY"),
            os.getenv("all_proxy"),
            os.getenv("HTTP_PROXY"),
            os.getenv("http_proxy"),
            os.getenv("HTTPS_PROXY"),
            os.getenv("https_proxy"),
        ]
        if not any(p and p.lower().startswith("socks") for p in proxies):
            return None
        if importlib.util.find_spec("socksio") is not None:
            return None
        return (
            "SOCKS proxy is configured but `socksio` is not installed. "
            "Install `httpx[socks]` or disable the SOCKS proxy for integration tests."
        )

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
        ensure_project_structure(self.workspace)
