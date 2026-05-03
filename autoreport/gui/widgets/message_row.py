"""Message cell — Codex CLI flat-timeline style.

- User messages: subtle background tint, › prefix (bold dim)
- Agent messages: plain text, • bullet prefix
- Coordination: muted bracket prefix
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class MessageRow(QWidget):
    """Render a chat message in Codex's flat timeline style."""

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
        layout.setContentsMargins(16, 4, 16, 4)
        layout.setSpacing(0)

        if self._is_coordination:
            prefix = QLabel("[Main Agent → Sub Agent]")
            prefix.setObjectName("msgCoordination")
            layout.addWidget(prefix)
            layout.addSpacing(2)

        if self._role == "user":
            row = QHBoxLayout()
            row.setContentsMargins(0, 4, 0, 4)
            row.setSpacing(0)

            # User wrapper with subtle bg tint
            wrapper = QWidget()
            wrapper.setObjectName("userMessageBubble")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(12, 10, 12, 10)
            wl.setSpacing(8)

            # › prefix (Codex-style)
            prompt_char = QLabel("›")
            prompt_char.setObjectName("userPrompt")
            prompt_char.setFixedWidth(14)
            prompt_char.setAlignment(Qt.AlignmentFlag.AlignTop)
            wl.addWidget(prompt_char)

            text = QLabel(self._content)
            text.setObjectName("userMessageText")
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            wl.addWidget(text, 1)

            layout.addWidget(wrapper)
        else:
            row = QHBoxLayout()
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(8)

            # • bullet prefix (Codex-style, dimmed)
            bullet = QLabel("•")
            bullet.setObjectName("agentBullet")
            bullet.setFixedWidth(14)
            bullet.setAlignment(Qt.AlignmentFlag.AlignTop)
            row.addWidget(bullet)

            text = QLabel(self._content)
            text.setObjectName("agentMessageText")
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            row.addWidget(text, 1)

            layout.addLayout(row)

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        return f"{role_text}: {self._content}"
