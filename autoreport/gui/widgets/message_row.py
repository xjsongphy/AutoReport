"""Message cell — VS Code Copilot Chat style.

- User messages: right-aligned rounded bubble (VS Code interactive-request)
- Agent messages: flat layout with avatar icon + content + hover copy footer
- Coordination: muted label above message
- Code blocks: monospace card with hover-visible copy icon
"""

import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QClipboard
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _parse_code_blocks(content: str) -> list[tuple[str, str | None]]:
    pattern = r"```(\w*)\n(.*?)```"
    parts: list[tuple[str, str | None]] = []
    last_end = 0
    for m in re.finditer(pattern, content, re.DOTALL):
        if m.start() > last_end:
            parts.append((content[last_end:m.start()], None))
        lang = m.group(1) or None
        code = m.group(2).rstrip()
        parts.append((code, lang))
        last_end = m.end()
    if last_end < len(content):
        parts.append((content[last_end:], None))
    if not parts:
        parts.append((content, None))
    return parts


class _CodeBlockWidget(QWidget):
    """VS Code-style code block with hover-visible copy icon."""

    def __init__(self, code: str, language: str | None, parent=None):
        super().__init__(parent)
        self._code = code
        self._language = language
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("codeBlockCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setObjectName("codeBlockHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 6, 8, 6)
        hl.setSpacing(8)

        lang_label = QLabel(self._language or "code")
        lang_label.setObjectName("codeBlockLang")
        hl.addWidget(lang_label)
        hl.addStretch()

        # Copy icon button — only visible on hover (handled by parent CSS)
        self._copy_btn = QPushButton("📋")
        self._copy_btn.setObjectName("codeBlockCopyBtn")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setFixedSize(24, 20)
        self._copy_btn.setToolTip("Copy code")
        self._copy_btn.clicked.connect(self._copy)
        hl.addWidget(self._copy_btn)

        layout.addWidget(header)

        # Code content
        code_label = QLabel(self._code)
        code_label.setObjectName("codeBlockContent")
        code_label.setWordWrap(False)
        code_label.setTextFormat(Qt.TextFormat.PlainText)
        code_label.setContentsMargins(12, 0, 12, 10)
        layout.addWidget(code_label)

    def _copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._code, QClipboard.Mode.Clipboard)


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
        self._complete = False  # streaming not yet finished
        self._agent_content_layout: QVBoxLayout | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        outer = QWidget()
        outer.setObjectName("msgOuterContainer")
        self._outer_layout = QVBoxLayout(outer)
        self._outer_layout.setContentsMargins(16, 6, 16, 6)
        self._outer_layout.setSpacing(0)

        if self._is_coordination:
            coord = QLabel("[Main Agent → Sub Agent]")
            coord.setObjectName("msgCoordination")
            self._outer_layout.addWidget(coord)

        if self._role == "user":
            row = QWidget()
            row.setObjectName("userMessageRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)
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
            self._outer_layout.addWidget(row)
        else:
            # Agent header
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
            self._outer_layout.addWidget(header)

            # Content area
            self._agent_content_layout = QVBoxLayout()
            self._agent_content_layout.setContentsMargins(32, 0, 0, 0)
            self._agent_content_layout.setSpacing(0)
            self._outer_layout.addLayout(self._agent_content_layout)
            self._rebuild_agent_content()

            # Footer copy toolbar — only visible on hover AFTER streaming complete
            self._footer = QWidget()
            self._footer.setObjectName("msgFooter")
            fl = QHBoxLayout(self._footer)
            fl.setContentsMargins(32, 6, 0, 0)
            fl.setSpacing(4)

            self._copy_btn = QPushButton("📋")
            self._copy_btn.setObjectName("copyBtn")
            self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._copy_btn.setToolTip("Copy")
            self._copy_btn.clicked.connect(self._copy_content)
            self._copy_btn.setFixedSize(24, 22)
            fl.addWidget(self._copy_btn)

            fl.addStretch()
            self._footer.setVisible(False)
            self._outer_layout.addWidget(self._footer)

        layout.addWidget(outer)

    def _clear_agent_content(self) -> None:
        if self._agent_content_layout is None:
            return
        while self._agent_content_layout.count():
            item = self._agent_content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                inner = item.layout()
                while inner.count():
                    inner_item = inner.takeAt(0)
                    if inner_item.widget():
                        inner_item.widget().deleteLater()

    def _rebuild_agent_content(self) -> None:
        self._clear_agent_content()
        if self._agent_content_layout is None:
            return
        segments = _parse_code_blocks(self._content)
        for seg_text, seg_lang in segments:
            if seg_lang is not None:
                code_widget = _CodeBlockWidget(seg_text, seg_lang)
                self._agent_content_layout.addWidget(code_widget)
            else:
                text_label = QLabel(seg_text)
                text_label.setObjectName("agentMessageText")
                text_label.setWordWrap(True)
                text_label.setTextFormat(Qt.TextFormat.PlainText)
                self._agent_content_layout.addWidget(text_label)

    def append_content(self, delta: str) -> None:
        """Append streaming text delta and rebuild content area."""
        self._content += delta
        self._rebuild_agent_content()

    def mark_complete(self) -> None:
        """Mark streaming as complete — footer copy button becomes available on hover."""
        self._complete = True

    def _copy_content(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._content, QClipboard.Mode.Clipboard)

    def enterEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "_footer") and self._complete:
            self._footer.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "_footer"):
            self._footer.setVisible(False)
        super().leaveEvent(event)

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        return f"{role_text}: {self._content}"
