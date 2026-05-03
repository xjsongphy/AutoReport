"""Message cell — VS Code Copilot Chat style.

- User messages: right-aligned rounded bubble (VS Code interactive-request)
- Agent messages: flat layout with avatar icon + content
- Coordination: muted label above message
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class MessageRow(QWidget):
    """Render a chat message matching VS Code Copilot Chat's exact visual style."""

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

        # Top-level padding matches VS Code: .interactive-item-container { padding: 12px 16px }
        # For the non-panel (editor-instance) style: padding: 5px 16px
        outer = QWidget()
        outer.setObjectName("msgOuterContainer")
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(16, 6, 16, 6)
        ol.setSpacing(0)

        if self._is_coordination:
            coord = QLabel("[Main Agent → Sub Agent]")
            coord.setObjectName("msgCoordination")
            ol.addWidget(coord)

        if self._role == "user":
            # VS Code: right-aligned bubble with background
            # .interactive-request .value .rendered-markdown {
            #   background-color: var(--vscode-chat-requestBubbleBackground);
            #   border-radius: var(--vscode-cornerRadius-xLarge);  // typically 12-14px
            #   padding: 8px 12px;
            #   max-width: 90%;
            #   margin-left: auto;  (right-aligned)
            # }
            row = QWidget()
            row.setObjectName("userMessageRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)

            # Right-align the bubble
            rl.addStretch(1)

            bubble = QWidget()
            bubble.setObjectName("userMessageBubble")
            bl = QVBoxLayout(bubble)
            bl.setContentsMargins(8, 8, 12, 8)
            bl.setSpacing(0)

            text = QLabel(self._content)
            text.setObjectName("userMessageText")
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            bl.addWidget(text)

            rl.addWidget(bubble, 0)

            ol.addWidget(row)
        else:
            # VS Code: flat agent response with avatar + username + content
            # .interactive-item-container .header { display: flex; align-items: center;
            #   gap: 8px; margin-bottom: 8px; }
            # .header .avatar { width: 24px; height: 24px; border-radius: 50%; }
            # .header .username { font-size: 13px; font-weight: 600; }
            # .value .rendered-markdown { line-height: 1.5em; font-size: 1em (13px); }
            header = QWidget()
            header.setObjectName("agentHeader")
            hl = QHBoxLayout(header)
            hl.setContentsMargins(0, 0, 0, 8)
            hl.setSpacing(8)

            avatar = QLabel("✦")
            avatar.setObjectName("agentAvatar")
            avatar.setFixedSize(24, 24)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hl.addWidget(avatar)

            username = QLabel("Agent")
            username.setObjectName("agentUsername")
            hl.addWidget(username)

            hl.addStretch()
            ol.addWidget(header)

            # Content area
            content_row = QWidget()
            content_row.setObjectName("agentMessageRow")
            cl = QHBoxLayout(content_row)
            cl.setContentsMargins(32, 0, 0, 0)
            cl.setSpacing(0)

            text = QLabel(self._content)
            text.setObjectName("agentMessageText")
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            cl.addWidget(text, 1)

            ol.addWidget(content_row)

        layout.addWidget(outer)

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        return f"{role_text}: {self._content}"
