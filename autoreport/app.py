"""Main application entry point."""

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger
from PyQt6.QtWidgets import QApplication, QDialog

from .config import ConfigManager
from .core.loops import LoopManager, MessageBus
from .gui import MainWindow
from .interfaces.protocol import BackendAPI
from .utils import log_exception, setup_exception_handler, setup_logging


class AutoReportApp:
    """Main AutoReport application."""

    def __init__(self):
        """Initialize application."""
        self.config_manager = ConfigManager()
        self.bus = MessageBus()
        self.backend = BackendAPIImpl(
            config_manager=self.config_manager,
            bus=self.bus,
        )
        self.loop_manager: LoopManager | None = None
        self.main_window: MainWindow | None = None

    async def startup(self, workspace: Path) -> bool:
        """Startup application. Returns True if successful.

        Args:
            workspace: Project workspace path.

        Returns:
            True if startup successful, False otherwise.
        """
        # Validate API keys
        is_valid, available = self.config_manager.validate_api_keys()
        if not is_valid:
            logger.warning("No API keys configured.")
            return False

        logger.info("Available providers: {}", available)

        # Use provided workspace
        workspace = Path(workspace).resolve()

        # Create project structure if needed
        self._ensure_project_structure(workspace)

        # Create loop manager
        self.loop_manager = LoopManager(
            workspace=workspace,
            config_manager=self.config_manager,
            bus=self.bus,
        )

        # Set loop manager in backend (for rollback functionality)
        self.backend.set_loop_manager(self.loop_manager)

        # Start message bus processing
        asyncio.create_task(self.bus.process_queue())

        # Start agent loops
        await self.loop_manager.start()

        logger.info("Application started successfully with workspace: {}", workspace)
        return True

    def _ensure_project_structure(self, workspace: Path) -> None:
        """Ensure project directory structure exists.

        Args:
            workspace: Project workspace path.
        """
        project_dirs = [
            workspace / "data",
            workspace / "data" / "processed",
            workspace / "references",
            workspace / "theory",
            workspace / "code",
            workspace / "tex",
        ]

        for dir_path in project_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)

        logger.debug("Ensured project structure in: {}", workspace)

    async def shutdown(self) -> None:
        """Shutdown application."""
        # Signal bus to stop processing
        self.bus.shutdown()

        if self.loop_manager:
            await self.loop_manager.stop()

        # Give pending tasks a moment to finish
        await asyncio.sleep(0.5)

        # Cancel remaining tasks
        loop = asyncio.get_event_loop()
        for task in asyncio.all_tasks(loop):
            if task is not asyncio.current_task():
                task.cancel()

        logger.info("Application shut down")

    def run_gui(self) -> None:
        """Run GUI application."""
        import threading

        # QApplication already created in main(), get the instance
        app = QApplication.instance()

        # Show project selection dialog first
        from .gui.project_dialog import ProjectDialog

        project_dialog = ProjectDialog(self.config_manager)

        # Store workspace path
        workspace: Path | None = None

        def on_project_selected(path: Path):
            nonlocal workspace
            workspace = path

        project_dialog.project_selected.connect(on_project_selected)

        # Show project dialog
        result = project_dialog.exec()

        if result != QDialog.DialogCode.Accepted:
            logger.info("Project selection cancelled")
            sys.exit(0)

        if workspace is None:
            logger.error("No workspace selected")
            sys.exit(1)

        # Create a dedicated async event loop for the backend
        self._async_loop = asyncio.new_event_loop()

        # Run startup in the async loop
        try:
            success = self._async_loop.run_until_complete(self.startup(workspace))
            if not success:
                logger.error("Failed to start application")
                sys.exit(1)
        except Exception as e:
            log_exception("Error during startup", e)
            sys.exit(1)

        # Keep the async loop running in a background thread so
        # run_coroutine_threadsafe works from the Qt GUI thread.
        def _run_loop():
            asyncio.set_event_loop(self._async_loop)
            self._async_loop.run_forever()

        self._loop_thread = threading.Thread(target=_run_loop, daemon=True)
        self._loop_thread.start()

        # Activate debug mode for agents specified via --debug-agent
        for agent in getattr(self, "_debug_agents_on_start", []):
            self.set_agent_debug_mode(agent, enabled=True)
            logger.info("Debug mode activated for {} (via CLI)", agent)

        # Create main window with selected workspace
        self.main_window = MainWindow(
            backend=self.backend,
            workspace=workspace,
        )
        self.main_window.set_async_loop(self._async_loop)
        self.main_window.show()

        exit_code = app.exec()

        # Graceful shutdown: run async cleanup in the loop
        future = asyncio.run_coroutine_threadsafe(self.shutdown(), self._async_loop)
        try:
            future.result(timeout=5)
        except Exception:
            pass

        # Stop the background event loop
        self._async_loop.call_soon_threadsafe(self._async_loop.stop)
        self._loop_thread.join(timeout=5)

        sys.exit(exit_code)


