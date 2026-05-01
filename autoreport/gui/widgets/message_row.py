"""Single message row component — Cline flat-timeline style (no bubble headers)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class MessageRow(QWidget):
    """Render a chat message in Cline's flat timeline style.

    - User messages: badge-background fill, 2px radius, no header (like Cline UserMessage)
    - Agent messages: plain inline text, no background, no header
    - Coordination messages: subtle muted prefix
    """

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
        layout.setContentsMargins(16, 6, 16, 2)  # px-4 py-1.5
        layout.setSpacing(0)

        if self._is_coordination:
            # Coordination messages show a muted source label
            prefix = QLabel("[主 Agent → 子 Agent]")
            prefix.setObjectName("msgCoordination")
            layout.addWidget(prefix)
            layout.addSpacing(4)

        if self._role == "user":
            # Cline UserMessage: badge-bg wrapper, 2px radius, no header
            wrapper = QWidget()
            wrapper.setObjectName("userMessageBubble")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(10, 10, 4, 10)  # p-2.5 pr-1
            wl.setSpacing(0)

            text = QLabel(self._content)
            text.setObjectName("userMessageText")
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            wl.addWidget(text, 1)
            layout.addWidget(wrapper)
        else:
            # Cline MarkdownRow: just inline text, no background, no bubble
            text = QLabel(self._content)
            text.setObjectName("agentMessageText")
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(text)

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        return f"{role_text}: {self._content}"
