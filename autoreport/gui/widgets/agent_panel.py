"""Agent panel with chat-style messages, input, and @ file references."""

from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from autoreport.core.file_search import FileSearchManager
from autoreport.gui.widgets.chat_input import ChatInput
from autoreport.gui.widgets.debug_panel import DebugPanel
from autoreport.gui.widgets.file_search_popup import FileSearchPopup
from autoreport.gui.widgets.message_row import MessageRow
from autoreport.gui.widgets.messages_area import MessagesArea
from autoreport.gui.widgets.tool_call_group import ToolCallGroup
from autoreport.interfaces.types import ApiDebugMessage


class AgentPanel(QWidget):
    """Chat-style agent panel with messages, status, and @ file references."""

    message_sent = pyqtSignal(str)
    debug_mode_toggled = pyqtSignal(bool)

    def __init__(self, panel_id: str, title: str, workspace: Path | None = None):
        super().__init__()
        self.panel_id = panel_id
        self._agent_type = "sub"
        self._workspace = Path(workspace).resolve() if workspace else Path.cwd()
        self._preview_context: tuple[str, str, int, int] | None = None
        self._opened_file: str | None = None  # file opened but no selection
        self._context_enabled: bool = True  # eye toggle state
        self._current_tool_group = None  # Track current tool call group

        self._file_search_manager = FileSearchManager(self._workspace)
        self._file_search_popup: FileSearchPopup | None = None

        self._setup_ui(title)
        self._apply_style()
        self._setup_file_search()

    def _setup_ui(self, title: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- Header bar ----
        header = QWidget()
        header.setObjectName("panelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("panelTitle")
        header_layout.addWidget(self._title_label)

        self._status_label = QLabel("空闲")
        self._status_label.setObjectName("panelStatus")
        header_layout.addWidget(self._status_label)

        header_layout.addStretch()

        self._debug_button = QPushButton("调试")
        self._debug_button.setObjectName("debugBtn")
        self._debug_button.setCheckable(True)
        self._debug_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._debug_button.clicked.connect(self._on_debug_toggled)
        header_layout.addWidget(self._debug_button)

        layout.addWidget(header)

        # ---- Main content area (messages + debug) ----
        content_splitter = QWidget()
        content_layout = QVBoxLayout(content_splitter)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ---- Messages area ----
        self._messages_area = MessagesArea()
        content_layout.addWidget(self._messages_area, 1)

        # ---- Debug panel (hidden by default) ----
        self._debug_panel = DebugPanel()
        self._debug_panel.setVisible(False)
        content_layout.addWidget(self._debug_panel)

        layout.addWidget(content_splitter, 1)

        # ---- Context chip bar ----
        self._context_bar = QWidget()
        self._context_bar.setObjectName("contextBar")
        self._context_bar.setVisible(False)
        context_layout = QHBoxLayout(self._context_bar)
        context_layout.setContentsMargins(8, 2, 8, 2)
        context_layout.setSpacing(4)

        file_icon = QLabel("\U0001F4C4")
        file_icon.setObjectName("contextIcon")
        context_layout.addWidget(file_icon)

        self._context_label = QLabel()
        self._context_label.setObjectName("contextLabel")
        self._context_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        context_layout.addWidget(self._context_label, 1)

        self._context_eye = QPushButton("\U0001F441")  # eye open
        self._context_eye.setObjectName("contextEye")
        self._context_eye.setCheckable(True)
        self._context_eye.setChecked(True)
        self._context_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self._context_eye.setToolTip("发送时包含上下文引用 (点击切换)")
        self._context_eye.clicked.connect(self._on_eye_toggled)
        self._context_eye.setFixedSize(24, 24)
        context_layout.addWidget(self._context_eye)

        layout.addWidget(self._context_bar)

        # ---- Input bar ----
        input_bar = QWidget()
        input_bar.setObjectName("inputBar")
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(8, 6, 8, 6)
        input_layout.setSpacing(6)

        self._input_field = ChatInput()
        self._input_field.setPlaceholderText("输入消息… (@ 引用文件, Enter 发送)")
        self._input_field.send_message.connect(self._on_send)
        self._input_field.file_reference_requested.connect(self._on_file_reference_requested)
        input_layout.addWidget(self._input_field, 1)

        send_btn = QPushButton("发送")
        send_btn.setObjectName("sendBtn")
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(send_btn)

        layout.addWidget(input_bar)

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        # Claude Code theme colors
        claude_orange = "#d97757"

        c = {
            # Header - VSCode sidebar background
            "headerBg": "#252526" if dark else "#f3f3f3",
            "headerBorder": "#3c3c3c" if dark else "#e0e0e0",
            "titleFg": "#cccccc" if dark else "#1a1a1a",
            # Status colors
            "statusIdle": "#858585" if dark else "#858585",
            "statusThink": "#4fc3f7" if dark else "#0066bf",
            "statusTool": "#ffb74d" if dark else "#e65100",
            "statusError": "#f14c4c" if dark else "#c62828",
            "statusDebug": "#ce93d8" if dark else "#7b1fa2",
            # Input - Claude Code style white background with orange focus
            "inputBg": "#3c3c3c" if dark else "#ffffff",
            "inputBorder": "#3c3c3c" if dark else "#e0e0e0",
            "inputFocusBorder": claude_orange,
            "inputFocusRing": "rgba(217, 119, 87, 0.12)",  # 12% opacity
            # Send button
            "sendBg": "#0e639c" if dark else claude_orange,
            "sendFg": "#ffffff",
            "sendHover": "#1177bb" if dark else "#c6613f",
            # Debug button
            "debugFg": "#858585" if dark else "#858585",
            "debugActiveBg": "#5c1a1a" if dark else "#ffcdd2",
            "debugActiveFg": "#f14c4c" if dark else "#c62828",
            # Context bar
            "contextBg": "#2d2d2d" if dark else "#e8f0fe",
            "contextBorder": claude_orange,
            "contextFg": "#cccccc" if dark else "#333333",
            "contextIconFg": claude_orange,
        }
        self._colors = c

        self.setStyleSheet(f"""
            #panelHeader {{
                background-color: {c["headerBg"]};
                border-bottom: 1px solid {c["headerBorder"]};
            }}
            #panelTitle {{
                font-size: 13px;
                font-weight: 600;
                color: {c["titleFg"]};
            }}
            #panelStatus {{
                font-size: 11px;
                color: {c["statusIdle"]};
                margin-left: 8px;
            }}
            #inputBar {{
                background-color: {c["headerBg"]};
                border-top: 1px solid {c["headerBorder"]};
            }}
            #sendBtn {{
                background-color: {c["sendBg"]};
                color: {c["sendFg"]};
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            #sendBtn:hover {{ background-color: {c["sendHover"]}; }}
            #debugBtn {{
                background-color: transparent;
                color: {c["debugFg"]};
                border: 1px solid {c["headerBorder"]};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            #contextBar {{
                background-color: {c["contextBg"]};
                border-left: 2px solid {c["contextBorder"]};
                border-bottom: 1px solid {c["headerBorder"]};
            }}
            #contextLabel {{
                font-size: 11px;
                color: {c["contextFg"]};
            }}
            #contextIcon, #contextEye {{
                font-size: 13px;
                color: {c["contextIconFg"]};
            }}
            #contextEye {{
                background-color: transparent;
                border: none;
                border-radius: 2px;
            }}
            #contextEye:hover {{ background-color: rgba(128,128,128,0.15); }}
        """)

        # Initialize tool group tracking
        self._current_tool_group = None

    def _setup_file_search(self) -> None:
        self._file_search_popup = FileSearchPopup(self)
        self._file_search_popup.file_selected.connect(self._on_file_selected)
        self._file_search_popup.cancelled.connect(self._on_file_search_cancelled)

    # ---- File reference handling ----

    def _on_file_reference_requested(self, query: str, position: QPoint) -> None:
        if not self._file_search_popup:
            return
        self._file_search_popup.move(position)
        self._file_search_popup.set_query(query, waiting=True)
        self._file_search_popup.show()
        self._file_search_popup.raise_()
        self._file_search_popup.setFocus()
        self._input_field.set_popup_active(True)

        async def on_results(matches):
            if self._file_search_popup and self._file_search_popup.isVisible():
                self._file_search_popup.set_matches(matches)

        import asyncio
        asyncio.create_task(self._file_search_manager.search(query, on_results))

    def _on_file_selected(self, file_path: Path) -> None:
        self._file_search_popup.hide()
        self._input_field.set_popup_active(False)
        self._input_field.setFocus()
        self._input_field.insert_file_reference(file_path)

    def _on_file_search_cancelled(self) -> None:
        self._file_search_popup.hide()
        self._input_field.set_popup_active(False)
        self._input_field.setFocus()

    # ---- Public API ----

    def set_opened_file(self, file_path: str) -> None:
        """Set context for a file that was opened but no text selected.

        Chip shows filename; on send, includes the file path for agent to read.

        Args:
            file_path: Relative file path.
        """
        self._opened_file = file_path
        self._preview_context = None
        self._context_enabled = True
        self._context_eye.setChecked(True)
        self._context_eye.setText("\U0001F441")  # eye open
        fname = Path(file_path).name
        self._context_label.setText(fname)
        self._context_bar.setVisible(True)

    def set_preview_context(self, file_path: str, selected_text: str, start_line: int, end_line: int) -> None:
        """Set context for selected text in preview.

        Chip shows line count; on send, includes filename, line range, and content.

        Args:
            file_path: Relative file path.
            selected_text: Selected text content.
            start_line: Start line number (1-indexed).
            end_line: End line number (1-indexed).
        """
        self._preview_context = (file_path, selected_text, start_line, end_line)
        self._opened_file = None
        self._context_enabled = True
        self._context_eye.setChecked(True)
        self._context_eye.setText("\U0001F441")  # eye open
        line_count = end_line - start_line + 1
        label = f"{line_count} line selected" if line_count == 1 else f"{line_count} lines selected"
        self._context_label.setText(label)
        self._context_bar.setVisible(True)

    def _on_eye_toggled(self) -> None:
        self._context_enabled = self._context_eye.isChecked()
        if self._context_enabled:
            self._context_eye.setText("\U0001F441")  # eye open
            self._context_eye.setToolTip("发送时包含上下文引用 (点击切换)")
        else:
            self._context_eye.setText("\U0001F576")  # crossed-out / hidden
            self._context_eye.setToolTip("上下文已隐藏，不会发送给 Agent (点击恢复)")

    def set_workspace(self, workspace: Path) -> None:
        self._workspace = Path(workspace).resolve()
        self._file_search_manager = FileSearchManager(self._workspace)

    def set_agent_type(self, agent_type: str) -> None:
        self._agent_type = agent_type
        titles = {
            "data_analysis": "数据分析 Agent",
            "plotting": "图像绘制 Agent",
            "theory": "理论推导 Agent",
            "report": "报告撰写 Agent",
            "main": "主 Agent",
            "sub": "子 Agent",
        }
        self._title_label.setText(titles.get(agent_type, "Agent"))

    @property
    def agent_type(self) -> str:
        return self._agent_type

    # ---- Messages ----

    def add_message(
        self,
        role: str,
        content: str,
        source: str = "user",
        coordination: bool = False,
        streaming: bool = False,
    ) -> None:
        """Add a message to the display using MessageRow widget.

        Args:
            role: Message role ("user" or "agent").
            content: Message content.
            source: Message source ("user" or "main_agent").
            coordination: Whether this is a coordination message.
            streaming: If True, append to last agent message instead of creating new.
        """
        # For streaming agent messages, we need to append to the last message
        if streaming and role == "agent" and not content:
            # Empty content signals completion - just ensure visible
            return

        if streaming and role == "agent":
            # Append to last agent message
            # Find the last MessageRow and append to it
            rows = self._messages_area.get_message_rows()
            if rows and rows[-1]._role == "agent":
                # Append content to the last message
                last_row = rows[-1]
                last_row._content += content
                # Update the content label
                # Find the content label (second child)
                if last_row.layout().count() > 1:
                    content_label = last_row.layout().itemAt(1).widget()
                    if content_label:
                        content_label.setText(last_row._content)
            return

        # Add new message row
        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role=role,
            content=content,
            timestamp=ts,
            is_coordination=coordination or source == "main_agent",
        )

    def add_tool_call(self, tool_name: str, arguments: dict) -> None:
        """Add a tool call entry using ToolCallGroup.

        Args:
            tool_name: Name of the tool being called.
            arguments: Tool arguments.
        """
        # Get or create the current tool group
        groups = self._messages_area.get_tool_groups()

        # If there's no recent group or the last group is "done", create a new one
        if not groups:
            group = self._messages_area.add_tool_group()
            self._current_tool_group = group
        else:
            # Use the last group
            self._current_tool_group = groups[-1]

    def add_tool_result(self, tool_name: str, result: Any, error: str | None = None) -> None:
        """Add a tool result entry to the current ToolCallGroup.

        Args:
            tool_name: Name of the tool.
            result: Tool result.
            error: Optional error message.
        """
        if hasattr(self, '_current_tool_group') and self._current_tool_group:
            # Calculate duration (placeholder - would need actual timing)
            duration_ms = 100  # Placeholder

            self._current_tool_group.add_tool_call(
                name=tool_name,
                arguments={},  # Arguments were already added in add_tool_call
                success=error is None,
                duration_ms=duration_ms,
                result=result if error is None else None,
                error=error,
            )

    def add_error(self, source: str, message: str) -> None:
        """Add an error message to the display.

        Args:
            source: Error source.
            message: Error message.
        """
        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role="agent",
            content=f"✗ {source}: {message}",
            timestamp=ts,
        )

    def add_checkpoint(self, checkpoint_id: str, description: str) -> None:
        """Add a checkpoint notification to the display.

        Args:
            checkpoint_id: Checkpoint ID.
            description: Checkpoint description.
        """
        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role="agent",
            content=f"⚑ {description}",
            timestamp=ts,
        )

    # ---- Status ----

    def set_status(self, status: str, extra: dict | None = None) -> None:
        labels = {
            "idle": "空闲",
            "thinking": "思考中…",
            "running_tool": "执行工具…",
            "error": "错误",
            "debug_mode": "调试模式",
        }
        color_map = {
            "idle": "statusIdle",
            "thinking": "statusThink",
            "running_tool": "statusTool",
            "error": "statusError",
            "debug_mode": "statusDebug",
        }
        label = labels.get(status, status)
        color_key = color_map.get(status, "statusIdle")
        color = self._colors.get(color_key, "#888")
        self._status_label.setText(label)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 11px; margin-left: 8px;")

    # ---- Actions ----

    def _on_send(self) -> None:
        content = self._input_field.get_plain_text().strip()
        if not content:
            return

        final_message = content
        if self._context_enabled:
            if self._preview_context:
                file_path, selected_text, start_line, end_line = self._preview_context
                context_block = (
                    f"\n\n<!-- 上下文引用 -->\n"
                    f"**文件**: {file_path} (行 {start_line}-{end_line})\n"
                    f"```\n{selected_text}\n```\n"
                )
                final_message = content + context_block
            elif self._opened_file:
                context_block = (
                    f"\n\n<!-- 上下文引用 -->\n"
                    f"**文件**: {self._opened_file}\n"
                )
                final_message = content + context_block

        self._input_field.clear_text()
        self.add_message("user", content)
        self.message_sent.emit(final_message)

        # Clear context bar after sending
        self._preview_context = None
        self._opened_file = None
        self._context_bar.setVisible(False)

    def _on_debug_toggled(self) -> None:
        enabled = self._debug_button.isChecked()
        if enabled:
            self._debug_button.setStyleSheet(
                f"background-color: {self._colors['debugActiveBg']}; "
                f"color: {self._colors['debugActiveFg']}; "
                "border: 1px solid transparent; border-radius: 3px; padding: 2px 8px; font-size: 11px;"
            )
            # Show debug panel
            self._debug_panel.setVisible(True)
        else:
            self._debug_button.setStyleSheet("")
            # Hide debug panel
            self._debug_panel.setVisible(False)
        self.debug_mode_toggled.emit(enabled)

    def subscribe_to_debug_messages(self, bus) -> None:
        """Subscribe to ApiDebugMessage from the message bus.

        Args:
            bus: MessageBus instance to subscribe to.
        """
        async def on_debug_message(msg):
            if isinstance(msg, ApiDebugMessage):
                self._debug_panel.add_entry(
                    timestamp=msg.timestamp,
                    model=msg.model,
                    tokens_in=msg.tokens_in,
                    tokens_out=msg.tokens_out,
                    duration_ms=msg.duration_ms,
                    status=msg.status,
                    error=msg.error,
                )

        bus.subscribe(ApiDebugMessage, on_debug_message)

    def set_debug_mode(self, enabled: bool) -> None:
        self._debug_button.setChecked(enabled)

    def hide_debug_button(self, hide: bool = True) -> None:
        self._debug_button.setHidden(hide)
