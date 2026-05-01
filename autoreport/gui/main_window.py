"""Main application window."""

import asyncio
from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QWidget,
)

from ..interfaces.protocol import BackendAPI
from ..interfaces.types import (
    AgentResponse,
    Checkpoint,
    Error,
    Message,
    StatusChange,
    ToolCall,
    ToolResult,
)
from .widgets.agent_panel import AgentPanel
from .widgets.file_tree import FileTreeWidget
from .widgets.preview import PreviewWidget


class MainWindow(QMainWindow):
    """Main application window.

    Implements the GUIAPI protocol via duck-typing (cannot use multiple
    inheritance with QMainWindow because of metaclass conflict).
    """

    # Signal for thread-safe message delivery from async bus to Qt thread
    _message_signal = pyqtSignal(object)

    def __init__(self, backend: BackendAPI, workspace: Path):
        """Initialize main window.

        Args:
            backend: Backend API for communication.
            workspace: Project workspace directory.
        """
        super().__init__()
        self.backend = backend
        self.workspace = Path(workspace).resolve()
        self._async_loop: asyncio.AbstractEventLoop | None = None

        self.setWindowTitle("AutoReport - 物理实验报告撰写系统")
        self.resize(1400, 900)

        # Apply VSCode-inspired global theme
        self._apply_theme()

        # Setup UI
        self._setup_ui()

        # Connect signal for thread-safe message delivery
        self._message_signal.connect(self._dispatch_backend_message)

        # Subscribe to backend messages via signal bridge
        self.backend.subscribe_to_messages(self._on_bus_message)

        logger.info("Main window initialized for workspace: {}", self.workspace)

    def _apply_theme(self) -> None:
        """Apply VSCode-inspired global theme."""
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        c = {
            "bg": "#1e1e1e" if dark else "#ffffff",
            "border": "#3c3c3c" if dark else "#e0e0e0",
            "fg": "#cccccc" if dark else "#333333",
            "fg_dim": "#858585" if dark else "#888888",
            "hover": "#2a2d2e" if dark else "#e8e8e8",
            "scroll": "#424242" if dark else "#c1c1c1",
            "title": "#323233" if dark else "#ebebeb",
            "splitter": "#3c3c3c" if dark else "#e0e0e0",
        }

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {c["bg"]};
                color: {c["fg"]};
            }}
            QWidget {{
                color: {c["fg"]};
            }}
            QSplitter::handle {{
                background-color: {c["splitter"]};
            }}
            QSplitter::handle:horizontal {{
                width: 1px;
            }}
            QSplitter::handle:vertical {{
                height: 1px;
            }}
            QScrollBar:vertical {{
                background-color: {c["bg"]};
                width: 10px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c["scroll"]};
                min-height: 30px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {c["fg_dim"]};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background-color: {c["bg"]};
                height: 10px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {c["scroll"]};
                min-width: 30px;
                border-radius: 5px;
            }}
            QToolBar {{
                background-color: {c["title"]};
                border-bottom: 1px solid {c["border"]};
                spacing: 4px;
                padding: 2px;
            }}
            QToolTip {{
                background-color: {c["title"]};
                color: {c["fg"]};
                border: 1px solid {c["border"]};
                padding: 4px;
                font-size: 12px;
            }}
        """)

    def _setup_ui(self) -> None:
        """Setup user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter for left/center/right sections
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter)

        # Left section: File tree
        self.file_tree = FileTreeWidget(self.workspace)
        self.file_tree.setMinimumWidth(200)
        self.file_tree.setMaximumWidth(400)
        self.file_tree.directory_selected.connect(self._on_directory_selected)
        self.file_tree.file_selected.connect(self._on_file_selected)
        main_splitter.addWidget(self.file_tree)

        # Center section: Preview
        self.preview = PreviewWidget(self.workspace)
        self.preview.setMinimumWidth(400)
        main_splitter.addWidget(self.preview)

        # Right section: Agent panels
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(right_splitter)

        # Top-right: Main agent panel
        self.main_agent_panel = AgentPanel("main", "Main Agent", self.workspace)
        self.main_agent_panel.setMinimumHeight(300)
        right_splitter.addWidget(self.main_agent_panel)

        # Bottom-right: Sub-agent panel
        self.sub_agent_panel = AgentPanel("sub", "Sub Agent", self.workspace)
        self.sub_agent_panel.setMinimumHeight(300)
        right_splitter.addWidget(self.sub_agent_panel)

        # Set splitter sizes
        main_splitter.setSizes([250, 500, 650])
        right_splitter.setSizes([300, 300])

        # Connect signals
        self.main_agent_panel.message_sent.connect(self._on_main_agent_message)
        self.sub_agent_panel.message_sent.connect(self._on_sub_agent_message)
        self.sub_agent_panel.debug_mode_toggled.connect(self._on_debug_mode_toggled)

        # Connect preview selection to sub-agent panel context
        self.preview.selection_changed.connect(self._on_preview_selection_changed)

        # Hide debug button on main agent panel (debug mode is for sub-agents only)
        self.main_agent_panel.hide_debug_button(hide=True)

    def _on_directory_selected(self, directory: str) -> None:
        """Handle directory selection.

        Args:
            directory: Selected directory name (data, refs, theory, code, tex).
        """
        self.preview.set_directory(directory)

        # Update sub-agent panel based on directory
        agent_map = {
            "data": "data_analysis",
            "refs": "main",
            "theory": "theory",
            "code": "plotting",
            "tex": "report",
        }
        agent_type = agent_map.get(directory, "sub")
        self.sub_agent_panel.set_agent_type(agent_type)

    def _on_preview_selection_changed(self, file_path: str, selected_text: str, start_line: int, end_line: int) -> None:
        """Handle preview text selection.

        Args:
            file_path: Relative file path.
            selected_text: Selected text content.
            start_line: Start line number.
            end_line: End line number.
        """
        # Forward selection context to sub-agent panel
        self.sub_agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)

    def _on_file_selected(self, file_path: Path) -> None:
        """Handle file selection from file tree.

        Args:
            file_path: Selected file path.
        """
        # Load file in preview
        self.preview.load_file(file_path)
        logger.debug("File selected: {}", file_path)

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the async event loop for thread-safe coroutine dispatch.

        Must be called after startup() creates the loop, before the user
        can interact with the GUI.

        Args:
            loop: The running asyncio event loop from the backend.
        """
        self._async_loop = loop

    def _submit_coroutine(self, coro):
        """Submit a coroutine to the async event loop from the Qt thread."""
        if self._async_loop is None:
            logger.warning("No async loop set, cannot dispatch coroutine")
            return
        asyncio.run_coroutine_threadsafe(coro, self._async_loop)

    def _on_main_agent_message(self, content: str) -> None:
        """Handle main agent message send."""
        self._submit_coroutine(self.backend.send_user_message(content, "main"))

    def _on_sub_agent_message(self, content: str) -> None:
        """Handle sub-agent message send."""
        agent_type = self.sub_agent_panel.agent_type
        self._submit_coroutine(self.backend.send_user_message(content, agent_type))

    def _on_debug_mode_toggled(self, enabled: bool) -> None:
        """Handle debug mode toggle.

        Args:
            enabled: Whether debug mode is enabled.
        """
        agent_type = self.sub_agent_panel.agent_type
        self.backend.set_agent_debug_mode(agent_type, enabled)

    def _on_bus_message(self, message: Message) -> None:
        """Bus callback — emits signal to marshal message to Qt thread.

        This is called from the async event loop thread, so we must NOT
        touch Qt widgets directly. Instead, emit a signal.
        """
        self._message_signal.emit(message)

    def _dispatch_backend_message(self, message: Message) -> None:
        """Handle message in the Qt thread (triggered by signal).

        Args:
            message: Message from backend.
        """
        from ..interfaces.types import (
            AgentResponse,
            Checkpoint,
            Error,
            StatusChange,
            ToolCall,
            ToolResult,
        )

        if isinstance(message, AgentResponse):
            self._handle_agent_response(message)
        elif isinstance(message, ToolCall):
            self._handle_tool_call(message)
        elif isinstance(message, ToolResult):
            self._handle_tool_result(message)
        elif isinstance(message, StatusChange):
            self._handle_status_change(message)
        elif isinstance(message, Error):
            self._handle_error(message)
        elif isinstance(message, Checkpoint):
            self._handle_checkpoint(message)

    def _handle_agent_response(self, message: AgentResponse) -> None:
        """Handle agent response."""
        panel = self._get_panel_for_agent(message.agent_type)
        panel.add_message("agent", message.content)

    def _handle_tool_call(self, message: ToolCall) -> None:
        """Handle tool call."""
        panel = self._get_panel_for_agent(message.agent_type)
        panel.add_tool_call(message.tool_name, message.arguments)

    def _handle_tool_result(self, message: ToolResult) -> None:
        """Handle tool result."""
        panel = self._get_panel_for_agent(message.agent_type)
        panel.add_tool_result(message.tool_name, message.result, message.error)

    def _handle_status_change(self, message: StatusChange) -> None:
        """Handle status change."""
        panel = self._get_panel_for_agent(message.agent_type)
        panel.set_status(message.status, message.extra)

    def _handle_error(self, message: Error) -> None:
        """Handle error."""
        self.main_agent_panel.add_error(message.source, message.message)

    def _handle_checkpoint(self, message: Checkpoint) -> None:
        """Handle checkpoint."""
        self.main_agent_panel.add_checkpoint(message.checkpoint_id, message.description)

    def _get_panel_for_agent(self, agent_type: str) -> AgentPanel:
        """Get agent panel for agent type."""
        if agent_type == "main":
            return self.main_agent_panel
        else:
            return self.sub_agent_panel
