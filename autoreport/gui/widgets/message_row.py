"""Single message row component for chat display."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class MessageRow(QWidget):
    """Render a single chat message (user or agent) with timestamp.

    Visual format:
        HH:MM  [Role]

          Content line 1
          Content line 2
    """

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str = "",
        is_coordination: bool = False,
        parent: QWidget | None = None,
    ):
        """Initialize message row.

        Args:
            role: "user" or "agent"
            content: Message content
            timestamp: Time in HH:MM format
            is_coordination: Whether this is a coordination message from main agent
            parent: Parent widget
        """
        super().__init__(parent)
        self._role = role
        self._content = content
        self._timestamp = timestamp or "00:00"
        self._is_coordination = is_coordination

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Header: timestamp + role
        header = QLabel()
        header.setObjectName("messageHeader")

        if self._role == "user":
            role_text = "你"
            if self._is_coordination:
                header.setText(f"{self._timestamp}  [主 Agent 协调] {role_text}")
            else:
                header.setText(f"{self._timestamp}  {role_text}")
        else:
            header.setText(f"{self._timestamp}  Agent")

        layout.addWidget(header)

        # Content
        content_label = QLabel(self._content)
        content_label.setObjectName("messageContent")
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(content_label)

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication

        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        if dark:
            header_fg = "#cccccc"
            user_content_bg = "#0e639c"
            user_content_fg = "#ffffff"
            agent_content_bg = "#2d2d2d"
            agent_content_fg = "#cccccc"
        else:
            header_fg = "#1a1a1a"
            user_content_bg = "#e1f5fe"
            user_content_fg = "#1a1a1a"
            agent_content_bg = "#f3f3f3"
            agent_content_fg = "#1a1a1a"

        self.setStyleSheet(f"""
            QLabel#messageHeader {{
                font-size: 11px;
                font-weight: 600;
                color: {header_fg};
            }}
            QLabel#messageContent {{
                font-size: 13px;
                padding: 4px 8px;
                border-radius: 4px;
                background-color: {user_content_bg if self._role == "user" else agent_content_bg};
                color: {user_content_fg if self._role == "user" else agent_content_fg};
            }}
        """)

    def get_display_text(self) -> str:
        """Get combined display text for testing."""
        role_text = "你" if self._role == "user" else "Agent"
        return f"{self._timestamp} {role_text} {self._content}"
