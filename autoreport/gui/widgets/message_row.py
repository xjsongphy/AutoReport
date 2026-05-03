"""Message cell — VS Code Copilot Chat style.

- User messages: right-aligned rounded bubble (VS Code interactive-request)
- Agent messages: flat layout with avatar icon + content + hover toolbar
- Coordination: muted label above message
- Code blocks: monospace card with copy button (VS Code interactive-result-code-block)
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
    """Split content into segments: (text, None) for text, (code, language) for code."""
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
    """VS Code-style code block card with monospace text and copy button."""

    clicked_copy = None  # set by caller

    def __init__(self, code: str, language: str | None, parent=None):
        super().__init__(parent)
        self._code = code
        self._language = language
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("codeBlockCard")
        self.setStyleSheet("""
            #codeBlockCard {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                margin: 4px 0;
            }
        """)

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

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("codeBlockCopyBtn")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFixedSize(52, 22)
        copy_btn.clicked.connect(self._copy)
        hl.addWidget(copy_btn)

        layout.addWidget(header)

        # Code content
        code_label = QLabel(self._code)
        code_label.setObjectName("codeBlockContent")
        code_label.setWordWrap(False)
        code_label.setTextFormat(Qt.TextFormat.PlainText)
        code_label.setContentsMargins(12, 0, 12, 10)
        code_label.setStyleSheet("""
            #codeBlockContent {
                color: #cccccc;
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
                font-size: 12px;
                line-height: 1.45;
                padding: 8px 12px 10px 12px;
            }
        """)
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
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

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
            ol.addWidget(row)
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
            ol.addWidget(header)

            # Content area with code block parsing
            content_widget = QWidget()
            content_widget.setObjectName("agentMessageRow")
            cl = QVBoxLayout(content_widget)
            cl.setContentsMargins(32, 0, 0, 0)
            cl.setSpacing(0)

            segments = _parse_code_blocks(self._content)
            for seg_text, seg_lang in segments:
                if seg_lang is not None:
                    # Code block segment
                    code_widget = _CodeBlockWidget(seg_text, seg_lang, content_widget)
                    cl.addWidget(code_widget)
                else:
                    # Text segment
                    text_label = QLabel(seg_text)
                    text_label.setObjectName("agentMessageText")
                    text_label.setWordWrap(True)
                    text_label.setTextFormat(Qt.TextFormat.PlainText)
                    cl.addWidget(text_label)

            ol.addWidget(content_widget)

            # Hover footer toolbar
            self._footer = QWidget()
            self._footer.setObjectName("msgFooter")
            fl = QHBoxLayout(self._footer)
            fl.setContentsMargins(32, 4, 0, 0)
            fl.setSpacing(4)

            copy_btn = QPushButton("Copy")
            copy_btn.setObjectName("copyBtn")
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.clicked.connect(self._copy_content)
            copy_btn.setFixedHeight(22)
            fl.addWidget(copy_btn)

            fl.addStretch()
            self._footer.setVisible(False)
            ol.addWidget(self._footer)

        layout.addWidget(outer)

    def _copy_content(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._content, QClipboard.Mode.Clipboard)

    def enterEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "_footer"):
            self._footer.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "_footer"):
            self._footer.setVisible(False)
        super().leaveEvent(event)

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        return f"{role_text}: {self._content}"
