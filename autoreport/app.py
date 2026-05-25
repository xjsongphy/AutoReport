"""Main application entry point."""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Annotated, Any, Dict

# Force UTF-8 encoding for all I/O operations
# This fixes Chinese character display issues on Windows systems
if sys.platform == "win32":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

import typer
from loguru import logger
from PyQt6.QtWidgets import QApplication, QDialog
from rich.console import Console

from .config import ConfigManager
from .core.loops import LoopManager, MessageBus
from .gui import MainWindow
from .interfaces.protocol import BackendAPI
from .utils import log_exception, setup_exception_handler, setup_logging

console = Console()
app = typer.Typer(
    name="autoreport",
    help="AutoReport - 物理实验报告自动撰写系统",
    rich_markup_mode="rich",
    no_args_is_help=True,
)


class _FilteredStderr:
    """Filter known noisy platform stderr lines while preserving real errors."""

    _BLOCK_PATTERNS = (
        "IMKCFRunLoopWakeUpReliable",
    )

    def __init__(self, wrapped):
        self._wrapped = wrapped
        self._buf = ""

    def write(self, data):
        if not isinstance(data, str):
            data = str(data)
        self._buf += data
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if any(pat in line for pat in self._BLOCK_PATTERNS):
                continue
            self._wrapped.write(line + "\n")
        return len(data)

    def flush(self):
        if self._buf:
            line = self._buf
            self._buf = ""
            if not any(pat in line for pat in self._BLOCK_PATTERNS):
                self._wrapped.write(line)
        self._wrapped.flush()

    def isatty(self):
        return self._wrapped.isatty() if hasattr(self._wrapped, "isatty") else False


def _install_stderr_filter() -> None:
    if sys.platform != "darwin":
        return
    if isinstance(sys.stderr, _FilteredStderr):
        return
    sys.stderr = _FilteredStderr(sys.stderr)


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
        self._qt_app: QApplication | None = None
        self._interrupted = False

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

    def _check_interrupt(self) -> None:
        if self._interrupted:
            logger.info("Shutting down via interrupt check timer...")
            from PyQt6.QtWidgets import QApplication
            QApplication.closeAllWindows()
            self._qt_app.quit()

    def run_gui(self, qt_app: QApplication) -> None:
        """Run GUI application."""
        import threading

        self._qt_app = qt_app

        # Setup signal handler for Ctrl+C
        def _handle_interrupt(*_):
            logger.info("Interrupt received, shutting down...")
            self._interrupted = True
            qt_app.quit()

        signal.signal(signal.SIGINT, _handle_interrupt)
        # Windows also supports SIGBREAK
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, _handle_interrupt)

        # Timer to check for interrupts periodically (Qt event loop blocks signals)
        from PyQt6.QtCore import QTimer
        self._interrupt_timer = QTimer()
        self._interrupt_timer.timeout.connect(self._check_interrupt)
        self._interrupt_timer.start(100)  # Check every 100ms

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
            debug_agents=list(getattr(self, "_debug_agents_on_start", [])),
        )
        self.main_window.set_async_loop(self._async_loop)
        self.main_window.prepare_initial_render()
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

    async def send_file_context(
        self,
        file_context: dict,
        agent_type: str,
    ) -> None:
        """Send file context to an agent as system message (invisible to user)."""
        from .interfaces.types import AgentType

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

        # Format file context as system message
        if file_context.get("type") == "selection":
            fp = file_context.get("file", "")
            s = file_context.get("start_line", "")
            e = file_context.get("end_line", "")
            text = file_context.get("content", "")
            context_msg = f"选中文件: {fp}\n行号: {s}-{e}\n内容:\n```\n{text}\n```\n"
        elif file_context.get("type") == "file":
            fp = file_context.get("file", "")
            context_msg = f"打开文件: {fp}\n"
        else:
            return

        # Send as system message (source="system")
        message = UserMessage(
            content=context_msg,
            agent_type=agent_type_enum,
            source="system",
        )
        await self.bus.publish(message)

    async def interrupt_current_message(self, agent_type: str) -> None:
        """Interrupt the currently processing message for an agent."""
        if self.loop_manager is None:
            logger.warning("Loop manager not initialized, cannot interrupt")
            return
        self.loop_manager.cancel_current_operation(agent_type)

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

    async def sync_agent_conversation(
        self,
        agent_type: str,
        messages: list[dict[str, str]] | None = None,
    ) -> None:
        """Replace in-memory conversation history for an agent loop."""
        if self.loop_manager is None:
            return

        from .core.providers.base import Message as LLMMessage
        from .interfaces.types import AgentType

        agent_type_map = {
            "main": AgentType.MAIN,
            "data_analysis": AgentType.DATA_ANALYSIS,
            "plotting": AgentType.PLOTTING,
            "theory": AgentType.THEORY,
            "report": AgentType.REPORT,
        }
        agent_enum = agent_type_map.get(agent_type)
        if agent_enum is None:
            return

        loop = self.loop_manager._loops.get(agent_enum)  # noqa: SLF001
        if loop is None:
            return

        loop._conversation_history.clear()  # noqa: SLF001
        for msg in messages or []:
            role = str(msg.get("role", "")).strip()
            content = str(msg.get("content", ""))
            if role not in {"user", "assistant", "system", "tool"}:
                continue
            loop._conversation_history.append(LLMMessage(role=role, content=content))  # noqa: SLF001

    async def rollback_to_checkpoint(self, agent_type: str, checkpoint_id: str) -> Dict[str, Any]:
        """Rollback an agent to a specific checkpoint.

        Returns:
            Dictionary with restored_files count and conversation_history.
        """
        if self.loop_manager is None:
            raise RuntimeError("Loop manager not initialized")

        result = await self.loop_manager.rollback_to_checkpoint(
            agent_type, checkpoint_id, restore_conversation=True
        )
        return result

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


