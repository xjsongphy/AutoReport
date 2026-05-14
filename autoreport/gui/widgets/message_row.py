"""Message cell — VS Code Copilot Chat style.

- User messages: right-aligned rounded bubble
- Agent messages: flat layout with avatar + markdown content + bottom copy
- Code blocks: monospace card with right-side copy icon (hover visible)
"""

import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QClipboard, QColor, QIcon

from ..scale import scaled_size
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
)

from .markdown_renderer import render_markdown
from ..theme import get_theme_colors
from .ui_utils import install_compact_tooltip, render_svg_icon


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


def _copy_icon() -> QIcon:
    return render_svg_icon("copy", QColor(get_theme_colors()["muted"]), size=16)


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

        w, h = scaled_size(30, 24)
        self._copy_btn = QPushButton()
        self._copy_btn.setObjectName("codeBlockCopyBtn")
        self._copy_btn.setIcon(_copy_icon())
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setFixedSize(w, h)
        install_compact_tooltip(self._copy_btn, "Copy")
        self._copy_btn.clicked.connect(self._copy)
        hl.addWidget(self._copy_btn)

        layout.addWidget(header)

        # Code content
        code_label = QLabel(self._code)
        code_label.setObjectName("codeBlockContent")
        code_label.setWordWrap(True)
        code_label.setTextFormat(Qt.TextFormat.PlainText)
        code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
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

    # Signal emitted when user saves an edit (content, row_widget)
    edit_saved = pyqtSignal(str, object)

    # Signal emitted when user cancels an edit
    edit_cancelled = pyqtSignal()

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
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
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
        self._wrapping_labels: list[QLabel] = []
        self._summary_btn: QPushButton | None = None
        self._detail_widget: QWidget | None = None
        self._editing = False  # Track if in edit mode
        self._original_text_widget: QWidget | None = None  # Store original widget when editing
        self._edit_widget: QPlainTextEdit | None = None  # Edit mode widget
        self._save_btn: QPushButton | None = None  # Save button in edit mode
        self._cancel_btn: QPushButton | None = None  # Cancel button in edit mode
        self._setup_ui()
        self._setup_hover_handler()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        outer = QWidget()
        outer.setObjectName("msgOuterContainer")
        outer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._outer_layout = QVBoxLayout(outer)
        self._outer_layout.setContentsMargins(16, 6, 16, 6)
        self._outer_layout.setSpacing(0)

        if self._is_coordination:
            coord = QLabel("[Main Agent → Sub Agent]")
            coord.setObjectName("msgCoordination")
            self._outer_layout.addWidget(coord)

        if self._is_outbound_message():
            row = QWidget()
            row.setObjectName("userMessageRow")
            row.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)
            rl.addStretch(1)

            self._user_bubble_container = QWidget()
            self._user_bubble_container.setObjectName("userMessageBubbleContainer")
            self._user_bubble_container.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Preferred,
            )
            bcl = QVBoxLayout(self._user_bubble_container)
            bcl.setContentsMargins(0, 0, 0, 0)
            bcl.setSpacing(0)

            bubble = QWidget()
            bubble.setObjectName("userMessageBubble")
            bubble.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
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
                text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                text.setTextFormat(Qt.TextFormat.PlainText)
                text.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                text.setMinimumWidth(0)
                c = get_theme_colors()
                text.setStyleSheet(f"color: {c['editor_fg']}; background-color: transparent;")
                bl.addWidget(text)

            bcl.addWidget(bubble)

            # Footer with edit/copy buttons (hover visible, right-aligned)
            self._user_footer = QWidget()
            self._user_footer.setObjectName("userMsgFooter")
            fl = QHBoxLayout(self._user_footer)
            fl.setContentsMargins(0, 2, 0, 4)
            fl.setSpacing(2)

            fl.addStretch()

            w, h = scaled_size(30, 24)
            self._edit_btn = QPushButton("✎")
            self._edit_btn.setObjectName("userEditBtn")
            self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            install_compact_tooltip(self._edit_btn, "Edit & Resend")
            self._edit_btn.setFixedSize(w, h)
            self._edit_btn.clicked.connect(self._request_edit)
            fl.addWidget(self._edit_btn)

            self._user_copy_btn = QPushButton()
            self._user_copy_btn.setObjectName("userCopyBtn")
            self._user_copy_btn.setIcon(_copy_icon())
            self._user_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._user_copy_btn.setFixedSize(w, h)
            install_compact_tooltip(self._user_copy_btn, "Copy")
            self._user_copy_btn.clicked.connect(self._copy_content)
            fl.addWidget(self._user_copy_btn)

            bcl.addWidget(self._user_footer)
            self._set_user_actions_visible(False)

            rl.addWidget(self._user_bubble_container, 0, Qt.AlignmentFlag.AlignRight)
            rl.setAlignment(self._user_bubble_container, Qt.AlignmentFlag.AlignRight)
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

            # Copy button at bottom — shown on hover, right-aligned
            self._footer = QWidget()
            self._footer.setObjectName("msgFooter")
            fl = QHBoxLayout(self._footer)
            fl.setContentsMargins(32, 4, 4, 0)
            fl.setSpacing(4)

            fl.addStretch()

            w, h = scaled_size(30, 24)
            self._copy_btn = QPushButton()
            self._copy_btn.setObjectName("copyBtn")
            self._copy_btn.setIcon(_copy_icon())
            self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            install_compact_tooltip(self._copy_btn, "Copy")
            self._copy_btn.clicked.connect(self._copy_content)
            self._copy_btn.setFixedSize(w, h)
            fl.addWidget(self._copy_btn)
            self._set_agent_actions_visible(False)
            self._outer_layout.addWidget(self._footer)

        layout.addWidget(outer)

    def _clear_agent_content(self) -> None:
        self._wrapping_labels = []
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
                text_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                text_label.setTextFormat(Qt.TextFormat.RichText)
                text_label.setOpenExternalLinks(True)
                text_label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                text_label.setContentsMargins(0, 2, 0, 4)
                text_label.setMinimumWidth(0)
                self._wrapping_labels.append(text_label)
                self._agent_content_layout.addWidget(text_label)
        self._apply_text_width_constraints()

    def append_content(self, delta: str) -> None:
        """Append streaming text delta and rebuild content area."""
        self._content += delta
        self._rebuild_agent_content()
        self._apply_text_width_constraints()

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
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            label.setContentsMargins(0, 2, 0, 4)
            label.setMinimumWidth(0)
            self._wrapping_labels.append(label)
        else:
            label = QLabel(self._detail or "")
            label.setObjectName("userMessageText")
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            label.setMinimumWidth(0)
            c = get_theme_colors()
            label.setStyleSheet(f"color: {c['editor_fg']}; background-color: transparent;")
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
        """Mark streaming complete — enable hover-triggered actions."""
        self._complete = True
        if hasattr(self, "_footer"):
            self._footer.setVisible(True)
            self._set_agent_actions_visible(False)
        if self._user_footer:
            self._set_user_actions_visible(False)

    def set_editable(self, editable: bool) -> None:
        """Set whether this user message can be edited.

        Only the most recent user message should be editable.
        """
        if self._role != "user":
            return
        self._editable = editable
        if self._complete and self._user_footer:
            self._edit_btn.setVisible(editable)
            self._set_user_actions_visible(False)

    def _request_edit(self) -> None:
        """Enter edit mode for this user message."""
        if self._role == "user" and self._editable:
            self.enter_edit_mode()

    def enter_edit_mode(self) -> None:
        """Replace text with editable widget in-place."""
        if not self._is_outbound_message() or self._editing:
            return

        self._editing = True
        self._set_user_actions_visible(False)  # Hide edit/copy buttons

        # Find the text label in the bubble
        if self._user_bubble_container is None:
            self._editing = False
            return

        bubble = self._user_bubble_container.findChild(QWidget, "userMessageBubble")
        if not bubble:
            self._editing = False
            return

        c = get_theme_colors()
        edit_style = f"color: {c['editor_fg']}; background-color: {c['editor_bg']}; border: 1px solid {c['border']}; border-radius: 4px; padding: 4px;"

        # Find the original text widget
        if self._summary is None:
            # Simple text case - find the userMessageText label
            text_widget = bubble.findChild(QLabel, "userMessageText")
            if text_widget:
                self._original_text_widget = text_widget
                edit = QPlainTextEdit(self._content)
                edit.setObjectName("userMessageEdit")
                edit.setPlainText(self._content)
                edit.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                edit.setStyleSheet(edit_style)
                self._edit_widget = edit
        else:
            # Summary/detail case - need to edit the detail widget
            if self._detail_widget:
                detail_label = self._detail_widget.findChild(QLabel, "userMessageText")
                if detail_label:
                    self._original_text_widget = detail_label
                    edit = QPlainTextEdit(self._detail or "")
                    edit.setObjectName("userMessageEdit")
                    edit.setPlainText(self._detail or "")
                    edit.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                    edit.setStyleSheet(edit_style)
                    self._edit_widget = edit

        # Guard: if no edit widget was created, abort edit mode
        if not self._edit_widget:
            self._editing = False
            self._set_user_actions_visible(True)
            return

        # Swap original widget with edit widget in layout
        orig_layout = self._original_text_widget.parent().layout()
        if orig_layout:
            index = orig_layout.indexOf(self._original_text_widget)
            orig_layout.removeWidget(self._original_text_widget)
            self._original_text_widget.setParent(None)
            orig_layout.insertWidget(index, self._edit_widget)
            self._edit_widget.setFocus()
            self._edit_widget.setMinimumWidth(0)

        # Change footer to Save/Cancel buttons
        if self._user_footer:
            layout = self._user_footer.layout()
            if layout:
                while layout.count():
                    item = layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

                w, h = scaled_size(40, 24)
                self._save_btn = QPushButton("Save")
                self._save_btn.setObjectName("userSaveBtn")
                self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self._save_btn.setFixedSize(w, h)
                self._save_btn.clicked.connect(self._save_edit)
                layout.addWidget(self._save_btn)

                self._cancel_btn = QPushButton("Cancel")
                self._cancel_btn.setObjectName("userCancelBtn")
                self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self._cancel_btn.setFixedSize(w, h)
                self._cancel_btn.clicked.connect(self._cancel_edit)
                layout.addWidget(self._cancel_btn)

            self._user_footer.setVisible(True)

    def _save_edit(self) -> None:
        """Save the edited content and emit signal."""
        if not self._editing or not self._edit_widget:
            return

        new_content = self._edit_widget.toPlainText()
        self._content = new_content  # Update stored content
        self.exit_edit_mode()
        self.edit_saved.emit(new_content, self)

    def _cancel_edit(self) -> None:
        """Cancel editing and restore original content."""
        if not self._editing:
            return
        self.exit_edit_mode()
        self.edit_cancelled.emit()

    def exit_edit_mode(self) -> None:
        """Restore original text widget and footer buttons."""
        if not self._editing:
            return

        self._editing = False

        # Restore original widget
        if self._original_text_widget and self._edit_widget:
            edit_layout = self._edit_widget.parent().layout()
            if edit_layout:
                index = edit_layout.indexOf(self._edit_widget)
                edit_layout.removeWidget(self._edit_widget)
                self._edit_widget.setParent(None)
                self._edit_widget.deleteLater()
                self._edit_widget = None
                edit_layout.insertWidget(index, self._original_text_widget)
            self._original_text_widget = None

        # Restore original footer buttons
        if self._user_footer:
            layout = self._user_footer.layout()
            if layout:
                while layout.count():
                    item = layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

                w, h = scaled_size(30, 24)
                layout.addStretch()

                self._edit_btn = QPushButton("✎")
                self._edit_btn.setObjectName("userEditBtn")
                self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                install_compact_tooltip(self._edit_btn, "Edit & Resend")
                self._edit_btn.setFixedSize(w, h)
                self._edit_btn.clicked.connect(self._request_edit)
                self._edit_btn.setEnabled(self._editable)
                layout.addWidget(self._edit_btn)

                self._user_copy_btn = QPushButton()
                self._user_copy_btn.setObjectName("userCopyBtn")
                self._user_copy_btn.setIcon(_copy_icon())
                self._user_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self._user_copy_btn.setFixedSize(w, h)
                install_compact_tooltip(self._user_copy_btn, "Copy")
                self._user_copy_btn.clicked.connect(self._copy_content)
                layout.addWidget(self._user_copy_btn)

            self._set_user_actions_visible(False)

    def _copy_content(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._content, QClipboard.Mode.Clipboard)

    def contextMenuEvent(self, event) -> None:
        """Show VS Code-like context menu for message actions."""
        menu = QMenu(self)
        c = get_theme_colors()
        menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: {c["surface"]};
                color: {c["fg"]};
                border: 1px solid {c["border"]};
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                padding: 6px 10px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}
            """
        )

        copy_action = menu.addAction("Copy")
        copy_action.triggered.connect(self._copy_content)

        if self._role == "user" and self._editable:
            edit_action = menu.addAction("Edit & Resend")
            edit_action.triggered.connect(self._request_edit)

        menu.exec(event.globalPos())
        event.accept()

    def _setup_hover_handler(self) -> None:
        """Setup hover detection for user message buttons."""
        if not self._is_outbound_message() or self._user_footer is None:
            return
        self._user_bubble_container.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle hover events for user message bubble container."""
        if not self._is_outbound_message():
            return super().eventFilter(obj, event)

        if obj == self._user_bubble_container:
            if event.type() == event.Type.Enter:
                if self._complete and self._user_footer:
                    self._set_user_actions_visible(True)
            elif event.type() == event.Type.Leave:
                if self._user_footer:
                    self._set_user_actions_visible(False)

        return super().eventFilter(obj, event)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self._is_outbound_message():
            if self._complete and self._user_footer:
                self._set_user_actions_visible(True)
        else:
            if self._complete:
                self._set_agent_actions_visible(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._is_outbound_message():
            if self._user_footer:
                self._set_user_actions_visible(False)
        else:
            self._set_agent_actions_visible(False)

    def _set_user_actions_visible(self, visible: bool) -> None:
        if not self._user_footer:
            return
        self._user_footer.setVisible(visible)
        if visible:
            edit_visible = self._editable
            self._edit_btn.setText("✎" if edit_visible else "")
            self._edit_btn.setEnabled(edit_visible)
            self._user_copy_btn.setIcon(_copy_icon())
            self._user_copy_btn.setEnabled(True)

    def _set_agent_actions_visible(self, visible: bool) -> None:
        if not hasattr(self, "_copy_btn"):
            return
        self._footer.setVisible(True)
        self._copy_btn.setEnabled(visible)
        self._copy_btn.setIcon(_copy_icon() if visible else QIcon())

    def resizeEvent(self, event) -> None:
        """Keep message content constrained to current panel width."""
        super().resizeEvent(event)
        self._apply_text_width_constraints()
        if self._is_outbound_message() and self._user_bubble_container is not None:
            width = max(80, int(self.width() * 0.45))
            self._user_bubble_container.setFixedWidth(width)

    def _is_outbound_message(self) -> bool:
        """Right-side messages sent to an agent share the user bubble layout."""
        return self._role == "user"

    def _apply_text_width_constraints(self) -> None:
        max_w = max(40, self._content_width_limit())
        for label in self._wrapping_labels:
            label.setMaximumWidth(max_w)

    def _content_width_limit(self) -> int:
        return self.width() - 56

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        return f"{role_text}: {self._content}"

    def is_expanded(self) -> bool:
        return self._expanded
