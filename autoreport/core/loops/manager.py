"""Loop manager for managing agent lifecycles."""

import asyncio
from pathlib import Path

from loguru import logger

from ...config import ConfigManager
from ...core.providers import ProviderFactory, ProviderManager
from ...interfaces.types import AgentType, Message, RestartRequest
from ..checkpoints import CheckpointManager
from ..skills import SkillLoader
from ..tools import (
    EditFileTool,
    ExecTool,
    ListDirTool,
    PDFParseTool,
    PythonExecTool,
    ReadFileTool,
    ReportIssueTool,
    SendToAgentTool,
    WriteFileTool,
)
from ..tools.registry import ToolRegistry
from .agent_loop import AgentLoop
from .bus import MessageBus


class LoopManager:
    """Manager for all agent loops."""

    def __init__(
        self,
        workspace: Path,
        config_manager: ConfigManager,
        bus: MessageBus,
    ):
        """Initialize loop manager.

        Args:
            workspace: Project workspace directory.
            config_manager: Configuration manager.
            bus: Message bus for communication.
        """
        self.workspace = Path(workspace).resolve()
        self.config_manager = config_manager
        self.bus = bus

        self._loops: dict[AgentType, AgentLoop] = {}
        self._running = False
        self._provider_manager = ProviderManager()
        self.checkpoint_manager = CheckpointManager(self.workspace)
        self.skill_loader = SkillLoader()

        # Subscribe to restart requests
        self.bus.subscribe(RestartRequest, self._handle_restart_request)

    @property
    def is_running(self) -> bool:
        """Check if any loops are running."""
        return self._running and len(self._loops) > 0

    async def start(self) -> None:
        """Start all agent loops."""
        if self._running:
            logger.warning("Loop manager already running")
            return

        self._running = True
        logger.info("Starting loop manager for workspace: {}", self.workspace)

        # Initialize providers
        await self._initialize_providers()

        # Create loops
        await self._create_loops()

        for agent_type, loop in self._loops.items():
            await loop.start()
            logger.info("Started loop for agent: {}", agent_type)

    async def _initialize_providers(self) -> None:
        """Initialize LLM providers from configuration."""
        config = self.config_manager.config

        for cfg in config.providers.configurations:
            if not cfg.enabled or not cfg.api_key:
                continue

            try:
                provider = ProviderFactory.create_provider(
                    cfg.provider,
                    cfg.api_key,
                    cfg.api_base,
                    cfg.default_model,
                )
                self._provider_manager.register_provider(cfg.id, provider)
                logger.info("Initialized {} provider: {}", cfg.provider, cfg.name)
            except Exception as e:
                logger.warning(
                    "Failed to initialize provider {} ({}): {}",
                    cfg.name, cfg.provider, e,
                )

        # Set active provider
        available = self._provider_manager.get_available_providers()
        if not available:
            logger.warning("No LLM providers initialized")
            return

        active_id = config.providers.active
        if active_id and self._provider_manager.has_provider(active_id):
            self._provider_manager.set_active_provider(active_id)
        else:
            self._provider_manager.set_active_provider(available[0])

        logger.info("Active provider: {}", self._provider_manager._active_key)

    async def stop(self) -> None:
        """Stop all agent loops."""
        if not self._running:
            return

        logger.info("Stopping loop manager")

        for agent_type, loop in self._loops.items():
            await loop.stop()
            logger.info("Stopped loop for agent: {}", agent_type)

        self._loops.clear()
        self._running = False

    async def restart(self, reason: str = "user_request") -> None:
        """Restart all agent loops.

        Args:
            reason: Reason for restart.
        """
        logger.info("Restarting loop manager (reason: {})", reason)

        await self.stop()
        # Small delay to ensure cleanup
        await asyncio.sleep(0.5)
        await self.start()

    async def _create_loops(self) -> None:
        """Create agent loops for all agent types."""
        config = self.config_manager.config.agents.defaults
        llm_provider = self._provider_manager.get_active_provider()

        # Create tools for each agent type
        for agent_type in AgentType:
            tools = self._create_tools_for_agent(agent_type)

            loop = AgentLoop(
                agent_type=agent_type,
                workspace=self.workspace,
                tools=tools,
                bus=self.bus,
                config=config,
                llm_provider=llm_provider,
                loop_manager=self,
                skill_loader=self.skill_loader,
            )
            self._loops[agent_type] = loop

    def get_loop(self, agent_type: AgentType) -> "AgentLoop | None":
        """Get agent loop by type.

        Args:
            agent_type: Agent type to retrieve.

        Returns:
            AgentLoop instance or None if not found.
        """
        return self._loops.get(agent_type)

    def _create_tools_for_agent(self, agent_type: AgentType) -> ToolRegistry:
        """Create tool registry for an agent type.

        Args:
            agent_type: Type of agent.

        Returns:
            Tool registry with appropriate tools.
        """
        registry = ToolRegistry()

        # Common tools for all agents
        registry.register(ReadFileTool(workspace=self.workspace))
        registry.register(ListDirTool(workspace=self.workspace))

        # Determine write allowed directory based on agent type
        write_dirs = {
            AgentType.DATA_ANALYSIS: self.workspace / "data" / "processed",
            AgentType.PLOTTING: self.workspace / "code",
            AgentType.THEORY: self.workspace / "theory",
            AgentType.REPORT: self.workspace / "tex",
            AgentType.MAIN: self.workspace,  # Main agent has full access
        }

        write_dir = write_dirs.get(agent_type, self.workspace)

        # Register write tools
        registry.register(WriteFileTool(
            workspace=self.workspace,
            write_allowed_dir=write_dir,
        ))
        registry.register(EditFileTool(
            workspace=self.workspace,
            write_allowed_dir=write_dir,
        ))

        # Execution tools (for data analysis, plotting, and main agent)
        if agent_type in (AgentType.DATA_ANALYSIS, AgentType.PLOTTING, AgentType.MAIN):
            registry.register(ExecTool(
                working_dir=self.workspace,
                timeout=120,
            ))
            registry.register(PythonExecTool(
                working_dir=self.workspace,
                timeout=60,
            ))

        # PDF parsing (all agents that may need to read reference materials)
        if agent_type in (
            AgentType.MAIN,
            AgentType.THEORY,
            AgentType.DATA_ANALYSIS,
            AgentType.REPORT,
        ):
            mineru_timeout = (
                self.config_manager.config.mineru_api.timeout
                if hasattr(self.config_manager.config, "mineru_api")
                else 300
            )
            registry.register(PDFParseTool(
                workspace=self.workspace,
                timeout=mineru_timeout,
            ))

        # Inter-agent communication tools
        if agent_type == AgentType.MAIN:
            registry.register(SendToAgentTool(bus=self.bus))
        else:
            registry.register(ReportIssueTool(bus=self.bus, agent_type=agent_type))

        return registry

    async def create_checkpoint(self, description: str) -> str:
        """Create a checkpoint.

        Args:
            description: Description of the checkpoint.

        Returns:
            Checkpoint ID.
        """
        checkpoint_id = await self.checkpoint_manager.create_checkpoint(description)

        # Notify GUI about new checkpoint
        checkpoint = self.checkpoint_manager.get_checkpoint(checkpoint_id)
        if checkpoint:
            from ...interfaces.types import Checkpoint as CheckpointMsg
            msg = CheckpointMsg(
                checkpoint_id=checkpoint_id,
                description=description,
                file_states={path: state.hash for path, state in checkpoint.file_states.items()},
            )
            await self.bus.publish(msg)

        return checkpoint_id

    async def rollback_to_checkpoint(self, checkpoint_id: str) -> None:
        """Rollback to a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID to rollback to.
        """
        await self.checkpoint_manager.rollback_to_checkpoint(checkpoint_id)

        # Create a new checkpoint after rollback
        await self.create_checkpoint(f"After rollback to {checkpoint_id[:8]}")

    async def _handle_restart_request(self, message: Message) -> None:
        """Handle restart request from GUI.

        Args:
            message: Restart request message.
        """
        if not isinstance(message, RestartRequest):
            return

        await self.restart(reason=message.reason)

    def set_agent_debug_mode(self, agent_type: str, enabled: bool) -> None:
        """Enable or disable debug mode for an agent.

        Args:
            agent_type: Agent type (data_analysis, plotting, theory, report).
            enabled: Whether debug mode is enabled.
        """
        # Convert string to AgentType
        agent_enum = AgentType(agent_type)

        if agent_enum in self._loops:
            self._loops[agent_enum].set_debug_mode(enabled)
            logger.info(
                "Debug mode {} for agent: {}",
                "enabled" if enabled else "disabled",
                agent_type,
            )

    def get_agent_debug_mode(self, agent_type: str) -> bool:
        """Check if debug mode is enabled for an agent.

        Args:
            agent_type: Agent type.

        Returns:
            True if debug mode is enabled.
        """
        agent_enum = AgentType(agent_type)

        if agent_enum in self._loops:
            return self._loops[agent_enum].debug_mode

        return False

    def get_agent_status(self, agent_type: str) -> str | None:
        """Query current status of an agent.

        Args:
            agent_type: Agent type string (e.g. "data_analysis").

        Returns:
            Agent status string ("idle", "thinking", "running_tool", "error",
            "debug_mode"), or None if agent not found.
        """
        agent_enum = AgentType(agent_type)

        if agent_enum in self._loops:
            return self._loops[agent_enum].status.value

        return None

    def get_all_agent_statuses(self) -> dict[str, str]:
        """Query status of all agents.

        Returns:
            Dict mapping agent type string to status string.
        """
        return {
            agent_type.value: loop.status.value
            for agent_type, loop in self._loops.items()
        }