@app.command()
def main(
    debug_agent: Annotated[
        list[str],
        typer.Option(
            "--debug-agent",
            help="在调试模式下启动指定的 Agent（可重复使用）",
        ),
    ] = [],  # noqa: B006
    sync_presets: Annotated[
        bool,
        typer.Option(
            "--sync-presets",
            help="从 cc-switch 仓库同步最新预设模板并退出",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "-v", "--verbose",
            help="输出 DEBUG 级别调试信息",
        ),
    ] = False,
) -> None:
    """AutoReport - 基于 Agent 的自动化物理实验报告撰写系统"""
    _install_stderr_filter()

    # Handle --sync-presets (CLI mode, no GUI needed)
    if sync_presets:
        setup_logging(log_level="INFO", log_to_file=True)
        console.print("[bold cyan]Syncing presets from cc-switch...[/bold cyan]")
        ok = _try_sync_presets(silent=False)
        if ok:
            from .config.presets import load_presets

            presets = load_presets()
            console.print(f"[green]Sync complete. {len(presets)} presets available.[/green]")
        else:
            console.print("[red]Sync failed. Check network/proxy settings.[/red]")
        raise typer.Exit(code=0 if ok else 1)

    # Create Qt application BEFORE any other initialization
    qt_app = QApplication(sys.argv)
    assert QApplication.instance() is not None, "QApplication creation failed"

    # Set application icon
    from PyQt6.QtGui import QIcon

    icon_path = Path(__file__).parent / "resources" / "icon.png"
    if icon_path.exists():
        qt_app.setWindowIcon(QIcon(str(icon_path)))

    # Setup logging and exception handling
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level=log_level, log_to_file=True)
    setup_exception_handler()

    logger.info("AutoReport starting...")

    app_inst = AutoReportApp()

    # Store debug agents for activation after loop manager starts
    app_inst._debug_agents_on_start = debug_agent

    # Check optional dependencies
    _check_dependencies(app_inst.config_manager)

    # Auto-sync presets on startup (failure is non-fatal)
    if not _try_sync_presets(silent=True):
        logger.info("Presets not synced — UI sync button available for retry")

    # Check API configuration first
    is_valid, _ = app_inst.config_manager.validate_api_keys()

    if not is_valid:
        from .gui.config_dialog import ConfigDialog

        dialog = ConfigDialog(app_inst.config_manager)
        result = dialog.exec()

        if result != QDialog.DialogCode.Accepted:
            logger.info("Configuration cancelled by user")
            raise typer.Exit(code=0)

        is_valid, _ = app_inst.config_manager.validate_api_keys()
        if not is_valid:
            logger.error("Still no valid API keys after configuration")
            raise typer.Exit(code=1)

    # Run GUI (includes project selection and startup)
    app_inst.run_gui(qt_app)

    # Shutdown
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(app_inst.shutdown())
    except Exception as e:
        log_exception("Error during shutdown", e)
    finally:
        del qt_app


if __name__ == "__main__":
    app()
