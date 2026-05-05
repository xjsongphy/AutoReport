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
    AgentFeedback,
    AgentResponse,
    Checkpoint,
    Error,
    Message,
    StatusChange,
    ToolCall,
    ToolResult,
    UserMessage,
)
from .scale import dpi_scale
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
        # No longer auto-load history — each session starts fresh

        self._message_signal.connect(self._dispatch_backend_message)
        self.backend.subscribe_to_messages(self._on_bus_message)
        self._subscribe_to_debug_messages()

        logger.info("Main window initialized for workspace: {}", self.workspace)

    def _apply_theme(self) -> None:
        """Apply theme matching VS Code Copilot Chat color variables."""
        from PyQt6.QtWidgets import QApplication

        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark
        s = dpi_scale()

        # Helper: scale pixel value for DPI
        def px(v: int) -> str:
            return f"{round(v * s)}px"

        if dark:
            c = {
                # VSCode Dark Modern: only 2 bg colors for large panels
                # #1F1F1F = content area  |  #181818 = chrome (sidebar/file tree)
                "bg": "#1f1f1f",
                "surface": "#181818",
                # code block / small elevated card
                "card": "#252526",
                # VSCode Dark Modern: subtle borders
                "border": "#2b2b2b",
                # --vscode-foreground
                "fg": "#cccccc",
                # --vscode-descriptionForeground
                "muted": "#737373",
                # --vscode-focusBorder
                "focus": "#0078d4",
                # --vscode-input-background
                "input_bg": "#313131",
                "input_border": "#3c3c3c",
                # --vscode-chat-requestBubbleBackground
                "bubble_bg": "#2a2a2a",
                "bubble_hover": "#333333",
                # --vscode-button-background
                "send_bg": "#0078d4",
                "send_hover": "#026ec1",
                # subtle scrollbar (VSCode: transparent track, barely visible handle)
                "scrollbar": "#ffffff1a",
                "scrollbar_hover": "#ffffff33",
                # --vscode-toolbar-hoverBackground
                "hover": "#2a2d2e",
                "selection": "#264f78",
                "status_think": "#0078d4",
                "status_tool": "#cca700",
                "status_error": "#f44747",
                "status_debug": "#b180d7",
                "status_idle": "#737373",
                "header_action": "#737373",
                "header_action_hover": "#cccccc",
                "context_bg": "#1f1f1f",
                "context_border": "#2b2b2b",
                "spinner_fg": "#0078d4",
                # --vscode-chat-avatarBackground
                "avatar_bg": "#3c3c3c",
                "avatar_fg": "#cccccc",
                # --vscode-textPreformat-foreground
                "tool_fg": "#cccccc",
                "tool_border": "#2b2b2b",
                "tool_detail": "#737373",
            }
        else:
            c = {
                "bg": "#ffffff",
                "surface": "#f3f3f3",
                "card": "#f5f5f5",
                "border": "#e0e0e0",
                "fg": "#616161",
                "muted": "#9e9e9e",
                "focus": "#0090ff",
                "input_bg": "#ffffff",
                "input_border": "#e0e0e0",
                "bubble_bg": "#f0f0f0",
                "bubble_hover": "#e8e8e8",
                "send_bg": "#0078d4",
                "send_hover": "#006cbe",
                "scrollbar": "#c1c1c1",
                "scrollbar_hover": "#a8a8a8",
                "hover": "#e8e8e8",
                "selection": "#0090ff",
                "status_think": "#0090ff",
                "status_tool": "#bf8900",
                "status_error": "#d32f2f",
                "status_debug": "#7b1fa2",
                "status_idle": "#9e9e9e",
                "header_action": "#9e9e9e",
                "header_action_hover": "#616161",
                "context_bg": "#f3f3f3",
                "context_border": "#e0e0e0",
                "spinner_fg": "#0090ff",
                "avatar_bg": "#e0e0e0",
                "avatar_fg": "#616161",
                "tool_fg": "#616161",
                "tool_border": "#e0e0e0",
                "tool_detail": "#9e9e9e",
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
                font-size: {px(13)};
            }}
            QSplitter::handle {{
                background-color: {c["border"]};
            }}
            QSplitter::handle:horizontal {{
                width: {px(1)};
            }}
            QSplitter::handle:vertical {{
                height: {px(1)};
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: {px(8)};
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c["scrollbar"]};
                min-height: {px(30)};
                border-radius: {px(4)};
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {c["scrollbar_hover"]};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background-color: transparent;
                height: {px(8)};
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {c["scrollbar"]};
                min-width: {px(30)};
                border-radius: {px(4)};
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
            QToolTip {{
                background-color: {c["surface"]};
                color: {c["fg"]};
                border: 1px solid {c["border"]};
                padding: {px(3)} {px(7)};
                font-size: {px(12)};
                border-radius: {px(4)};
            }}

            /* ---- Panel Header ---- */
            #panelHeader {{
                background-color: {c["bg"]};
                border-bottom: 1px solid {c["border"]};
            }}
            #panelTitle {{
                font-size: {px(13)};
                font-weight: 600;
                color: {c["fg"]};
            }}
            #panelStatus {{
                font-size: {px(11)};
                color: {c["status_idle"]};
            }}
            #headerAction {{
                background-color: transparent;
                color: {c["header_action"]};
                border: none;
                border-radius: {px(4)};
                font-size: {px(13)};
            }}
            #headerAction:hover {{
                background-color: {c["hover"]};
                color: {c["header_action_hover"]};
            }}
            #debugBtn {{
                background-color: transparent;
                color: {c["muted"]};
                border: 1px solid {c["border"]};
                border-radius: {px(4)};
                padding: {px(2)} {px(10)};
                font-size: {px(11)};
            }}
            #debugBtn:hover {{
                background-color: {c["hover"]};
            }}
            #debugBtn:checked {{
                background-color: {c["status_error"]};
                color: #ffffff;
                border-color: transparent;
            }}

            /* ---- Input Container (with working border space) ---- */
            #inputContainer {{
                background-color: {c["bg"]};
            }}

            /* ---- Input Bar ---- */
            #inputBar {{
                background-color: transparent;
            }}

            /* ---- Secondary Toolbar ---- */
            #secondaryToolbar {{
                background-color: {c["bg"]};
            }}
            #secondaryBtn {{
                background-color: transparent;
                color: {c["muted"]};
                border: none;
                border-radius: {px(4)};
                font-size: {px(14)};
            }}
            #secondaryBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}
            #secondaryStatus {{
                font-size: {px(11)};
                color: {c["muted"]};
            }}
            /* VS Code send button */
            #sendBtn {{
                background-color: {c["send_bg"]};
                color: #ffffff;
                border: none;
                border-radius: {px(13)};
                font-size: {px(14)};
                font-weight: 700;
                padding: 0;
                min-width: {px(26)};
                min-height: {px(26)};
                max-width: {px(26)};
                max-height: {px(26)};
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
                font-size: {px(11)};
                color: {c["muted"]};
                font-family: "SF Mono", "Consolas", monospace;
            }}
            #contextEye {{
                background-color: transparent;
                border: none;
                border-radius: {px(4)};
                font-size: {px(12)};
            }}
            #contextEye:hover {{
                background-color: {c["hover"]};
            }}

            /* ---- User Message — right-aligned bubble ---- */
            #userMessageRow {{
                background-color: transparent;
            }}
            #userMessageBubble {{
                background-color: {c["bubble_bg"]};
                border-radius: {px(12)};
                max-width: 95%;
            }}
            #userMessageBubble:hover {{
                background-color: {c["bubble_hover"]};
            }}
            #userMessageText {{
                color: {c["fg"]};
                font-size: {px(13)};
                line-height: 1.5;
            }}

            /* ---- Agent Message — flat with avatar ---- */
            #agentHeader {{
                background-color: transparent;
            }}
            #agentAvatar {{
                background-color: {c["avatar_bg"]};
                color: {c["avatar_fg"]};
                border-radius: {px(12)};
                font-size: {px(12)};
            }}
            #agentUsername {{
                font-size: {px(13)};
                font-weight: 600;
                color: {c["fg"]};
            }}
            #agentMessageRow {{
                background-color: transparent;
            }}
            #agentMessageText {{
                color: {c["fg"]};
                font-size: {px(13)};
                line-height: 1.5;
                background-color: transparent;
            }}
            #msgCoordination {{
                font-size: {px(11)};
                color: {c["muted"]};
                font-style: italic;
                padding-left: 0;
                margin-bottom: {px(4)};
            }}

            /* ---- Message Footer (hover toolbar) ---- */
            #msgFooter {{
                background-color: transparent;
                padding-top: {px(4)};
            }}
            #copyBtn {{
                background-color: transparent;
                color: {c["muted"]};
                border: 1px solid {c["border"]};
                border-radius: {px(4)};
                padding: {px(1)} {px(5)};
                font-size: {px(11)};
            }}
            #copyBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}

            /* ---- Code Block ---- */
            #codeBlockCard {{
                background-color: {c["card"]};
                border: 1px solid {c["border"]};
                border-radius: {px(6)};
                margin: {px(4)} 0;
            }}
            #codeBlockHeader {{
                background-color: transparent;
                border-bottom: 1px solid {c["border"]};
            }}
            #codeBlockLang {{
                font-size: {px(11)};
                color: {c["muted"]};
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
            }}
            #codeBlockCopyBtn {{
                background-color: transparent;
                color: transparent;
                border: none;
                border-radius: {px(4)};
                font-size: {px(12)};
                padding: {px(1)} {px(4)};
            }}
            #codeBlockCard:hover #codeBlockCopyBtn {{
                color: {c["muted"]};
            }}
            #codeBlockCopyBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]} !important;
            }}
            #codeBlockContent {{
                color: {c["fg"]};
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
                font-size: {px(12)};
            }}

            /* ---- Tool Call Group ---- */
            #toolCallHeader {{
                background-color: transparent;
                border: none;
                color: {c["tool_fg"]};
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
                font-size: {px(12)};
                text-align: left;
                padding: 0;
                border-radius: {px(4)};
            }}
            #toolCallHeader:hover {{
                background-color: {c["hover"]};
                color: {c["focus"]};
            }}
            #toolCallDetail {{
                color: {c["tool_detail"]};
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
                font-size: {px(11)};
                padding: {px(2)} 0;
            }}

            /* ---- Status Indicator ---- */
            #statusSpinner {{
                color: {c["spinner_fg"]};
                font-size: {px(13)};
            }}
            #statusHeader {{
                color: {c["muted"]};
                font-size: 12px;
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

        # Right: Agent panels side-by-side (Sub Agent | Main Agent)
        self.sub_agent_panel = AgentPanel("sub", "Sub Agent", self.workspace)
        self.sub_agent_panel.setMinimumWidth(280)
        main_splitter.addWidget(self.sub_agent_panel)

        self.main_agent_panel = AgentPanel("main", "Main Agent", self.workspace)
        self.main_agent_panel.setMinimumWidth(280)
        main_splitter.addWidget(self.main_agent_panel)

        main_splitter.setSizes([250, 500, 350, 350])

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

        self.main_agent_panel.conversation_cleared.connect(
            lambda: self._on_conversation_cleared("main"))
        self.sub_agent_panel.conversation_cleared.connect(
            lambda: self._on_conversation_cleared(self.sub_agent_panel.agent_type))

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

        if agent_type != self.sub_agent_panel.agent_type:
            self.sub_agent_panel._messages_area.clear()
            self.sub_agent_panel.set_agent_type(agent_type)
            if agent_type != "sub":
                self._load_conversations_for_agent(agent_type, self.sub_agent_panel)

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
        # Only restore main agent history. Sub-agents start fresh each session.
        agent_type = "main"
        records = self._conv_store.load_messages(agent_type)
        if records:
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
        if agent_type == "sub":
            self.main_agent_panel.add_message("agent", "请先在左侧文件树选择目录以激活对应的子 Agent。")
            return
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
            TaskUpdateMessage,
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
        elif isinstance(message, TaskUpdateMessage):
            self._handle_task_update_msg(message)
        elif isinstance(message, AgentFeedback):
            self._handle_agent_feedback(message)

    def _handle_agent_response(self, message: AgentResponse) -> None:
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        # Empty non-streaming message = completion signal for streaming
        if not message.streaming and not message.content:
            rows = panel._messages_area.get_message_rows()
            if rows and rows[-1]._role == "agent":
                rows[-1].mark_complete()
            return
        # Non-streaming with content — check if streaming already delivered it
        if not message.streaming and message.content:
            rows = panel._messages_area.get_message_rows()
            if (rows
                    and rows[-1]._role == "agent"
                    and rows[-1]._content
                    and not rows[-1]._complete):
                rows[-1].mark_complete()
                self._conv_store.append_message(agent_str, "agent", rows[-1]._content)
                return
        panel.add_message("agent", message.content, streaming=message.streaming)
        if not message.streaming:
            self._conv_store.append_message(agent_str, "agent", message.content)
            # Mark newly added message as complete (copy button visible)
            rows = panel._messages_area.get_message_rows()
            if rows and rows[-1]._role == "agent":
                rows[-1].mark_complete()

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

    def _handle_agent_feedback(self, message: AgentFeedback) -> None:
        """Handle AgentFeedback — show sub-agent issue report in main panel."""
        from enum import Enum
        agent_str = message.agent_type.value if isinstance(message.agent_type, Enum) else str(message.agent_type)
        issue_type = message.feedback_type or "issue"
        self.main_agent_panel.add_message(
            "agent",
            f"[{agent_str} reported {issue_type}] {message.content}",
            source=agent_str,
        )

    def _handle_checkpoint(self, message: Checkpoint) -> None:
        agent_str = str(message.agent_type) if hasattr(message, "agent_type") else "main"
        panel = self._get_panel_for_agent(agent_str)
        panel.add_checkpoint(message.checkpoint_id, message.description)

    def _handle_task_update_msg(self, message) -> None:
        """Handle TaskUpdateMessage — display task notification in relevant panels."""
        from enum import Enum

        src = message.source_agent
        src_str = src.value if isinstance(src, Enum) else str(src)
        tgt = message.target_agent
        tgt_str = tgt.value if isinstance(tgt, Enum) else str(tgt)

        src_panel = self._get_panel_for_agent(src_str)
        tgt_panel = self._get_panel_for_agent(tgt_str)
        for panel in {src_panel, tgt_panel}:
            panel.handle_task_update(
                task_id=message.task_id,
                action=message.action,
                source=src_str,
                target=tgt_str,
                description=message.description,
            )

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

    def _on_conversation_cleared(self, agent_type: str) -> None:
        self._conv_store.new_session(agent_type=agent_type)
        logger.info("/clear for {}: new session {}", agent_type,
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
