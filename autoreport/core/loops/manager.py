"""Loop manager for managing agent lifecycles."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from ...config import ConfigManager
from ...core.providers import ProviderFactory, ProviderManager
from ...interfaces.types import AgentType, FileRollbackRequest, Message, RestartRequest, RollbackStatus
from ..checkpoints import CheckpointManager
from ..tools import SkillLoader
from ..tools import (
    ApplyPatchTool,
    DeleteFileTool,
    ExecTool,
    FileStateManager,
    LoadSkillTool,
    ManageTasksTool,
    ManifestManager,
    PDFParseTool,
    ReadTool,
    ReportTool,
    SendToAgentTool,
    SkillLoader,
    TaskBoard,
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
        self._task_board = TaskBoard()
        self.manifest_manager = ManifestManager(self.workspace)
        self._file_state_managers: dict[AgentType, FileStateManager] = {}

        # Subscribe to restart requests and file rollback requests
        self.bus.subscribe(RestartRequest, self._handle_restart_request)
        self.bus.subscribe(FileRollbackRequest, self._handle_file_rollback_request)

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

    def cancel_current_operation(self, agent_type: str) -> None:
        """Cancel the currently processing message for an agent.

        Args:
            agent_type: Agent type string (e.g. "main", "data_analysis").
        """
        from autoreport.interfaces.types import AgentType

        agent_map = {
            "main": AgentType.MAIN,
            "data_analysis": AgentType.DATA_ANALYSIS,
            "plotting": AgentType.PLOTTING,
            "theory": AgentType.THEORY,
            "report": AgentType.REPORT,
        }
        agent_enum = agent_map.get(agent_type)
        if agent_enum is None:
            logger.warning("Unknown agent type for cancel: {}", agent_type)
            return

        loop = self._loops.get(agent_enum)
        if loop is None:
            logger.warning("No loop found for agent: {}", agent_type)
            return

        loop.cancel_current()
        logger.info("Cancelled current operation for agent: {}", agent_type)

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
                manifest_manager=self.manifest_manager,
                task_board=self._task_board,
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

    def get_agent_session_id(self, agent_type: AgentType) -> str | None:
        loop = self._loops.get(agent_type)
        if loop is None:
            return None
        return getattr(loop, "_current_session_id", None)

    def _create_tools_for_agent(self, agent_type: AgentType) -> ToolRegistry:
        """Create tool registry for an agent type.

        Args:
            agent_type: Type of agent.

        Returns:
            Tool registry with appropriate tools.
        """
        registry = ToolRegistry()
        file_state_manager = self._get_file_state_manager(agent_type)

        # Common tools for all agents
        registry.register(ReadTool(
            workspace=self.workspace,
            file_state_manager=file_state_manager,
        ))

        # Determine write allowed directory based on agent type
        write_dirs = {
            AgentType.DATA_ANALYSIS: self.workspace / "Data",
            AgentType.PLOTTING: self.workspace / "Plots",
            AgentType.THEORY: self.workspace / "Theory",
            AgentType.REPORT: self.workspace / "Tex",
            AgentType.MAIN: self.workspace / "Outline",  # MAIN only writes Outline/report_outline.md
        }

        write_dir = write_dirs.get(agent_type, self.workspace)

        # Register write tools
        write_tool_kwargs = dict(
            workspace=self.workspace,
            write_allowed_dir=write_dir,
            manifest_manager=self.manifest_manager,
            agent_type=agent_type.value,
            file_state_manager=file_state_manager,
        )
        if agent_type == AgentType.PLOTTING:
            from ..tools.file_tools import _validate_plotting_script
            write_tool_kwargs["content_validator"] = _validate_plotting_script

        registry.register(ApplyPatchTool(**write_tool_kwargs))
        registry.register(DeleteFileTool(
            workspace=self.workspace,
            write_allowed_dir=write_dir,
            manifest_manager=self.manifest_manager,
            agent_type=agent_type.value,
            file_state_manager=file_state_manager,
        ))

        # Execution tool (for data analysis, plotting, report agents only — MAIN delegates, does not execute)
        if agent_type in (AgentType.DATA_ANALYSIS, AgentType.PLOTTING, AgentType.REPORT):
            registry.register(ExecTool(
                working_dir=self.workspace,
                timeout=120,
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

        # Skill loading — all agents can load skills on demand
        registry.register(LoadSkillTool(skill_loader=self.skill_loader))

        # Inter-agent communication tools
        if agent_type == AgentType.MAIN:
            registry.register(
                SendToAgentTool(
                    bus=self.bus,
                    task_board=self._task_board,
                    session_id_resolver=lambda a=agent_type: self.get_agent_session_id(a),
                )
            )
        else:
            registry.register(
                ReportTool(
                    bus=self.bus,
                    agent_type=agent_type,
                    task_board=self._task_board,
                    session_id_resolver=lambda a=agent_type: self.get_agent_session_id(a),
                )
            )

        # Task management — all agents can manage their own tasks
        registry.register(ManageTasksTool(
            task_board=self._task_board,
            agent_type=agent_type,
            bus=self.bus,
            session_id_resolver=lambda a=agent_type: self.get_agent_session_id(a),
        ))

        return registry

    def _get_file_state_manager(self, agent_type: AgentType) -> FileStateManager:
        manager = self._file_state_managers.get(agent_type)
        if manager is None:
            manager = FileStateManager(workspace=self.workspace)
            self._file_state_managers[agent_type] = manager
        return manager

    async def create_checkpoint(
        self, agent_type: str, description: str = "", source: str = "pre_message",
        conversation_history: List[Dict[str, Any]] | None = None,
        message_id: str | None = None,
    ) -> str:
        """Create a per-agent checkpoint.

        Args:
            agent_type: Agent type string (e.g. "main", "data_analysis").
            description: Human-readable description.
            source: Checkpoint source — "pre_message" | "manual" | "rollback".
            conversation_history: Optional conversation history to save.
            message_id: The message that triggered this checkpoint (if any).

        Returns:
            Checkpoint ID.
        """
        checkpoint_id = await self.checkpoint_manager.create_checkpoint(
            agent_type=agent_type,
            description=description,
            source=source,
            conversation_history=conversation_history,
            message_id=message_id,
        )

        cp = self.checkpoint_manager.get_checkpoint(agent_type, checkpoint_id)
        if cp:
            from ...interfaces.types import Checkpoint as CheckpointMsg
            # For baseline: use file_states hashes directly.
            # For subsequent: derive from file_diffs (sha256_after for each file).
            if cp.file_states:
                file_hashes = {path: state.hash for path, state in cp.file_states.items()}
            else:
                file_hashes = {
                    path: d.sha256_after
                    for path, d in cp.file_diffs.items()
                    if d.sha256_after
                }
            msg = CheckpointMsg(
                agent_type=agent_type,
                checkpoint_id=checkpoint_id,
                description=cp.description,
                file_states=file_hashes,
                message_id=message_id,
            )
            await self.bus.publish(msg)

        return checkpoint_id

    async def rollback_to_checkpoint(
        self, agent_type: str, checkpoint_id: str, restore_conversation: bool = True
    ) -> Dict[str, Any]:
        """Rollback an agent to a specific checkpoint and create a post-rollback checkpoint.

        Args:
            agent_type: Agent type string.
            checkpoint_id: Checkpoint ID to rollback to.
            restore_conversation: Whether to restore conversation history to agent loop.

        Returns:
            Dictionary with restored_files count and conversation_history if restored.
        """
        # Cancel any ongoing operation first
        self.cancel_current_operation(agent_type)

        # Get checkpoint before rolling back (to access conversation history)
        cp = self.checkpoint_manager.get_checkpoint(agent_type, checkpoint_id)
        if cp is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        # Rollback files
        restored = await self.checkpoint_manager.rollback(agent_type, checkpoint_id)

        result = {
            "restored_files": restored,
            "conversation_history": cp.conversation_history if restore_conversation else [],
        }

        # Restore conversation history to agent loop if requested
        if restore_conversation and cp.conversation_history:
            from .agent_loop import LLMMessage
            loop = self._loops.get(agent_type)
            if loop:
                # Clear current history and restore from checkpoint
                loop._conversation_history.clear()
                for msg_dict in cp.conversation_history:
                    msg_dict = dict(msg_dict)
                    msg_dict["content"] = msg_dict.get("content") or ""
                    msg = LLMMessage(**msg_dict)
                    loop._conversation_history.append(msg)
                logger.info("Restored {} messages for {}", len(loop._conversation_history), agent_type)

        # Create post-rollback checkpoint
        await self.create_checkpoint(
            agent_type=agent_type,
            description=f"After rollback to {checkpoint_id[-12:]}",
            source="rollback",
        )

        return result

    async def _handle_restart_request(self, message: Message) -> None:
        """Handle restart request from GUI.

        Args:
            message: Restart request message.
        """
        if not isinstance(message, RestartRequest):
            return

        await self.restart(reason=message.reason)

    async def _handle_file_rollback_request(self, message: Message) -> None:
        """Handle file rollback request from GUI.

        Triggered when the user right-clicks a chat message and selects
        "Rollback files to this point".

        Args:
            message: FileRollbackRequest message.
        """
        if not isinstance(message, FileRollbackRequest):
            return

        logger.info(
            "Handling file rollback request: checkpoint={}, agent={}",
            message.checkpoint_id, message.agent_type,
        )

        try:
            result = await self.rollback_to_checkpoint(
                agent_type=message.agent_type,
                checkpoint_id=message.checkpoint_id,
                restore_conversation=True,
            )

            await self.bus.publish(RollbackStatus(
                checkpoint_id=message.checkpoint_id,
                agent_type=message.agent_type,
                success=True,
                restored_files=result.get("restored_files", 0),
            ))
            logger.info(
                "Rollback successful: {} files restored for agent {}",
                result.get("restored_files", 0),
                message.agent_type,
            )
        except Exception as e:
            logger.error("Rollback failed: {}", str(e))
            await self.bus.publish(RollbackStatus(
                checkpoint_id=message.checkpoint_id,
                agent_type=message.agent_type,
                success=False,
                error=str(e),
            ))

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
