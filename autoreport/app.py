"""Main application entry point."""

import asyncio
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QDialog
from loguru import logger

from .config import ConfigManager
from .core.loops import MessageBus, LoopManager
from .interfaces.protocol import BackendAPI
from .gui import MainWindow
from .utils import setup_logging, setup_exception_handler, log_exception


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
            gui=self.backend,
        )

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

        # Create loop manager
        self.loop_manager = LoopManager(
            workspace=workspace,
            config_manager=self.config_manager,
            bus=self.bus,
            gui=self.backend,
        )

        # Start message bus processing
        asyncio.create_task(self.bus.process_queue())

        # Start agent loops
        await self.loop_manager.start()

        logger.info("Application started successfully")
        return True

    async def shutdown(self) -> None:
        """Shutdown application."""
        if self.loop_manager:
            await self.loop_manager.stop()
        logger.info("Application shut down")

    def run_gui(self) -> None:
        """Run GUI application."""
        app = QApplication(sys.argv)

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

        # Now startup with selected workspace
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            success = loop.run_until_complete(self.startup(workspace))
            if not success:
                logger.error("Failed to start application")
                sys.exit(1)
        except Exception as e:
            log_exception("Error during startup", e)
            sys.exit(1)

        # Create main window with selected workspace
        self.main_window = MainWindow(
            backend=self.backend,
            workspace=workspace,
        )
        self.main_window.show()

        sys.exit(app.exec())


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

    async def send_user_message(
        self,
        content: str,
        agent_type: str,
        message_id: str | None = None
    ) -> None:
        """Send a user message to an agent."""
        from ...interfaces.types import UserMessage
        message = UserMessage(
            content=content,
            agent_type=agent_type,
            message_id=message_id,
        )
        await self.bus.publish(message)

    async def restart_agents(self, reason: str) -> None:
        """Restart the agent system."""
        from ...interfaces.types import RestartRequest
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
        # TODO: Implement rollback
        pass

    def subscribe_to_messages(
        self,
        callback
    ) -> None:
        """Subscribe to all backend messages."""
        from ...interfaces.types import Message
        self.bus.subscribe(Message, callback)


def main():
    """Main entry point."""
    # Setup logging
    setup_logging(log_level="INFO", log_to_file=True)

    # Setup global exception handler
    setup_exception_handler()

    logger.info("AutoReport starting...")

    app = AutoReportApp()

    # Check API configuration first
    is_valid, _ = app.config_manager.validate_api_keys()

    # Create Qt application first (needed for dialogs)
    qt_app = QApplication(sys.argv)

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

    # Shutdown
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(app.shutdown())
    except Exception as e:
        log_exception("Error during shutdown", e)


if __name__ == "__main__":
    main()