class BackendAPIImpl(BackendAPI):
    """Backend API implementation."""

    def __init__(
        self,
        config_manager: ConfigManager,
        bus: MessageBus,
    ):
        """Initialize backend API.

        Args:
            config_manager: Configuration manager.
            bus: Message bus.
        """
        self.config_manager = config_manager
        self.bus = bus
        self.loop_manager: LoopManager | None = None

    def set_loop_manager(self, loop_manager: LoopManager) -> None:
        """Set the loop manager (called after it's created).

        Args:
            loop_manager: Loop manager instance.
        """
        self.loop_manager = loop_manager

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
        from .interfaces.types import AgentType, UserMessage

        # Map string to AgentType enum
        agent_type_map = {
            "main": AgentType.MAIN,
            "data_analysis": AgentType.DATA_ANALYSIS,
            "plotting": AgentType.PLOTTING,
            "theory": AgentType.THEORY,
            "report": AgentType.REPORT,
            "sub": AgentType.MAIN,  # Default to main for "sub"
        }
        agent_type_enum = agent_type_map.get(agent_type, AgentType.MAIN)

        message = UserMessage(
            content=content,
            agent_type=agent_type_enum,
            message_id=message_id,
            source=source,
        )
        await self.bus.publish(message)

    async def restart_agents(self, reason: str) -> None:
        """Restart the agent system."""
        from .interfaces.types import RestartRequest
        message = RestartRequest(reason=reason)
        await self.bus.publish(message)

    async def switch_provider(self, provider: str) -> None:
        """Switch to a different provider."""
        # Update config
        self.config_manager.config.agents.defaults.provider = provider
        # Restart agents
        await self.restart_agents(reason="config_change")

    async def switch_model(self, model: str) -> None:
        """Switch to a different model."""
        # Update config
        self.config_manager.config.agents.defaults.model = model
        # No restart needed for model change

    async def rollback_to_checkpoint(self, checkpoint_id: str) -> None:
        """Rollback to a specific checkpoint."""
        if self.loop_manager is None:
            raise RuntimeError("Loop manager not initialized")

        await self.loop_manager.rollback_to_checkpoint(checkpoint_id)

    def set_agent_debug_mode(self, agent_type: str, enabled: bool) -> None:
        """Enable or disable debug mode for an agent."""
        if self.loop_manager is None:
            raise RuntimeError("Loop manager not initialized")

        self.loop_manager.set_agent_debug_mode(agent_type, enabled)

    def subscribe_to_messages(
        self,
        callback
    ) -> None:
        """Subscribe to all backend messages."""
        from .interfaces.types import Message
        self.bus.subscribe(Message, callback)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="AutoReport - 物理实验报告自动撰写系统",
    )
    parser.add_argument(
        "--debug-agent",
        action="append",
        default=[],
        choices=["data_analysis", "plotting", "theory", "report"],
        help="在调试模式下启动指定的 Agent（可重复使用）",
    )
    parser.add_argument(
        "--sync-presets",
        action="store_true",
        default=False,
        help="从 cc-switch 仓库同步最新预设模板并退出",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="输出 DEBUG 级别调试信息",
    )
    return parser.parse_args(argv)


