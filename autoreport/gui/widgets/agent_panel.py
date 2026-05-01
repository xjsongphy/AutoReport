"""Agent panel with chat-style messages, input, and @ file references."""

from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from autoreport.core.file_search import FileSearchManager
from autoreport.gui.widgets.chat_input import ChatInput
from autoreport.gui.widgets.file_search_popup import FileSearchPopup


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

        # ---- Messages area ----
        self._messages_area = QTextEdit()
        self._messages_area.setReadOnly(True)
        self._messages_area.setObjectName("messagesArea")
        layout.addWidget(self._messages_area, 1)

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
            # Messages area - VSCode editor background
            "msgBg": "#1e1e1e" if dark else "#ffffff",
            "userBubble": "#0e639c" if dark else "#e1f5fe",
            "userFg": "#ffffff" if dark else "#1a1a1a",
            "agentBubble": "#2d2d2d" if dark else "#f3f3f3",
            "agentFg": "#cccccc" if dark else "#1a1a1a",
            # Tool output - white background with border
            "toolBg": "#252526" if dark else "#ffffff",
            "toolBorder": "#3c3c3c" if dark else "#e0e0e0",
            "toolFg": "#858585" if dark else "#666666",
            # Input - Claude Code style white background with orange focus
            "inputBg": "#3c3c3c" if dark else "#ffffff",
            "inputBorder": "#3c3c3c" if dark else "#e0e0e0",
            "inputFocusBorder": claude_orange,
            "inputFocusRing": f"rgba(217, 119, 87, 0.12)",  # 12% opacity
            # Send button
            "sendBg": "#0e639c" if dark else claude_orange,
            "sendFg": "#ffffff",
            "sendHover": "#1177bb" if dark else "#c6613f",
            # Debug button
            "debugFg": "#858585" if dark else "#858585",
            "debugActiveBg": "#5c1a1a" if dark else "#ffcdd2",
            "debugActiveFg": "#f14c4c" if dark else "#c62828",
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
            #messagesArea {{
                background-color: {c["msgBg"]};
                border: none;
                padding: 8px;
                font-size: 13px;
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
        """)

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

    def set_preview_context(self, file_path: str, selected_text: str, start_line: int, end_line: int) -> None:
        self._preview_context = (file_path, selected_text, start_line, end_line)

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
    ) -> None:
        """Add a message to the display.

        Codex-style: Clear bubble formatting with timestamps and role labels.

        Args:
            role: Message role ("user" or "agent").
            content: Message content.
            source: Message source ("user" or "main_agent").
            coordination: Whether this is a coordination message.
        """
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Add spacing before each message
        cursor.insertText("\n")

        ts = datetime.now().strftime("%H:%M")

        if role == "user":
            # Role label with timestamp
            label_fmt = QTextCharFormat()
            label_fmt.setFontWeight(QFont.Weight.Bold)
            label_fmt.setForeground(QColor(self._colors["userFg"]))

            # Coordination indicator (orange)
            if coordination or source == "main_agent":
                coord_fmt = QTextCharFormat()
                coord_fmt.setForeground(QColor("#d97757"))  # Claude orange
                coord_fmt.setFontWeight(QFont.Weight.Bold)
                cursor.insertText(f"{ts} ", self._default_fmt(cursor))
                cursor.insertText("[主 Agent 协调] ", coord_fmt)
                cursor.insertText("你\n", label_fmt)
            else:
                cursor.insertText(f"{ts} ", self._default_fmt(cursor))
                cursor.insertText("你\n", label_fmt)

            # Message content with bubble background
            bubble_fmt = QTextCharFormat()
            bubble_fmt.setBackground(QColor(self._colors["userBubble"]))
            if not coordination:
                bubble_fmt.setForeground(QColor(self._colors["userFg"]))
            else:
                bubble_fmt.setForeground(QColor("#d97757"))  # Orange for coordination

            # Content as block
            lines = content.split("\n")
            for line in lines:
                cursor.insertText("  " + line + "\n", bubble_fmt)

        else:
            # Agent response
            label_fmt = QTextCharFormat()
            label_fmt.setFontWeight(QFont.Weight.Bold)
            label_fmt.setForeground(QColor(self._colors["agentFg"]))

            cursor.insertText(f"{ts} ", self._default_fmt(cursor))
            cursor.insertText("Agent\n", label_fmt)

            # Message content
            content_fmt = QTextCharFormat()
            content_fmt.setForeground(QColor(self._colors["agentFg"]))

            lines = content.split("\n")
            for line in lines:
                cursor.insertText("  " + line + "\n", content_fmt)

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

    def _default_fmt(self, cursor) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._colors["agentFg"]))
        return fmt

    def add_tool_call(self, tool_name: str, arguments: dict) -> None:
        """Add a tool call entry (Codex-style: inline with monospace).

        Args:
            tool_name: Name of the tool being called.
            arguments: Tool arguments.
        """
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        cursor.insertText("\n  ")  # Indent

        # Tool name in monospace with icon
        name_fmt = QTextCharFormat()
        name_fmt.setFontFamily("Consolas, Monaco, monospace")
        name_fmt.setForeground(QColor(self._colors["statusTool"]))

        cursor.insertText("✎ ", name_fmt)
        cursor.insertText(tool_name, name_fmt)

        # Arguments in monospace
        if arguments:
            args_fmt = QTextCharFormat()
            args_fmt.setFontFamily("Consolas, Monaco, monospace")
            args_fmt.setForeground(QColor(self._colors["toolFg"]))

            cursor.insertText("(", args_fmt)
            arg_items = []
            for k, v in arguments.items():
                arg_str = f"{k}={repr(v)[:50]}"  # Limit long values
                arg_items.append(arg_str)
            cursor.insertText(", ".join(arg_items), args_fmt)
            cursor.insertText(")", args_fmt)

        cursor.insertText("\n")

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

    def add_tool_result(self, tool_name: str, result: Any, error: str | None = None) -> None:
        """Add a tool result entry (Codex-style: compact status).

        Args:
            tool_name: Name of the tool.
            result: Tool result.
            error: Optional error message.
        """
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        cursor.insertText("  ")  # Indent

        fmt = QTextCharFormat()
        fmt.setFontFamily("Consolas, Monaco, monospace")

        if error:
            fmt.setForeground(QColor(self._colors["statusError"]))
            cursor.insertText("✗ ", fmt)
            fmt.setFontWeight(QFont.Weight.Bold)
            cursor.insertText(f"{tool_name} failed: ", fmt)
            fmt.setFontWeight(QFont.Weight.Normal)
            cursor.insertText(f"{error}\n", fmt)
        else:
            fmt.setForeground(QColor(self._colors["toolFg"]))
            cursor.insertText("✓ ", fmt)
            cursor.insertText(f"{tool_name}\n", fmt)

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

    def add_error(self, source: str, message: str) -> None:
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        ts = datetime.now().strftime("%H:%M")
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._colors["statusError"]))
        fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f"\n{ts}  ✗ {source}: {message}\n", fmt)

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

    def add_checkpoint(self, checkpoint_id: str, description: str) -> None:
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        ts = datetime.now().strftime("%H:%M")
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#4fc3f7"))
        cursor.insertText(f"\n{ts}  ⚑ {description}\n", fmt)

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

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
        if self._preview_context:
            file_path, selected_text, start_line, end_line = self._preview_context
            context_block = (
                f"\n\n<!-- 上下文引用 -->\n"
                f"**文件**: {file_path} (行 {start_line}-{end_line})\n"
                f"```\n{selected_text}\n```\n"
            )
            final_message = content + context_block
            self._preview_context = None

        self._input_field.clear_text()
        self.add_message("user", content)
        self.message_sent.emit(final_message)

    def _on_debug_toggled(self) -> None:
        enabled = self._debug_button.isChecked()
        if enabled:
            self._debug_button.setStyleSheet(
                f"background-color: {self._colors['debugActiveBg']}; "
                f"color: {self._colors['debugActiveFg']}; "
                "border: 1px solid transparent; border-radius: 3px; padding: 2px 8px; font-size: 11px;"
            )
        else:
            self._debug_button.setStyleSheet("")
        self.debug_mode_toggled.emit(enabled)

    def set_debug_mode(self, enabled: bool) -> None:
        self._debug_button.setChecked(enabled)

    def hide_debug_button(self, hide: bool = True) -> None:
        self._debug_button.setHidden(hide)
