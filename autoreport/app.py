"""Main application entry point."""

import asyncio
import importlib.resources
import os
import shutil
import signal
import sys
from pathlib import Path
from typing import Annotated, Any, Dict

# Force UTF-8 encoding for all I/O operations
# This fixes Chinese character display issues on Windows systems
if sys.platform == "win32":
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
from .utils.editor_context import build_editor_context_prompt
from .utils import add_project_logging, log_exception, setup_exception_handler, setup_logging

console = Console()
app = typer.Typer(
    name="autoreport",
    help="AutoReport - 物理实验报告自动撰写系统",
    rich_markup_mode="rich",
    no_args_is_help=True,
)


# Known noisy macOS platform lines (byte patterns) to drop from stderr.
_BLOCK_STDERR_PATTERNS = (b"IMKCFRunLoopWakeUpReliable",)


def _install_stderr_filter() -> None:
    """Redirect OS-level stderr through a line filter on macOS.

    Qt (``qWarning``) and macOS system frameworks (IMK / ``NSLog``) write
    directly to the stderr file descriptor, bypassing Python's ``sys.stderr``
    object — so wrapping ``sys.stderr`` cannot suppress them.  We instead point
    fd 2 at a pipe and filter the byte stream on a background thread, dropping
    known noisy platform lines before forwarding survivors to the real stderr.

    Tool subprocesses capture their own stderr (``stderr=PIPE``), so they are
    unaffected.  A detached relaunch child inherits fd 2 (this pipe); once the
    parent exits the child's forward target is gone — on that broken-pipe error
    the pump keeps draining-and-discarding so the child never blocks on a full
    pipe (it simply stops forwarding, which is harmless for a relaunched app).
    """
    import os
    import threading

    if sys.platform != "darwin":
        return

    try:
        real_stderr_fd = os.dup(2)
        read_fd, write_fd = os.pipe()
        os.dup2(write_fd, 2)
        os.close(write_fd)
    except OSError:
        return  # Don't let filter setup break app startup.

    def _pump() -> None:
        buf = b""
        forward_dead = False
        while True:
            try:
                chunk = os.read(read_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            if forward_dead:
                continue  # keep draining so the pipe can never fill / block.
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if any(pat in line for pat in _BLOCK_STDERR_PATTERNS):
                    continue
                try:
                    os.write(real_stderr_fd, line + b"\n")
                except OSError:
                    forward_dead = True
                    buf = b""
                    break
        # Flush any trailing partial line that lacks a newline.
        if buf and not forward_dead and not any(pat in buf for pat in _BLOCK_STDERR_PATTERNS):
            try:
                os.write(real_stderr_fd, buf)
            except OSError:
                pass
        try:
            os.close(read_fd)
        except OSError:
            pass

    threading.Thread(target=_pump, daemon=True, name="stderr-filter").start()


def _copy_builtin_templates(workspace: Path) -> None:
    """Copy built-in LaTeX template files to Tex/ on first project open.

    Only copies files that don't already exist — user or agent modifications
    are never overwritten.  User-provided templates in References/ are
    handled by the Report Agent at writing time (see report_agent.md).

    Args:
        workspace: Project workspace path.

    Raises:
        RuntimeError: If critical template file (main.tex) fails to copy.
    """
    tex_dir = workspace / "tex"
    template_root = importlib.resources.files("autoreport.templates.reports")

    # main.tex (PKUMpLtX-based template) - CRITICAL for LaTeX compilation
    dst_tex = tex_dir / "main.tex"
    if not dst_tex.exists():
        src = template_root / "template_mpl.tex"
        if src.is_file():
            try:
                shutil.copy2(str(src), str(dst_tex))
                logger.info("Copied built-in template → Tex/main.tex")
            except OSError as e:
                logger.error("Failed to copy built-in template: {}", e)
                raise RuntimeError(
                    f"Failed to copy critical template file main.tex: {e}. "
                    "LaTeX compilation will not work without this file."
                ) from e
        else:
            logger.warning("Built-in template template_mpl.tex not found in package")

    # mpltx.cls (document class, must be alongside main.tex for xelatex) - CRITICAL
    dst_cls = tex_dir / "mpltx.cls"
    if not dst_cls.exists():
        src = template_root / "mpltx.cls"
        if src.is_file():
            try:
                shutil.copy2(str(src), str(dst_cls))
                logger.info("Copied built-in .cls → Tex/mpltx.cls")
            except OSError as e:
                logger.error("Failed to copy built-in .cls: {}", e)
                raise RuntimeError(
                    f"Failed to copy critical class file mpltx.cls: {e}. "
                    "LaTeX compilation will not work without this file."
                ) from e
        else:
            logger.warning("Built-in class mpltx.cls not found in package")

    # requirements.md (writing style guide, built-in only) - OPTIONAL
    dst_req = tex_dir / "requirements.md"
    if not dst_req.exists():
        src = template_root / "requirements.md"
        if src.is_file():
            try:
                shutil.copy2(str(src), str(dst_req))
                logger.debug("Copied built-in requirements.md")
            except OSError as e:
                logger.warning("Failed to copy requirements.md: {}", e)
                # Non-critical, don't raise exception
        else:
            logger.debug("Built-in requirements.md not found in package")


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

        # Add project-bound logging (in addition to global ./logs/)
        add_project_logging(workspace)

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
            workspace / "Outline",
            workspace / "tex",
        ]

        for dir_path in project_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Copy built-in LaTeX template files to tex/ (only if not already present).
        # mpltx.cls must be in the same directory as main.tex for xelatex to find it.
        _copy_builtin_templates(workspace)

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

    def run_gui(self, qt_app: QApplication, project: Path | None = None) -> None:
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

        wants_tutorial = False
        workspace: Path | None = None

        if project is not None:
            # Direct project open (e.g. workspace switch relaunch):
            # skip welcome guide and project selection dialog.
            workspace = Path(project).expanduser().resolve()
            logger.info("Opening project directly: {}", workspace)
        else:
            # ── Phase 1: Pre-project welcome guide ──
            from .gui.onboarding import show_pre_project_guide
            wants_tutorial = show_pre_project_guide()

            # Show project selection dialog first
            from .gui.project_dialog import ProjectDialog

            project_dialog = ProjectDialog(self.config_manager)

            def on_project_selected(path: Path):
                nonlocal workspace
                workspace = path

            project_dialog.project_selected.connect(on_project_selected)

            # Show project dialog
            result = project_dialog.exec()

            # The "新手提示" button may have re-enabled the tutorial from inside
            # the project dialog; honor that choice for the Phase 2 tutorial.
            wants_tutorial = wants_tutorial or project_dialog.wants_tutorial

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

        # ── Phase 2: Post-project tutorial (only if user chose "new user" in Phase 1) ──
        if wants_tutorial:
            from .gui.onboarding import show_onboarding
            show_onboarding(self.main_window)

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

        # Format file context as system message.
        # Keep context strictly scoped to the attachment shown in agent composer.
        if file_context.get("type") == "selection":
            context_msg = build_editor_context_prompt(
                {
                    "type": "selection",
                    "file": file_context.get("file", ""),
                    "selected_lines": f"{file_context.get('start_line', '')}-{file_context.get('end_line', '')}",
                },
                "",
            )
            context_msg = (
                f"{context_msg}\n"
                "Constraint: selected text is not attached; do not infer or list other open tabs.\n"
            ).strip()
        elif file_context.get("type") == "file":
            context_msg = build_editor_context_prompt(
                {
                    "type": "file",
                    "file": file_context.get("file", ""),
                },
                "",
            )
            context_msg = (
                f"{context_msg}\n"
                "Constraint: do not infer or list other open tabs.\n"
            ).strip()
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
        session_id: str | None = None,
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

        loop._current_session_id = session_id  # noqa: SLF001

        loop._conversation_history.clear()  # noqa: SLF001
        for msg in messages or []:
            role = str(msg.get("role", "")).strip()
            content = str(msg.get("content", ""))
            is_tool_result = bool(msg.get("is_tool_result", False))
            if role not in {"user", "assistant", "system"}:
                continue
            loop._conversation_history.append(LLMMessage(role=role, content=content, is_tool_result=is_tool_result))  # noqa: SLF101

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
    project: Annotated[
        Path | None,
        typer.Option(
            "--project", "-p",
            help="直接打开指定项目目录（跳过项目选择对话框，用于切换工作区）",
        ),
    ] = None,
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
    app_inst.run_gui(qt_app, project=project)

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
