"""Message cell — VS Code Copilot Chat style.

- User messages: right-aligned rounded bubble
- Agent messages: flat layout with avatar + markdown content + bottom copy
- Code blocks: monospace card with right-side copy icon (hover visible)
"""

import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QClipboard

from ..scale import scaled_size
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .markdown_renderer import render_markdown


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
    """VS Code-style code block with right-side hover-visible copy icon."""

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

        # Header bar with language label (left) and copy icon (right)
        header = QWidget()
        header.setObjectName("codeBlockHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 4, 4, 4)
        hl.setSpacing(8)

        lang_label = QLabel(self._language or "code")
        lang_label.setObjectName("codeBlockLang")
        hl.addWidget(lang_label)
        hl.addStretch()

        w, h = scaled_size(28, 20)
        self._copy_btn = QPushButton("⎘")
        self._copy_btn.setObjectName("codeBlockCopyBtn")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setFixedSize(w, h)
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
    """Render a chat message matching VS Code Copilot Chat's visual style."""

    # Signal emitted when user clicks edit button on their message
    edit_requested = pyqtSignal(str)

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str = "",
        is_coordination: bool = False,
        agent_name: str = "Agent",
        summary: str | None = None,
        detail: str | None = None,
        expandable: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._role = role
        self._content = content
        self._timestamp = timestamp
        self._is_coordination = is_coordination
        self._agent_name = agent_name
        self._complete = False
        self._agent_content_layout: QVBoxLayout | None = None
        self._user_footer: QWidget | None = None
        self._editable = False
        self._user_bubble_container: QWidget | None = None
        self._summary = summary
        self._detail = detail
        self._expandable = expandable
        self._expanded = False
        self._summary_btn: QPushButton | None = None
        self._detail_widget: QWidget | None = None
        self._setup_ui()
        self._setup_hover_handler()

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

            self._user_bubble_container = QWidget()
            self._user_bubble_container.setObjectName("userMessageBubbleContainer")
            bcl = QVBoxLayout(self._user_bubble_container)
            bcl.setContentsMargins(0, 0, 0, 0)
            bcl.setSpacing(0)

            bubble = QWidget()
            bubble.setObjectName("userMessageBubble")
            bl = QVBoxLayout(bubble)
            bl.setContentsMargins(8, 8, 12, 8)
            bl.setSpacing(0)

            if self._summary is not None:
                bl.addWidget(self._build_summary_widget("user"))
                self._detail_widget = self._build_detail_widget("user")
                bl.addWidget(self._detail_widget)
                self._detail_widget.setVisible(False)
            else:
                text = QLabel(self._content)
                text.setObjectName("userMessageText")
                text.setWordWrap(True)
                text.setTextFormat(Qt.TextFormat.PlainText)
                bl.addWidget(text)

            bcl.addWidget(bubble)

            # Footer with edit/copy buttons (hover visible)
            self._user_footer = QWidget()
            self._user_footer.setObjectName("userMsgFooter")
            fl = QHBoxLayout(self._user_footer)
            fl.setContentsMargins(8, 2, 12, 4)
            fl.setSpacing(4)

            w, h = scaled_size(28, 20)
            self._edit_btn = QPushButton("✎")
            self._edit_btn.setObjectName("userEditBtn")
            self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._edit_btn.setToolTip("Edit & Resend")
            self._edit_btn.setFixedSize(w, h)
            self._edit_btn.clicked.connect(self._request_edit)
            fl.addWidget(self._edit_btn)

            self._user_copy_btn = QPushButton("⎘")
            self._user_copy_btn.setObjectName("userCopyBtn")
            self._user_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._user_copy_btn.setToolTip("Copy")
            self._user_copy_btn.setFixedSize(w, h)
            self._user_copy_btn.clicked.connect(self._copy_content)
            fl.addWidget(self._user_copy_btn)

            bcl.addWidget(self._user_footer)
            self._user_footer.setVisible(False)

            rl.addWidget(self._user_bubble_container, 0)
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

            username = QLabel(self._agent_name)
            username.setObjectName("agentUsername")
            hl.addWidget(username)
            hl.addStretch()
            self._outer_layout.addWidget(header)

            # Content area — rebuilt via _rebuild_agent_content
            self._agent_content_layout = QVBoxLayout()
            self._agent_content_layout.setContentsMargins(32, 0, 0, 0)
            self._agent_content_layout.setSpacing(0)
            self._outer_layout.addLayout(self._agent_content_layout)
            self._rebuild_agent_content()

            # Copy button at bottom, always visible after complete (VS Code: .chat-footer-toolbar)
            self._footer = QWidget()
            self._footer.setObjectName("msgFooter")
            fl = QHBoxLayout(self._footer)
            fl.setContentsMargins(32, 4, 0, 0)
            fl.setSpacing(4)

            w, h = scaled_size(28, 24)
            self._copy_btn = QPushButton("⎘")
            self._copy_btn.setObjectName("copyBtn")
            self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._copy_btn.setToolTip("Copy")
            self._copy_btn.clicked.connect(self._copy_content)
            self._copy_btn.setFixedSize(w, h)
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

        if self._summary is not None:
            self._agent_content_layout.addWidget(self._build_summary_widget("agent"))
            self._detail_widget = self._build_detail_widget("agent")
            self._agent_content_layout.addWidget(self._detail_widget)
            self._detail_widget.setVisible(self._expanded and self._has_detail())
            return

        segments = _parse_code_blocks(self._content)
        for seg_text, seg_lang in segments:
            if seg_lang is not None:
                code_widget = _CodeBlockWidget(seg_text, seg_lang)
                self._agent_content_layout.addWidget(code_widget)
            else:
                # Render markdown text
                html = render_markdown(seg_text)
                text_label = QLabel(html)
                text_label.setObjectName("agentMessageText")
                text_label.setWordWrap(True)
                text_label.setTextFormat(Qt.TextFormat.RichText)
                text_label.setOpenExternalLinks(True)
                text_label.setContentsMargins(0, 2, 0, 4)
                self._agent_content_layout.addWidget(text_label)

    def append_content(self, delta: str) -> None:
        """Append streaming text delta and rebuild content area."""
        self._content += delta
        self._rebuild_agent_content()

    def _has_detail(self) -> bool:
        return bool(self._detail)

    def _summary_arrow(self) -> str:
        if not (self._expandable and self._has_detail()):
            return "-"
        return "v" if self._expanded else ">"

    def _build_summary_widget(self, summary_type: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._summary_btn = QPushButton(f"{self._summary_arrow()} {self._summary or ''}")
        self._summary_btn.setObjectName("toolCallHeader" if summary_type == "agent" else "userCopyBtn")
        self._summary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._summary_btn.clicked.connect(self._toggle_summary)
        self._summary_btn.setEnabled(self._expandable and self._has_detail())
        layout.addWidget(self._summary_btn)
        layout.addStretch()
        return widget

    def _build_detail_widget(self, detail_type: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 2, 0, 0)
        layout.setSpacing(0)

        if detail_type == "agent":
            html = render_markdown(self._detail or "")
            label = QLabel(html)
            label.setObjectName("agentMessageText")
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setOpenExternalLinks(True)
            label.setContentsMargins(0, 2, 0, 4)
        else:
            label = QLabel(self._detail or "")
            label.setObjectName("userMessageText")
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(label)
        return widget

    def _toggle_summary(self) -> None:
        if not (self._expandable and self._has_detail()):
            return
        self._expanded = not self._expanded
        if self._detail_widget:
            self._detail_widget.setVisible(self._expanded)
        if self._summary_btn:
            self._summary_btn.setText(f"{self._summary_arrow()} {self._summary or ''}")

    def mark_complete(self) -> None:
        """Mark streaming complete — show copy button at bottom."""
        self._complete = True
        if hasattr(self, "_footer"):
            self._footer.setVisible(True)
        # User footer buttons are shown on hover (via eventFilter)
        # but we need to mark them as ready
        if self._user_footer:
            self._user_copy_btn.setVisible(True)
            self._edit_btn.setVisible(self._editable)
            # Initially hide footer - will show on hover
            self._user_footer.setVisible(False)

    def set_editable(self, editable: bool) -> None:
        """Set whether this user message can be edited.

        Only the most recent user message should be editable.
        """
        if self._role != "user":
            return
        self._editable = editable
        if self._complete and self._user_footer:
            self._edit_btn.setVisible(editable)

    def _request_edit(self) -> None:
        """Emit edit_requested signal with current content."""
        if self._role == "user":
            self.edit_requested.emit(self._content)

    def _copy_content(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._content, QClipboard.Mode.Clipboard)

    def _setup_hover_handler(self) -> None:
        """Setup hover detection for user message buttons."""
        if self._role != "user" or self._user_footer is None:
            return
        self._user_bubble_container.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle hover events for user message bubble container."""
        if self._role != "user":
            return super().eventFilter(obj, event)

        if obj == self._user_bubble_container:
            if event.type() == event.Type.Enter:
                if self._complete and self._user_footer:
                    self._user_footer.setVisible(True)
            elif event.type() == event.Type.Leave:
                if self._user_footer:
                    self._user_footer.setVisible(False)

        return super().eventFilter(obj, event)

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        return f"{role_text}: {self._content}"

    def is_expanded(self) -> bool:
        return self._expanded