def _try_sync_presets(silent: bool = False) -> bool:
    """Try to sync presets from cc-switch. Returns True on success."""
    from .core.preset_sync import is_cached, sync_presets

    try:
        if is_cached():
            logger.debug("Presets already cached, skipping auto-sync")
            return True
        n = sync_presets(timeout=10)
        logger.info("Auto-synced {} preset files from cc-switch", n)
        return True
    except Exception as e:
        if not silent:
            logger.warning("Preset sync failed (network/proxy issue): {}", e)
        return False


def _check_dependencies(config_manager: ConfigManager) -> None:
    """Check for optional tool dependencies and log warnings."""
    import shutil

    # LaTeX
    if not shutil.which("xelatex") and not shutil.which("lualatex"):
        logger.warning(
            "LaTeX not found (xelatex/lualatex). "
            "Report compilation will fail. "
            "Install TeX Live or MiKTeX."
        )

    # MinerU
    cfg = config_manager.config
    check_mineru = (
        hasattr(cfg, "mineru_api")
        and cfg.mineru_api.enabled
        and cfg.mineru_api.validate_on_startup
    )
    if check_mineru and not shutil.which("mineru-open-api"):
        logger.warning(
            "mineru-open-api not found. PDF parsing will be unavailable. "
            "Install: https://mineru.net/ecosystem?tab=cli"
        )


def main():
    """Main entry point."""
    # Parse arguments first (no GUI needed)
    args = parse_args()

    # Handle --sync-presets (CLI mode, no GUI)
    if args.sync_presets:
        setup_logging(log_level="INFO", log_to_file=True)
        print("Syncing presets from cc-switch...")
        ok = _try_sync_presets(silent=False)
        if ok:
            from .config.presets import load_presets
            presets = load_presets()
            print(f"Sync complete. {len(presets)} presets available.")
        else:
            print("Sync failed. Check network/proxy settings.")
        sys.exit(0 if ok else 1)

    # Create Qt application BEFORE any other initialization.
    # Must keep a strong reference to prevent garbage collection.
    qt_app = QApplication(sys.argv)
    assert QApplication.instance() is not None, "QApplication creation failed"

    # Set application icon
    from PyQt6.QtGui import QIcon
    icon_path = Path(__file__).parent / "resources" / "icon.png"
    if icon_path.exists():
        qt_app.setWindowIcon(QIcon(str(icon_path)))

    # Now safe to setup logging and exception handling
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level=log_level, log_to_file=True)
    setup_exception_handler()

    logger.info("AutoReport starting...")

    app = AutoReportApp()

    # Store debug agents for activation after loop manager starts
    app._debug_agents_on_start = args.debug_agent

    # Check optional dependencies
    _check_dependencies(app.config_manager)

    # Auto-sync presets on startup (failure is non-fatal)
    if not _try_sync_presets(silent=True):
        logger.info("Presets not synced — UI sync button available for retry")

    # Check API configuration first
    is_valid, _ = app.config_manager.validate_api_keys()

    if not is_valid:
        # Show config dialog
        from .gui.config_dialog import ConfigDialog
        dialog = ConfigDialog(app.config_manager)
        result = dialog.exec()

        if result != QDialog.DialogCode.Accepted:
            logger.info("Configuration cancelled by user")
            sys.exit(0)

        # Re-validate after config
        is_valid, available = app.config_manager.validate_api_keys()
        if not is_valid:
            logger.error("Still no valid API keys after configuration")
            sys.exit(1)

    # Run GUI (includes project selection and startup)
    app.run_gui()

    # Shutdown (keep qt_app alive until exit)
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(app.shutdown())
    except Exception as e:
        log_exception("Error during shutdown", e)
    finally:
        del qt_app


if __name__ == "__main__":
    main()
