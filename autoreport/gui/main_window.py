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
    QueueUpdateMessage,
    StatusChange,
    ToolCall,
    ToolResult,
    UserMessage,
)
from ..utils.agent_labels import get_agent_badge, get_agent_title
from ..utils.logging_config import ui_logger
from .scale import dpi_scale
from .theme import get_theme_colors
from .widgets.agent_panel import AgentPanel
from .widgets.file_tree import FileTreeWidget
from .widgets.preview import PreviewWidget
from .widgets.ui_utils import compact_tooltip_qss


class MainWindow(QMainWindow):
    """Main application window.

    Implements the GUIAPI protocol via duck-typing (cannot use multiple
    inheritance with QMainWindow because of metaclass conflict).
    """

    _message_signal = pyqtSignal(object)

    def __init__(
        self,
        backend: BackendAPI,
        workspace: Path,
        debug_agents: list[str] | None = None,
    ):
        super().__init__()
        self.backend = backend
        self.workspace = Path(workspace).resolve()
        self._async_loop: asyncio.AbstractEventLoop | None = None
        self._debug_agents = {str(a) for a in (debug_agents or [])}

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
        s = dpi_scale()

        # Helper: scale pixel value for DPI
        def px(v: int) -> str:
            return f"{round(v * s)}px"

        # Get unified theme colors
        c = get_theme_colors()
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
            QScrollBar::handle:vertical:pressed {{
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
            QScrollBar::handle:horizontal:hover,
            QScrollBar::handle:horizontal:pressed {{
                background-color: {c["scrollbar_hover"]};
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
            {compact_tooltip_qss("QToolTip")}

            /* ---- Panel Header ---- */
            #panelHeader {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
                padding-right: 1px;
            }}
            /* Agent Panel background */
            AgentPanel {{
                background-color: {c["surface"]};
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
            #stopBtn {{
                background-color: {c["stop_bg"]};
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
            #stopBtn:hover {{
                background-color: {c["stop_hover"]};
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
            }}
            #userMessageBubble:hover {{
                background-color: {c["bubble_hover"]};
            }}
            #userMessageText {{
                color: {c["editor_fg"]};
                font-size: {px(13)};
                line-height: 1.5;
            }}
            #userMessageBubbleContainer {{
                background-color: transparent;
            }}
            #userMsgFooter {{
                background-color: transparent;
                padding-top: {px(2)};
                padding-right: {px(8)};
            }}
            #userEditBtn, #userCopyBtn {{
                background-color: transparent;
                color: {c["muted"]};
                border: none;
                border-radius: {px(4)};
                padding: 0;
                font-size: {px(15)};
            }}
            #userEditBtn:hover, #userCopyBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}
            #queuePreview {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
            }}
            #queueTitle {{
                font-size: {px(11)};
                color: {c["muted"]};
                font-weight: 600;
            }}
            #queueItems {{
                font-size: {px(12)};
                color: {c["fg"]};
                line-height: 1.4;
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
                color: {c["editor_fg"]};
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
                padding: 0;
                font-size: {px(15)};
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
                font-size: {px(15)};
                padding: 0;
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
                font-family: "Segoe UI", "SF Pro", -apple-system, sans-serif;
                font-size: {px(12)};
                font-weight: 500;
                text-align: left;
                padding: {px(2)} 0;
                border-radius: {px(4)};
            }}
            #toolCallHeader:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}
            #toolCallDetail {{
                color: {c["tool_detail"]};
                font-family: "Segoe UI", "SF Pro", -apple-system, sans-serif;
                font-size: {px(11)};
                padding: {px(1)} 0 {px(2)} {px(12)};
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
        main_splitter.setChildrenCollapsible(False)
        main_layout.addWidget(main_splitter)

        # Left: File tree
        self.file_tree = FileTreeWidget(self.workspace)
        # Don't override minimum width - let FileTreeWidget handle it
        self.file_tree.directory_selected.connect(self._on_directory_selected)
        self.file_tree.file_selected.connect(self._on_file_selected)
        main_splitter.addWidget(self.file_tree)

        # Center: Preview
        self.preview = PreviewWidget(self.workspace)
        self.preview.setMinimumWidth(300)
        main_splitter.addWidget(self.preview)

        # Right: Agent panels side-by-side (Sub Agent | Main Agent)
        self.sub_agent_panel = AgentPanel("sub", get_agent_title("sub"), self.workspace)
        main_splitter.addWidget(self.sub_agent_panel)

        self.main_agent_panel = AgentPanel("main", get_agent_title("main"), self.workspace)
        main_splitter.addWidget(self.main_agent_panel)

        for index in range(main_splitter.count()):
            main_splitter.setCollapsible(index, False)

        # Set stretch factors for proportional sizing
        # file_tree: 20%, preview: 35%, sub_agent: 22.5%, main_agent: 22.5%
        main_splitter.setStretchFactor(0, 20)   # file_tree
        main_splitter.setStretchFactor(1, 35)   # preview
        main_splitter.setStretchFactor(2, 23)   # sub_agent_panel
        main_splitter.setStretchFactor(3, 23)   # main_agent_panel

        # Store main_splitter for resize handling
        self._main_splitter = main_splitter
        self._apply_splitter_sizes()

        # Connect signals
        self.main_agent_panel.message_sent.connect(self._on_main_agent_message)
        self.sub_agent_panel.message_sent.connect(self._on_sub_agent_message)

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
        self.main_agent_panel.interrupt_requested.connect(lambda: self._on_interrupt("main"))
        self.sub_agent_panel.interrupt_requested.connect(lambda: self._on_interrupt(self.sub_agent_panel.agent_type))

        self.preview.selection_changed.connect(self._on_preview_selection_changed)
        self.main_agent_panel.set_agent_type("main")
        self.main_agent_panel.set_debug_mode("main" in self._debug_agents)
        self.sub_agent_panel.set_debug_mode(self.sub_agent_panel.agent_type in self._debug_agents)

        self.main_agent_panel.conversation_cleared.connect(
            lambda: self._on_conversation_cleared("main"))
        self.sub_agent_panel.conversation_cleared.connect(
            lambda: self._on_conversation_cleared(self.sub_agent_panel.agent_type))

    def _on_directory_selected(self, directory: str) -> None:
        ui_logger.debug("MainWindow: directory selected {}", directory)
        self.preview.set_directory(directory)
        agent_map = {
            "data": "data_analysis",
            "refs": "main",
            "theory": "theory",
            "code": "plotting",
            "tex": "report",
        }
        agent_type = agent_map.get(directory, "sub")

        # Clear file context when user switches directories by clicking a folder.
        # Skip if this was triggered by clicking a file (file_selected fires first).
        if not getattr(self, "_file_just_selected", False):
            self.main_agent_panel.clear_file_context()
            self.sub_agent_panel.clear_file_context()
        self._file_just_selected = False

        if agent_type != self.sub_agent_panel.agent_type:
            sizes = self._main_splitter.sizes() if hasattr(self, "_main_splitter") else None
            ui_logger.debug("MainWindow: switching sub-agent panel to {}", agent_type)
            self.sub_agent_panel._messages_area.clear()
            self.sub_agent_panel.set_agent_type(agent_type)
            self.sub_agent_panel.set_debug_mode(agent_type in self._debug_agents)
            if agent_type != "sub":
                self._load_conversations_for_agent(agent_type, self.sub_agent_panel)
            if sizes:
                self._main_splitter.setSizes(sizes)

    def _on_preview_selection_changed(self, file_path: str, selected_text: str, start_line: int, end_line: int) -> None:
        self.main_agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)
        self.sub_agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)

    def _on_file_selected(self, file_path: Path) -> None:
        ui_logger.debug("MainWindow: file selected {}", file_path.name)
        self._file_just_selected = True
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
                    panel.add_message(
                        "user",
                        content,
                        summary=rec.get("summary"),
                        detail=rec.get("detail"),
                        expandable=rec.get("expandable", True),
                    )
                elif role == "agent":
                    panel.add_message(
                        "agent",
                        content,
                        summary=rec.get("summary"),
                        detail=rec.get("detail"),
                        expandable=rec.get("expandable", True),
                    )
                elif role == "tool_call":
                    panel.add_tool_call(
                        content,
                        rec.get("arguments", {}),
                        summary=rec.get("summary"),
                        detail=rec.get("detail"),
                        expandable=rec.get("expandable", True),
                    )
                elif role == "tool_result":
                    panel.add_tool_result(
                        content,
                        rec.get("result"),
                        rec.get("error"),
                        summary=rec.get("summary"),
                        detail=rec.get("detail"),
                        expandable=rec.get("expandable"),
                    )
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
                panel.add_message(
                    "user",
                    content,
                    summary=rec.get("summary"),
                    detail=rec.get("detail"),
                    expandable=rec.get("expandable", True),
                )
            elif role == "agent":
                panel.add_message(
                    "agent",
                    content,
                    summary=rec.get("summary"),
                    detail=rec.get("detail"),
                    expandable=rec.get("expandable", True),
                )
            elif role == "tool_call":
                panel.add_tool_call(
                    content,
                    rec.get("arguments", {}),
                    summary=rec.get("summary"),
                    detail=rec.get("detail"),
                    expandable=rec.get("expandable", True),
                )
            elif role == "tool_result":
                panel.add_tool_result(
                    content,
                    rec.get("result"),
                    rec.get("error"),
                    summary=rec.get("summary"),
                    detail=rec.get("detail"),
                    expandable=rec.get("expandable"),
                )
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

    def _on_interrupt(self, agent_type: str) -> None:
        """Handle interrupt request from GUI."""
        self._submit_coroutine(self.backend.interrupt_current_message(agent_type))

    def _on_bus_message(self, message: Message) -> None:
        self._message_signal.emit(message)

    def _dispatch_backend_message(self, message: Message) -> None:
        from ..interfaces.types import (
            AgentResponse,
            Checkpoint,
            Error,
            QueueUpdateMessage,
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
        elif isinstance(message, QueueUpdateMessage):
            self._handle_queue_update(message)

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
        source_key = str(message.source or "user")
        is_agent_message = source_key not in {"user", "system"}
        is_coordination = source_key == "main_agent"
        summary = None
        detail = None
        expandable = True
        if is_agent_message:
            sender = "Main" if source_key == "main_agent" else self._get_agent_display_name(source_key)
            summary, detail, expandable = self._build_inter_agent_summary(
                f"Message From {sender}",
                message.content,
            )

        target_panel = self._get_panel_for_agent(agent_str)
        target_panel.add_message(
            "user",
            message.content,
            source=message.source,
            coordination=is_coordination,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )

        self._conv_store.append_message(
            agent_str,
            "user",
            message.content,
            extra={
                "source": message.source,
                "summary": summary,
                "detail": detail,
                "expandable": expandable,
            },
        )

    def _get_agent_display_name(self, agent_type: str) -> str:
        return get_agent_badge(agent_type)

    def _handle_tool_call(self, message: ToolCall) -> None:
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        summary = None
        detail = None
        expandable = True
        if agent_str == "main" and message.tool_name == "send_to_agent":
            target = self._get_agent_display_name(str(message.arguments.get("agent_type", "sub")))
            summary = f"Main To {target}"
            expandable = False

        panel.add_tool_call(
            message.tool_name,
            message.arguments,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )
        self._conv_store.append_tool_call(
            agent_str,
            message.tool_name,
            message.arguments,
            extra={
                "summary": summary,
                "detail": detail,
                "expandable": expandable,
            },
        )

    def _handle_tool_result(self, message: ToolResult) -> None:
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        result_str = str(message.result) if message.result else None
        summary = None
        detail = None
        expandable = None

        if agent_str == "main" and message.tool_name == "send_to_agent":
            summary, detail, expandable = self._format_send_to_agent_result(message.result, message.error)
            result_str = detail or summary
        elif message.tool_name == "manage_tasks":
            summary, detail, expandable = self._format_manage_tasks_result(message.result, message.error)
            if summary or detail:
                result_str = detail or summary

        panel.add_tool_result(
            message.tool_name,
            message.result,
            message.error,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )
        self._conv_store.append_tool_result(
            agent_str,
            message.tool_name,
            result_str,
            message.error,
            extra={
                "summary": summary,
                "detail": detail,
                "expandable": expandable,
            },
        )

    def _format_send_to_agent_result(self, result, error: str | None) -> tuple[str, str | None, bool]:
        if error:
            return ("Send To Agent failed", error, True)

        if not isinstance(result, dict):
            text = str(result).strip() if result is not None else ""
            return ("Sub-agent replied", text or None, bool(text))

        target = self._get_agent_display_name(str(result.get("agent_type", "sub")))
        status = str(result.get("status", "success"))
        response = str(result.get("response", "") or "").strip()

        if status == "delegated":
            detail = str(result.get("message", "") or "").strip() or None
            return (f"Delegated To {target}", detail, bool(detail))

        if status == "timeout":
            detail = str(result.get("error", "") or "").strip() or None
            return (f"{target} did not reply in time", detail, bool(detail))

        if status == "error":
            detail = str(result.get("error", "") or "").strip() or None
            return (f"Send To {target} failed", detail, bool(detail))

        if not response:
            return (f"{target} replied", None, False)

        first_line = response.splitlines()[0].strip()
        summary = f"{target} replied: {first_line}" if first_line else f"{target} replied"
        detail = response if ("\n" in response or len(response) > len(first_line)) else None
        return (summary, detail, bool(detail))

    def _format_manage_tasks_result(self, result, error: str | None) -> tuple[str | None, str | None, bool | None]:
        if error or not isinstance(result, dict):
            return (None, None, None)

        if str(result.get("status", "")) != "ok":
            return (None, None, None)

        ui_summary = str(result.get("_ui_summary", "") or "").strip()
        ui_detail = str(result.get("_ui_detail", "") or "").strip()
        if not ui_summary and not ui_detail:
            return (None, None, None)

        summary = ui_summary or "Task completed"
        detail = ui_detail or None
        expandable = bool(detail)
        return (summary, detail, expandable)

    def _build_inter_agent_summary(self, prefix: str, content: str) -> tuple[str, str | None, bool]:
        response = str(content or "").strip()
        if not response:
            return (prefix, None, False)

        first_line = response.splitlines()[0].strip()
        summary = f"{prefix}: {first_line}" if first_line else prefix
        detail = response if ("\n" in response or len(response) > len(first_line)) else None
        return (summary, detail, bool(detail))

    def _handle_status_change(self, message: StatusChange) -> None:
        panel = self._get_panel_for_agent(message.agent_type)
        panel.set_status(message.status, message.extra)

    def _handle_error(self, message: Error) -> None:
        self.main_agent_panel.add_error(message.source, message.message)

    def _handle_agent_feedback(self, message: AgentFeedback) -> None:
        """Handle AgentFeedback and show collapsed sub-agent issue reports in main."""
        from enum import Enum

        agent_str = message.agent_type.value if isinstance(message.agent_type, Enum) else str(message.agent_type)
        issue_type = message.feedback_type or "issue"
        summary, detail, expandable = self._build_inter_agent_summary(
            f"{self._get_agent_display_name(agent_str)} reported {issue_type}",
            message.content,
        )
        self.main_agent_panel.add_message(
            "agent",
            message.content,
            source=agent_str,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )
        self._conv_store.append_message(
            "main",
            "agent",
            message.content,
            extra={
                "source": agent_str,
                "summary": summary,
                "detail": detail,
                "expandable": expandable,
                "feedback_type": issue_type,
            },
        )

    def _handle_queue_update(self, message: QueueUpdateMessage) -> None:
        agent_str = str(message.agent_type)
        panel = self._get_panel_for_agent(agent_str)
        panel.set_queue_preview(message.queued_messages)

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
                brief=getattr(message, "brief", "") or "",
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

    def resizeEvent(self, event):
        """Handle window resize to maintain proportional layout."""
        super().resizeEvent(event)
        self._apply_splitter_sizes()

    def _apply_splitter_sizes(self) -> None:
        if not hasattr(self, "_main_splitter"):
            return
        total_width = self._main_splitter.width()
        if total_width <= 0:
            return

        # Explorer keeps its minimal complete width by default.
        file_target = self.file_tree.minimumWidth()
        remaining = max(0, total_width - file_target)
        sizes = [
            file_target,
            int(remaining * 0.4375),   # preview (35 / 80)
            int(remaining * 0.28125),  # sub agent (22.5 / 80)
            int(remaining * 0.28125),  # main agent (22.5 / 80)
        ]
        self._main_splitter.setSizes(sizes)
