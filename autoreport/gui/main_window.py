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
from .widgets.file_tree import FileTreeWidget
from .widgets.preview import PreviewWidget


class MainWindow(QMainWindow):
    """Main application window.

    Implements the GUIAPI protocol via duck-typing (cannot use multiple
    inheritance with QMainWindow because of metaclass conflict).
    """

    _message_signal = pyqtSignal(object)

    def __init__(self, backend: BackendAPI, workspace: Path):
        super().__init__()
        self.backend = backend
        self.workspace = Path(workspace).resolve()
        self._async_loop: asyncio.AbstractEventLoop | None = None

        self.setWindowTitle("AutoReport")
        self.resize(1400, 900)

        self._conv_store = ConversationStore(workspace)

        self._apply_theme()
        self._setup_ui()
        self._load_conversations()

        self._message_signal.connect(self._dispatch_backend_message)
        self.backend.subscribe_to_messages(self._on_bus_message)
        self._subscribe_to_debug_messages()

        logger.info("Main window initialized for workspace: {}", self.workspace)

    def _apply_theme(self) -> None:
        """Apply Codex CLI / GitHub-inspired theme."""
        from PyQt6.QtWidgets import QApplication

        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        if dark:
            c = {
                "bg": "#0d1117",
                "surface": "#161b22",
                "border": "#30363d",
                "fg": "#e6edf3",
                "muted": "#8b949e",
                "focus": "#58a6ff",
                "input_bg": "#0d1117",
                "input_border": "#30363d",
                "badge_bg": "#1c2333",
                "badge_fg": "#e6edf3",
                "send_bg": "#238636",
                "send_hover": "#2ea043",
                "scrollbar": "#30363d",
                "scrollbar_hover": "#484f58",
                "hover": "#1c2333",
                "selection": "#264f78",
                "status_think": "#58a6ff",
                "status_tool": "#d29922",
                "status_error": "#f85149",
                "status_debug": "#bc8cff",
                "status_idle": "#8b949e",
                "header_action": "#8b949e",
                "header_action_hover": "#e6edf3",
                "context_bg": "#161b22",
                "context_border": "#30363d",
                "spinner_fg": "#58a6ff",
                "user_prompt": "#8b949e",
                "agent_bullet": "#484f58",
                "tool_bg": "#161b22",
                "tool_fg": "#e6edf3",
                "tool_border": "#30363d",
                "tool_detail": "#8b949e",
            }
        else:
            c = {
                "bg": "#ffffff",
                "surface": "#f6f8fa",
                "border": "#d0d7de",
                "fg": "#1f2328",
                "muted": "#656d76",
                "focus": "#0969da",
                "input_bg": "#ffffff",
                "input_border": "#d0d7de",
                "badge_bg": "#f6f8fa",
                "badge_fg": "#1f2328",
                "send_bg": "#1f883d",
                "send_hover": "#1a7f37",
                "scrollbar": "#d0d7de",
                "scrollbar_hover": "#afb8c1",
                "hover": "#f6f8fa",
                "selection": "#0969da",
                "status_think": "#0969da",
                "status_tool": "#9a6700",
                "status_error": "#cf222e",
                "status_debug": "#8250df",
                "status_idle": "#656d76",
                "header_action": "#656d76",
                "header_action_hover": "#1f2328",
                "context_bg": "#f6f8fa",
                "context_border": "#d0d7de",
                "spinner_fg": "#0969da",
                "user_prompt": "#656d76",
                "agent_bullet": "#afb8c1",
                "tool_bg": "#f6f8fa",
                "tool_fg": "#1f2328",
                "tool_border": "#d0d7de",
                "tool_detail": "#656d76",
            }

        self._theme_colors = c

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {c["bg"]};
                color: {c["fg"]};
            }}
            QWidget {{
                color: {c["fg"]};
                font-family: "Segoe UI", "SF Pro", -apple-system, sans-serif;
                font-size: 13px;
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
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c["scrollbar"]};
                min-height: 30px;
                border-radius: 4px;
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
                height: 8px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {c["scrollbar"]};
                min-width: 30px;
                border-radius: 4px;
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QToolTip {{
                background-color: {c["surface"]};
                color: {c["fg"]};
                border: 1px solid {c["border"]};
                padding: 6px 8px;
                font-size: 12px;
                border-radius: 6px;
            }}

            /* ---- Panel Header (Codex-style) ---- */
            #panelHeader {{
                background-color: {c["bg"]};
                border-bottom: 1px solid {c["border"]};
            }}
            #panelTitle {{
                font-size: 12px;
                font-weight: 600;
                color: {c["fg"]};
                letter-spacing: 0.02em;
            }}
            #panelStatus {{
                font-size: 11px;
                color: {c["status_idle"]};
            }}
            #headerAction {{
                background-color: transparent;
                color: {c["header_action"]};
                border: none;
                border-radius: 6px;
                font-size: 13px;
            }}
            #headerAction:hover {{
                background-color: {c["hover"]};
                color: {c["header_action_hover"]};
            }}
            #debugBtn {{
                background-color: transparent;
                color: {c["muted"]};
                border: 1px solid {c["border"]};
                border-radius: 6px;
                padding: 2px 10px;
                font-size: 11px;
            }}
            #debugBtn:hover {{
                background-color: {c["hover"]};
            }}
            #debugBtn:checked {{
                background-color: {c["status_error"]};
                color: #ffffff;
                border-color: transparent;
            }}

            /* ---- Input Bar ---- */
            #inputBar {{
                background-color: {c["bg"]};
                border-top: 1px solid {c["border"]};
            }}
            #sendBtn {{
                background-color: {c["send_bg"]};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 700;
            }}
            #sendBtn:hover {{
                background-color: {c["send_hover"]};
            }}

            /* ---- Context Bar ---- */
            #contextBar {{
                background-color: {c["context_bg"]};
                border-top: 1px solid {c["context_border"]};
            }}
            #contextLabel {{
                font-size: 11px;
                color: {c["muted"]};
                font-family: "SF Mono", "Consolas", monospace;
            }}
            #contextEye {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }}
            #contextEye:hover {{
                background-color: {c["hover"]};
            }}

            /* ---- Message Cells (Codex flat timeline) ---- */
            #userMessageBubble {{
                background-color: {c["badge_bg"]};
                border-radius: 8px;
            }}
            #userPrompt {{
                color: {c["user_prompt"]};
                font-weight: 700;
                font-size: 14px;
            }}
            #userMessageText {{
                color: {c["badge_fg"]};
                font-size: 13px;
                line-height: 1.5;
            }}
            #agentBullet {{
                color: {c["agent_bullet"]};
                font-size: 14px;
            }}
            #agentMessageText {{
                color: {c["fg"]};
                font-size: 13px;
                background-color: transparent;
                line-height: 1.5;
            }}
            #msgCoordination {{
                font-size: 11px;
                color: {c["muted"]};
                font-style: italic;
                margin-left: 30px;
            }}

            /* ---- Tool Call Group ---- */
            #toolCallHeader {{
                background-color: transparent;
                border: none;
                color: {c["tool_fg"]};
                font-family: "SF Mono", "Consolas", "Monaco", monospace;
                font-size: 12px;
                text-align: left;
                padding: 0;
                border-radius: 4px;
            }}
            #toolCallHeader:hover {{
                background-color: {c["hover"]};
                color: {c["focus"]};
            }}
            #toolCallDetail {{
                color: {c["tool_detail"]};
                font-family: "SF Mono", "Consolas", "Monaco", monospace;
                font-size: 11px;
                padding: 2px 0;
            }}

            /* ---- Status Indicator ---- */
            #statusSpinner {{
                color: {c["spinner_fg"]};
                font-size: 13px;
            }}
            #statusHeader {{
                color: {c["fg"]};
                font-size: 12px;
                font-weight: 500;
            }}
            #statusElapsed {{
                color: {c["muted"]};
                font-size: 11px;
            }}
            #statusHint {{
                color: {c["muted"]};
                font-size: 11px;
            }}
        """)

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter)

        # Left: File tree
        self.file_tree = FileTreeWidget(self.workspace)
        self.file_tree.setMinimumWidth(200)
        self.file_tree.setMaximumWidth(400)
        self.file_tree.directory_selected.connect(self._on_directory_selected)
        self.file_tree.file_selected.connect(self._on_file_selected)
        main_splitter.addWidget(self.file_tree)

        # Center: Preview
        self.preview = PreviewWidget(self.workspace)
        self.preview.setMinimumWidth(400)
        main_splitter.addWidget(self.preview)

        # Right: Agent panels
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(right_splitter)

        self.main_agent_panel = AgentPanel("main", "Main Agent", self.workspace)
        self.main_agent_panel.setMinimumHeight(300)
        right_splitter.addWidget(self.main_agent_panel)

        self.sub_agent_panel = AgentPanel("sub", "Sub Agent", self.workspace)
        self.sub_agent_panel.setMinimumHeight(300)
        right_splitter.addWidget(self.sub_agent_panel)

        main_splitter.setSizes([250, 500, 650])
        right_splitter.setSizes([300, 300])

        # Connect signals
        self.main_agent_panel.message_sent.connect(self._on_main_agent_message)
        self.sub_agent_panel.message_sent.connect(self._on_sub_agent_message)
        self.sub_agent_panel.debug_mode_toggled.connect(self._on_debug_mode_toggled)

        self.main_agent_panel.history_requested.connect(lambda: self._on_history_requested("main"))
        self.main_agent_panel.new_conversation_requested.connect(lambda: self._on_new_conversation_requested("main"))
        self.main_agent_panel.session_selected_from_dropdown.connect(lambda sid: self._on_session_selected(sid, "main"))
        self.main_agent_panel.delete_session_requested.connect(self._on_delete_session)
        self.main_agent_panel.rename_session_requested.connect(self._on_rename_session)
        self.sub_agent_panel.history_requested.connect(lambda: self._on_history_requested(self.sub_agent_panel.agent_type))
        self.sub_agent_panel.new_conversation_requested.connect(lambda: self._on_new_conversation_requested(self.sub_agent_panel.agent_type))
        self.sub_agent_panel.session_selected_from_dropdown.connect(lambda sid: self._on_session_selected(sid, self.sub_agent_panel.agent_type))
        self.sub_agent_panel.delete_session_requested.connect(self._on_delete_session)
        self.sub_agent_panel.rename_session_requested.connect(self._on_rename_session)

        self.preview.selection_changed.connect(self._on_preview_selection_changed)
        self.main_agent_panel.hide_debug_button(hide=True)

    def _on_directory_selected(self, directory: str) -> None:
        self.preview.set_directory(directory)
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
        self.main_agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)
        self.sub_agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)

    def _on_file_selected(self, file_path: Path) -> None:
        self.preview.load_file(file_path)
        rel_path = self._relative_path(file_path)
        self.main_agent_panel.set_opened_file(rel_path)
        self.sub_agent_panel.set_opened_file(rel_path)
        logger.debug("File selected: {}", file_path)

    def _relative_path(self, file_path: Path) -> str:
        try:
            return file_path.relative_to(self.workspace).as_posix()
        except ValueError:
            return file_path.as_posix()

    def _load_conversations(self) -> None:
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
            logger.info("Loaded {} messages for agent {}", len(records), agent_type)

    def _load_conversations_for_agent(self, agent_type: str, panel: AgentPanel) -> None:
        records = self._conv_store.load_messages(agent_type)
        if not records:
            return
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
        logger.info("Loaded {} messages for agent {}", len(records), agent_type)

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._async_loop = loop

    def _submit_coroutine(self, coro):
        if self._async_loop is None:
            logger.warning("No async loop set, cannot dispatch coroutine")
            return
        asyncio.run_coroutine_threadsafe(coro, self._async_loop)

    def _on_main_agent_message(self, content: str) -> None:
        self._conv_store.append_message("main", "user", content)
        self._submit_coroutine(self.backend.send_user_message(content, "main"))

    def _on_sub_agent_message(self, content: str) -> None:
        agent_type = self.sub_agent_panel.agent_type
        self._conv_store.append_message(agent_type, "user", content)
        self._submit_coroutine(self.backend.send_user_message(content, agent_type))

    def _on_debug_mode_toggled(self, enabled: bool) -> None:
        agent_type = self.sub_agent_panel.agent_type
        self.backend.set_agent_debug_mode(agent_type, enabled)

    def _on_bus_message(self, message: Message) -> None:
        self._message_signal.emit(message)

    def _dispatch_backend_message(self, message: Message) -> None:
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
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        panel.add_message("agent", message.content, streaming=message.streaming)
        if not message.streaming or message.content == "":
            self._conv_store.append_message(agent_str, "agent", message.content)

    def _handle_user_message(self, message: UserMessage) -> None:
        agent_str = str(message.agent_type)
        is_coordination = message.source == "main_agent"

        target_panel = self._get_panel_for_agent(agent_str)
        target_panel.add_message(
            "user",
            message.content,
            source=message.source,
            coordination=is_coordination,
        )

        if is_coordination:
            self.main_agent_panel.add_message(
                "user",
                f"[→ {self._get_agent_display_name(agent_str)}] {message.content}",
                source="main_agent",
                coordination=True,
            )

        self._conv_store.append_message(
            agent_str,
            "user",
            message.content,
            extra={"source": message.source},
        )

    def _get_agent_display_name(self, agent_type: str) -> str:
        names = {
            "data_analysis": "Data Analysis",
            "plotting": "Plotting",
            "theory": "Theory",
            "report": "Report",
        }
        return names.get(agent_type, agent_type)

    def _handle_tool_call(self, message: ToolCall) -> None:
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        panel.add_tool_call(message.tool_name, message.arguments)
        self._conv_store.append_tool_call(agent_str, message.tool_name, message.arguments)

    def _handle_tool_result(self, message: ToolResult) -> None:
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        result_str = str(message.result) if message.result else None
        panel.add_tool_result(message.tool_name, message.result, message.error)
        self._conv_store.append_tool_result(agent_str, message.tool_name, result_str, message.error)

    def _handle_status_change(self, message: StatusChange) -> None:
        panel = self._get_panel_for_agent(message.agent_type)
        panel.set_status(message.status, message.extra)

    def _handle_error(self, message: Error) -> None:
        self.main_agent_panel.add_error(message.source, message.message)

    def _handle_checkpoint(self, message: Checkpoint) -> None:
        self.main_agent_panel.add_checkpoint(message.checkpoint_id, message.description)

    def _get_panel_for_agent(self, agent_type: str) -> AgentPanel:
        if agent_type == "main":
            return self.main_agent_panel
        return self.sub_agent_panel

    # ---- Conversation History ----

    def _on_history_requested(self, agent_type: str) -> None:
        sessions = self._conv_store.get_sessions()
        current_id = self._conv_store.get_current_session_id(agent_type)
        panel = self._get_panel_for_agent(agent_type)
        panel.show_history_dropdown(sessions, current_id)

    def _on_new_conversation_requested(self, agent_type: str) -> None:
        self._conv_store.new_session(agent_type=agent_type)
        panel = self._get_panel_for_agent(agent_type)
        panel._messages_area.clear()
        logger.info("New conversation session for {}: {}", agent_type,
                     self._conv_store.get_current_session_id(agent_type))

    def _on_session_selected(self, session_id: str, agent_type: str) -> None:
        if self._conv_store.switch_session(session_id, agent_type):
            panel = self._get_panel_for_agent(agent_type)
            panel._messages_area.clear()
            self._load_conversations_for_agent(agent_type, panel)
            logger.info("Switched {} to session: {}", agent_type, session_id)

    def _on_delete_session(self, session_id: str) -> None:
        self._conv_store.delete_session(session_id)
        self._clear_all_panels()
        self._load_conversations()
        logger.info("Deleted session: {}", session_id)

    def _on_rename_session(self, session_id: str, new_name: str) -> None:
        self._conv_store.rename_session(session_id, new_name)
        logger.info("Renamed session {} to {}", session_id, new_name)

    def _clear_all_panels(self) -> None:
        self.main_agent_panel._messages_area.clear()
        self.sub_agent_panel._messages_area.clear()

    def _subscribe_to_debug_messages(self) -> None:
        self.main_agent_panel.subscribe_to_debug_messages(self.backend.bus)
        self.sub_agent_panel.subscribe_to_debug_messages(self.backend.bus)
