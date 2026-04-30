"""Agent panel widget for timeline and chat with file references."""

from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from PyQt6.QtCore import QPoint, pyqtSignal
from PyQt6.QtGui import QTextCursor
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
    """Enhanced agent panel with timeline, chat input, and @ file references."""

    message_sent = pyqtSignal(str)
    debug_mode_toggled = pyqtSignal(bool)  # Signal for debug mode toggle

    def __init__(self, panel_id: str, title: str, workspace: Path | None = None):
        """Initialize agent panel.

        Args:
            panel_id: Panel identifier.
            title: Panel title.
            workspace: Project workspace directory (for file search).
        """
        super().__init__()
        self.panel_id = panel_id
        self._agent_type = "sub"
        self._workspace = Path(workspace).resolve() if workspace else Path.cwd()
        self._preview_context: tuple[str, str, int, int] | None = None

        # File search components
        self._file_search_manager = FileSearchManager(self._workspace)
        self._file_search_popup: FileSearchPopup | None = None

        self._setup_ui(title)
        self._setup_file_search()

    def _setup_ui(self, title: str) -> None:
        """Setup user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(title_label)

        # Status
        self._status_label = QLabel("状态: 空闲")
        self._status_label.setStyleSheet("color: gray;")
        layout.addWidget(self._status_label)

        # Debug mode button (for sub-agents only)
        debug_layout = QHBoxLayout()
        layout.addLayout(debug_layout)

        debug_layout.addStretch()

        self._debug_button = QPushButton("调试模式")
        self._debug_button.setCheckable(True)
        self._debug_button.clicked.connect(self._on_debug_toggled)
        debug_layout.addWidget(self._debug_button)

        # Timeline/messages area
        self._messages_area = QTextEdit()
        self._messages_area.setReadOnly(True)
        self._messages_area.setMinimumHeight(200)
        layout.addWidget(self._messages_area)

        # Input area - use ChatInput for @ file reference support
        input_layout = QHBoxLayout()
        layout.addLayout(input_layout)

        self._input_field = ChatInput()
        self._input_field.setPlaceholderText("输入消息... (@ 引用文件)")
        self._input_field.send_message.connect(self._on_send)
        self._input_field.file_reference_requested.connect(self._on_file_reference_requested)
        input_layout.addWidget(self._input_field)

        # Send button (optional, since Enter works)
        send_button = QPushButton("发送")
        send_button.clicked.connect(self._on_send)
        input_layout.addWidget(send_button)

    def _setup_file_search(self) -> None:
        """Setup file search popup and manager."""
        self._file_search_popup = FileSearchPopup(self)
        self._file_search_popup.file_selected.connect(self._on_file_selected)
        self._file_search_popup.cancelled.connect(self._on_file_search_cancelled)

    def _on_file_reference_requested(self, query: str, position: QPoint) -> None:
        """Handle @ file reference request.

        Args:
            query: Search query (text after @).
            position: Global position for popup.
        """
        if not self._file_search_popup:
            return

        # Position and show popup
        self._file_search_popup.move(position)
        self._file_search_popup.set_query(query, waiting=True)
        self._file_search_popup.show()
        self._file_search_popup.raise_()
        self._file_search_popup.setFocus()

        # Update input state
        self._input_field.set_popup_active(True)

        # Trigger search
        async def on_results(matches):
            # Check if popup still active
            if self._file_search_popup and self._file_search_popup.isVisible():
                self._file_search_popup.set_matches(matches)

        import asyncio
        asyncio.create_task(self._file_search_manager.search(query, on_results))

    def _on_file_selected(self, file_path: Path) -> None:
        """Handle file selected from popup.

        Args:
            file_path: Selected file path.
        """
        self._file_search_popup.hide()
        self._input_field.set_popup_active(False)
        self._input_field.setFocus()

        # Insert file reference markdown link
        self._input_field.insert_file_reference(file_path)

        logger.debug("File reference inserted: {}", file_path)

    def _on_file_search_cancelled(self) -> None:
        """Handle file search cancelled."""
        self._file_search_popup.hide()
        self._input_field.set_popup_active(False)
        self._input_field.setFocus()

    def set_preview_context(self, file_path: str, selected_text: str, start_line: int, end_line: int) -> None:
        """Store preview selection context for next message.

        Args:
            file_path: Relative file path.
            selected_text: Selected text content.
            start_line: Start line number.
            end_line: End line number.
        """
        self._preview_context = (file_path, selected_text, start_line, end_line)
        logger.debug(
            "Preview context set: {} (lines {}-{})",
            file_path,
            start_line,
            end_line
        )

    def set_workspace(self, workspace: Path) -> None:
        """Update workspace directory.

        Args:
            workspace: New workspace directory.
        """
        self._workspace = Path(workspace).resolve()
        self._file_search_manager = FileSearchManager(self._workspace)

    def set_agent_type(self, agent_type: str) -> None:
        """Set agent type for this panel.

        Args:
            agent_type: Agent type (data_analysis, plotting, theory, report).
        """
        self._agent_type = agent_type

        # Update title
        titles = {
            "data_analysis": "数据分析 Agent",
            "plotting": "图像绘制 Agent",
            "theory": "理论推导 Agent",
            "report": "报告撰写 Agent",
            "main": "主 Agent",
            "sub": "子 Agent",
        }
        title = titles.get(agent_type, "Agent")

        # Find title label and update
        for child in self.children():
            if isinstance(child, QLabel) and "Agent" in child.text():
                child.setText(title)
                break

    @property
    def agent_type(self) -> str:
        """Get current agent type."""
        return self._agent_type

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the timeline.

        Args:
            role: Message role (user, agent).
            content: Message content.
        """
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        timestamp = datetime.now().strftime("%H:%M:%S")
        role_label = "用户" if role == "user" else "Agent"

        cursor.insertText(f"\n[{timestamp}] {role_label}:\n")
        cursor.insertText(content)
        cursor.insertText("\n" + "-" * 50 + "\n")

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

    def add_tool_call(self, tool_name: str, arguments: dict) -> None:
        """Add a tool call to the timeline.

        Args:
            tool_name: Name of tool being called.
            arguments: Tool arguments.
        """
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        timestamp = datetime.now().strftime("%H:%M:%S")
        cursor.insertText(f"\n[{timestamp}] 🔧 调用工具: {tool_name}\n")

        # Add arguments (simplified)
        args_str = ", ".join(f"{k}={v}" for k, v in arguments.items())
        cursor.insertText(f"参数: {args_str}\n")

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

    def add_tool_result(self, tool_name: str, result: Any, error: str | None = None) -> None:
        """Add a tool result to the timeline.

        Args:
            tool_name: Name of tool.
            result: Tool result.
            error: Error message if any.
        """
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        timestamp = datetime.now().strftime("%H:%M:%S")

        if error:
            cursor.insertText(f"\n[{timestamp}] ❌ 工具错误 ({tool_name}): {error}\n")
        else:
            cursor.insertText(f"\n[{timestamp}] ✅ 工具完成: {tool_name}\n")

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

    def set_status(self, status: str, extra: dict | None = None) -> None:
        """Set agent status display.

        Args:
            status: Agent status (idle, thinking, running_tool, error).
            extra: Extra information.
        """
        status_labels = {
            "idle": "空闲",
            "thinking": "思考中...",
            "running_tool": "执行工具...",
            "error": "错误",
            "debug_mode": "调试模式",
        }

        label = status_labels.get(status, status)
        self._status_label.setText(f"状态: {label}")

        # Update color
        colors = {
            "idle": "gray",
            "thinking": "blue",
            "running_tool": "orange",
            "error": "red",
            "debug_mode": "purple",
        }
        color = colors.get(status, "black")
        self._status_label.setStyleSheet(f"color: {color};")

    def add_error(self, source: str, message: str) -> None:
        """Add an error to the timeline.

        Args:
            source: Error source.
            message: Error message.
        """
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        timestamp = datetime.now().strftime("%H:%M:%S")
        cursor.insertText(f"\n[{timestamp}] ❌ 错误 ({source}): {message}\n")

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

    def add_checkpoint(self, checkpoint_id: str, description: str) -> None:
        """Add a checkpoint to the timeline.

        Args:
            checkpoint_id: Checkpoint ID.
            description: Checkpoint description.
        """
        cursor = self._messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        timestamp = datetime.now().strftime("%H:%M:%S")
        cursor.insertText(f"\n[{timestamp}] 📍 检查点: {description}\n")
        cursor.insertText(f"   ID: {checkpoint_id}\n")

        self._messages_area.setTextCursor(cursor)
        self._messages_area.ensureCursorVisible()

    def _on_send(self) -> None:
        """Handle send button click."""
        content = self._input_field.get_plain_text().strip()
        if not content:
            return

        # Append preview context if available
        final_message = content
        if self._preview_context:
            file_path, selected_text, start_line, end_line = self._preview_context
            context_block = f"\n\n<!-- 上下文引用 -->\n**文件**: {file_path} (行 {start_line}-{end_line})\n```\n{selected_text}\n```\n"
            final_message = content + context_block

            # Clear context after use
            self._preview_context = None

        self._input_field.clear_text()
        self.add_message("user", final_message)
        self.message_sent.emit(final_message)

    def _on_debug_toggled(self) -> None:
        """Handle debug mode toggle."""
        enabled = self._debug_button.isChecked()

        if enabled:
            self._debug_button.setStyleSheet("background-color: #ffcccc;")
            self.add_message("system", "调试模式已启用")
        else:
            self._debug_button.setStyleSheet("")
            self.add_message("system", "调试模式已禁用")

        # Emit signal
        self.debug_mode_toggled.emit(enabled)

    def set_debug_mode(self, enabled: bool) -> None:
        """Set debug mode state (from external source).

        Args:
            enabled: Whether debug mode is enabled.
        """
        self._debug_button.setChecked(enabled)

    def hide_debug_button(self, hide: bool = True) -> None:
        """Hide or show debug button.

        Args:
            hide: Whether to hide the button (True for main agent panel).
        """
        self._debug_button.setHidden(hide)
