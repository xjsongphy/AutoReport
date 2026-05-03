"""Message cell — VS Code Copilot Chat flat style.

- User messages: left accent border, no bubble
- Agent messages: plain text with bullet prefix
- Coordination: muted bracket label
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class MessageRow(QWidget):
    """Render a chat message in VS Code Copilot's flat style."""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str = "",
        is_coordination: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._role = role
        self._content = content
        self._timestamp = timestamp
        self._is_coordination = is_coordination
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if self._is_coordination:
            coord = QLabel("[Main Agent → Sub Agent]")
            coord.setObjectName("msgCoordination")
            coord.setContentsMargins(16, 4, 16, 0)
            layout.addWidget(coord)

        if self._role == "user":
            # User: flat row with left accent border (VS Code interactive-request)
            row = QWidget()
            row.setObjectName("userMessageRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(16, 6, 16, 6)
            rl.setSpacing(8)

            text = QLabel(self._content)
            text.setObjectName("userMessageText")
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            rl.addWidget(text, 1)

            layout.addWidget(row)
        else:
            # Agent: flat row with bullet prefix
            row = QWidget()
            row.setObjectName("agentMessageRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(16, 4, 16, 4)
            rl.setSpacing(6)

            bullet = QLabel("●")
            bullet.setObjectName("agentBullet")
            bullet.setFixedWidth(12)
            bullet.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            rl.addWidget(bullet)

            text = QLabel(self._content)
            text.setObjectName("agentMessageText")
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            rl.addWidget(text, 1)

            layout.addWidget(row)

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        return f"{role_text}: {self._content}"
