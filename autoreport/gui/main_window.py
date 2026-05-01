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

from ..core.conversations import ConversationStore
from ..interfaces.protocol import BackendAPI
from ..interfaces.types import (
    AgentResponse,
    Checkpoint,
    Error,
    Message,
    StatusChange,
    ToolCall,
    ToolResult,
    UserMessage,
)
from .widgets.agent_panel import AgentPanel
from .widgets.conversation_history import ConversationHistoryDialog
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

        # Conversation persistence
        self._conv_store = ConversationStore(workspace)

        # Apply VSCode-inspired global theme
        self._apply_theme()

        # Setup UI
        self._setup_ui()

        # Load previous conversations
        self._load_conversations()

        # Connect signal for thread-safe message delivery
        self._message_signal.connect(self._dispatch_backend_message)

        # Subscribe to backend messages via signal bridge
        self.backend.subscribe_to_messages(self._on_bus_message)

        # Subscribe agent panels to ApiDebugMessage
        self._subscribe_to_debug_messages()

        logger.info("Main window initialized for workspace: {}", self.workspace)

    def _apply_theme(self) -> None:
        """Apply VSCode-inspired global theme matching Cline's exact color tokens.

        Cline maps to --vscode-* CSS custom properties. We replicate those
        values for dark/light themes since PyQt6 QSS has no CSS-variable support.
        """
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        if dark:
            c = {
                "editor_bg": "#1e1e1e",
                "sidebar_bg": "#252526",
                "fg": "#cccccc",
                "muted": "#8b949e",
                "border": "#3c3c3c",
                "focus": "#007acc",
                "input_bg": "#3c3c3c",
                "input_fg": "#cccccc",
                "input_border": "#3c3c3c",
                "input_placeholder": "#8b949e",
                "badge_bg": "#4d4d4d",
                "badge_fg": "#ffffff",
                "button_bg": "#0e639c",
                "button_fg": "#ffffff",
                "button_hover": "#1177bb",
                "error": "#f14c4c",
                "success": "#4ec9b0",
                "warning": "#cca700",
                "link": "#3794ff",
                "code_bg": "#1e1e1e",
                "scrollbar": "#424242",
                "scrollbar_hover": "#686868",
                "titlebar_bg": "#323233",
                "hover": "#2a2d2e",
                "selection": "#264f78",
                "shadow": "rgba(0,0,0,0.36)",
            }
        else:
            c = {
                "editor_bg": "#ffffff",
                "sidebar_bg": "#f3f3f3",
                "fg": "#333333",
                "muted": "#8b949e",
                "border": "#e0e0e0",
                "focus": "#007acc",
                "input_bg": "#ffffff",
                "input_fg": "#333333",
                "input_border": "#e0e0e0",
                "input_placeholder": "#8b949e",
                "badge_bg": "#e8e8e8",
                "badge_fg": "#333333",
                "button_bg": "#0e639c",
                "button_fg": "#ffffff",
                "button_hover": "#1177bb",
                "error": "#c62828",
                "success": "#2e7d32",
                "warning": "#e65100",
                "link": "#007acc",
                "code_bg": "#f8f8f8",
                "scrollbar": "#c1c1c1",
                "scrollbar_hover": "#a1a1a1",
                "titlebar_bg": "#ebebeb",
                "hover": "#e8e8e8",
                "selection": "#add6ff",
                "shadow": "rgba(0,0,0,0.12)",
            }

        self._theme_colors = c

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {c["sidebar_bg"]};
                color: {c["fg"]};
            }}
            QWidget {{
                color: {c["fg"]};
                font-size: 14px;
            }}
            QSplitter::handle {{
                background-color: {c["border"]};
            }}
            QSplitter::handle:horizontal {{
                width: 1px;
            }}
            QSplitter::handle:vertical {{
                height: 1px;
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: 10px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c["scrollbar"]};
                min-height: 30px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {c["scrollbar_hover"]};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background-color: transparent;
                height: 10px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {c["scrollbar"]};
                min-width: 30px;
                border-radius: 5px;
            }}
            QToolBar {{
                background-color: {c["titlebar_bg"]};
                border-bottom: 1px solid {c["border"]};
                spacing: 4px;
                padding: 2px;
            }}
            QToolTip {{
                background-color: {c["titlebar_bg"]};
                color: {c["fg"]};
                border: 1px solid {c["border"]};
                padding: 4px;
                font-size: 12px;
            }}
            /* MessageRow — Cline flat timeline style */
            QLabel#msgTimestamp {{
                font-size: 11px;
                color: {c["muted"]};
            }}
            QLabel#msgRole {{
                font-size: 11px;
                font-weight: 600;
                color: {c["fg"]};
            }}
            QLabel#msgCoordination {{
                font-size: 11px;
                color: {c["muted"]};
            }}
            QWidget#userMessageBubble {{
                background-color: {c["badge_bg"]};
                border-radius: 2px;
                margin: 4px 0px;
            }}
            QLabel#userMessageText {{
                color: {c["badge_fg"]};
                font-size: 13px;
            }}
            QLabel#agentMessageText {{
                color: {c["fg"]};
                font-size: 13px;
                background-color: transparent;
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

        # Connect conversation history signals (both panels)
        self.main_agent_panel.history_requested.connect(self._on_history_requested)
        self.main_agent_panel.new_conversation_requested.connect(self._on_new_conversation_requested)
        self.sub_agent_panel.history_requested.connect(self._on_history_requested)
        self.sub_agent_panel.new_conversation_requested.connect(self._on_new_conversation_requested)

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
        # Forward selection context to both main and sub-agent panels
        self.main_agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)
        self.sub_agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)

    def _on_file_selected(self, file_path: Path) -> None:
        """Handle file selection from file tree.

        Args:
            file_path: Selected file path.
        """
        # Load file in preview
        self.preview.load_file(file_path)
        # Set file-only context on both panels (no selection yet)
        rel_path = self._relative_path(file_path)
        self.main_agent_panel.set_opened_file(rel_path)
        self.sub_agent_panel.set_opened_file(rel_path)
        logger.debug("File selected: {}", file_path)

    def _relative_path(self, file_path: Path) -> str:
        """Get relative path from workspace.

        Args:
            file_path: Absolute file path.

        Returns:
            Relative path as string.
        """
        try:
            return file_path.relative_to(self.workspace).as_posix()
        except ValueError:
            return file_path.as_posix()

    def _load_conversations(self) -> None:
        """Load previous conversations from disk into agent panels."""
        for agent_type in self._conv_store.get_agent_types_with_history():
            records = self._conv_store.load_messages(agent_type)
            if not records:
                continue

            panel = self._get_panel_for_agent(agent_type)
            for rec in records:
                role = rec.get("role", "")
                content = rec.get("content", "")
                if role == "user":
                    panel.add_message("user", content)
                elif role == "agent":
                    panel.add_message("agent", content)
                elif role == "tool_call":
                    panel.add_tool_call(content, rec.get("arguments", {}))
                elif role == "tool_result":
                    panel.add_tool_result(content, rec.get("result"), rec.get("error"))
                elif role == "error":
                    panel.add_error(rec.get("source", ""), content)

            n = len(records)
            logger.info("Loaded {} messages for agent {}", n, agent_type)

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
        self._conv_store.append_message("main", "user", content)
        self._submit_coroutine(self.backend.send_user_message(content, "main"))

    def _on_sub_agent_message(self, content: str) -> None:
        """Handle sub-agent message send."""
        agent_type = self.sub_agent_panel.agent_type
        self._conv_store.append_message(agent_type, "user", content)
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
            UserMessage,
        )

        if isinstance(message, AgentResponse):
            self._handle_agent_response(message)
        elif isinstance(message, UserMessage):
            self._handle_user_message(message)
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
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        panel.add_message("agent", message.content, streaming=message.streaming)
        # Only store in conversation history when stream is complete
        if not message.streaming or message.content == "":
            self._conv_store.append_message(agent_str, "agent", message.content)

    def _handle_user_message(self, message: UserMessage) -> None:
        """Handle user message (including coordination from main agent).

        Coordination messages (source="main_agent") are displayed in both
        the main agent panel and the target sub-agent panel.
        """
        agent_str = str(message.agent_type)
        is_coordination = message.source == "main_agent"

        # Display in the target agent's panel
        target_panel = self._get_panel_for_agent(agent_str)
        target_panel.add_message(
            "user",
            message.content,
            source=message.source,
            coordination=is_coordination,
        )

        # For coordination messages, also display in main agent panel
        if is_coordination:
            self.main_agent_panel.add_message(
                "user",
                f"[发送给 {self._get_agent_display_name(agent_str)}] {message.content}",
                source="main_agent",
                coordination=True,
            )

        # Store in conversation with source
        self._conv_store.append_message(
            agent_str,
            "user",
            message.content,
            extra={"source": message.source},
        )

    def _get_agent_display_name(self, agent_type: str) -> str:
        """Get display name for agent type."""
        names = {
            "data_analysis": "数据分析 Agent",
            "plotting": "图像绘制 Agent",
            "theory": "理论推导 Agent",
            "report": "报告撰写 Agent",
        }
        return names.get(agent_type, agent_type)

    def _handle_tool_call(self, message: ToolCall) -> None:
        """Handle tool call."""
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        panel.add_tool_call(message.tool_name, message.arguments)
        self._conv_store.append_tool_call(agent_str, message.tool_name, message.arguments)

    def _handle_tool_result(self, message: ToolResult) -> None:
        """Handle tool result."""
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        result_str = str(message.result) if message.result else None
        panel.add_tool_result(message.tool_name, message.result, message.error)
        self._conv_store.append_tool_result(agent_str, message.tool_name, result_str, message.error)

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

    # ---- Conversation History ----

    def _on_history_requested(self) -> None:
        """Show conversation history dialog."""
        sessions = self._conv_store.get_sessions()
        current_id = self._conv_store.get_current_session_id()

        dialog = ConversationHistoryDialog(sessions, current_id, parent=self)
        dialog.session_selected.connect(self._on_session_selected)
        dialog.new_conversation_requested.connect(self._on_new_conversation_requested)
        dialog.delete_session_requested.connect(self._on_delete_session)
        dialog.rename_session_requested.connect(self._on_rename_session)

        dialog.exec()

    def _on_new_conversation_requested(self) -> None:
        """Create a new conversation session and clear the UI."""
        self._conv_store.new_session()
        self._clear_all_panels()
        logger.info("New conversation session created: {}", self._conv_store.get_current_session_id())

    def _on_session_selected(self, session_id: str) -> None:
        """Switch to a different conversation session."""
        if self._conv_store.switch_session(session_id):
            self._clear_all_panels()
            self._load_conversations()
            logger.info("Switched to session: {}", session_id)

    def _on_delete_session(self, session_id: str) -> None:
        """Delete a conversation session."""
        self._conv_store.delete_session(session_id)
        # Reload the current session (might have changed)
        self._clear_all_panels()
        self._load_conversations()
        logger.info("Deleted session: {}", session_id)

    def _on_rename_session(self, session_id: str, new_name: str) -> None:
        """Rename a conversation session."""
        self._conv_store.rename_session(session_id, new_name)
        logger.info("Renamed session {} to {}", session_id, new_name)

    def _clear_all_panels(self) -> None:
        """Clear messages from all agent panels."""
        self.main_agent_panel._messages_area.clear()
        self.sub_agent_panel._messages_area.clear()

    def _subscribe_to_debug_messages(self) -> None:
        """Subscribe agent panels to ApiDebugMessage via MessageBus."""
        # Subscribe both main and sub-agent panels to debug messages
        self.main_agent_panel.subscribe_to_debug_messages(self.backend.bus)
        self.sub_agent_panel.subscribe_to_debug_messages(self.backend.bus)
