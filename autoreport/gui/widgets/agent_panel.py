"""Agent panel widget for timeline and chat."""

from datetime import datetime
from typing import Any

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from loguru import logger


class AgentPanel(QWidget):
    """Agent panel with timeline and chat input."""

    message_sent = pyqtSignal(str)

    def __init__(self, panel_id: str, title: str):
        """Initialize agent panel.

        Args:
            panel_id: Panel identifier.
            title: Panel title.
        """
        super().__init__()
        self.panel_id = panel_id
        self._agent_type = "sub"
        self._setup_ui(title)

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

        # Timeline/messages area
        self._messages_area = QTextEdit()
        self._messages_area.setReadOnly(True)
        self._messages_area.setMinimumHeight(200)
        layout.addWidget(self._messages_area)

        # Input area
        input_layout = QHBoxLayout()
        layout.addLayout(input_layout)

        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("输入消息...")
        self._input_field.returnPressed.connect(self._on_send)
        input_layout.addWidget(self._input_field)

        send_button = QPushButton("发送")
        send_button.clicked.connect(self._on_send)
        input_layout.addWidget(send_button)

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
        content = self._input_field.text().strip()
        if not content:
            return

        self._input_field.clear()
        self.add_message("user", content)
        self.message_sent.emit(content)
