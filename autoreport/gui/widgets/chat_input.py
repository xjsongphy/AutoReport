"""Enhanced chat input widget with @ file reference support."""

from pathlib import Path
from typing import override

from PyQt6.QtCore import QMimeData, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QInputMethodEvent, QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from ..theme import get_theme_colors, scrollbar_stylesheet


class ChatInput(QPlainTextEdit):
    """Enhanced input widget with @ file reference and / command support.

    Detects @ symbol → triggers file/agent search popup.
    Detects / → triggers command palette popup.
    Styled to match VS Code's .chat-input-container.
    """

    file_reference_requested = pyqtSignal(str, QPoint)
    command_palette_requested = pyqtSignal(str, QPoint)
    send_message = pyqtSignal()
    popup_navigate = pyqtSignal(str)  # "up" | "down" | "select" | "cancel"
    height_changed = pyqtSignal(int)
    _MIN_LINES = 1
    _MAX_LINES = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_active = False
        self._popup_kind: str = ""  # "@" or "/"
        self._base_placeholder = "Message…  (@ file, / command)"
        self._composing = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setPlaceholderText(self._base_placeholder)
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )
        self.document().setDocumentMargin(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        c = get_theme_colors()

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                border: none;
                border-radius: 0;
                padding: 6px 8px;
                background-color: transparent;
                color: {c["fg"]};
                font-size: 13px;
                font-family: "Segoe UI", "SF Pro", sans-serif;
            }}
            QPlainTextEdit:focus {{
                border: none;
            }}
            {scrollbar_stylesheet(
                selector="QPlainTextEdit QScrollBar",
                orientation="vertical",
                background_color="transparent",
                thickness="8px",
                min_handle_extent="20px",
                radius="4px",
                colors=c,
            )}
        """)
        self.textChanged.connect(self._sync_after_text_change)
        layout = self.document().documentLayout()
        if layout is not None:
            layout.documentSizeChanged.connect(lambda _size: self._schedule_sync())
        self._sync_after_text_change()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_height()

    def setPlaceholderText(self, placeholder: str) -> None:  # noqa: N802
        self._base_placeholder = placeholder
        super().setPlaceholderText(placeholder)
        self._update_placeholder_visibility()

    def inputMethodEvent(self, event: QInputMethodEvent) -> None:  # noqa: N802
        self._composing = bool(event.preeditString())
        self._update_placeholder_visibility()
        super().inputMethodEvent(event)
        self._composing = bool(event.preeditString())
        self._schedule_sync()

    def _schedule_sync(self) -> None:
        QTimer.singleShot(0, self._sync_after_text_change)

    def _sync_after_text_change(self) -> None:
        self._update_placeholder_visibility()
        self._update_height()
        self.ensureCursorVisible()
        self.updateGeometry()
        self.height_changed.emit(self.height())

    def _update_placeholder_visibility(self) -> None:
        if self._composing or self.toPlainText():
            placeholder = ""
        else:
            placeholder = self._base_placeholder
        if self.placeholderText() != placeholder:
            super().setPlaceholderText(placeholder)

    def _update_height(self) -> None:
        metrics = self.fontMetrics()
        line_h = metrics.lineSpacing()
        # Vertical chrome around the text: stylesheet padding (contents margins)
        # + the plain-text frame + the document margin. All derived from the
        # widget itself, so no hardcoded magic numbers to drift out of sync.
        cm = self.contentsMargins()
        overhead = (
            cm.top() + cm.bottom()
            + self.frameWidth() * 2
            + int(self.document().documentMargin() * 2)
        )

        content_h = self._content_pixel_height()
        max_content_h = self._MAX_LINES * line_h
        visible_h = min(content_h, max_content_h)
        target = int(round(visible_h)) + overhead
        self.setFixedHeight(target)

        # Show the vertical scrollbar only when content truly overflows the
        # capped height. A half-line hysteresis avoids flicker at the boundary.
        needs_scroll = content_h > max_content_h + (line_h * 0.5)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn if needs_scroll else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def _content_pixel_height(self) -> float:
        """Total pixel height of all (wrapped) content.

        ``QPlainTextDocumentLayout.documentSize().height()`` does NOT return
        pixels, so wrapping was never counted (long pasted lines failed to grow
        the box). ``blockBoundingRect`` forces each block to lay out and returns
        its true wrapped height, so this works for both explicit newlines and
        word-wrap. Always at least one line.
        """
        line_h = max(1, self.fontMetrics().lineSpacing())
        total = 0.0
        block = self.document().firstBlock()
        while block.isValid():
            total += self.blockBoundingRect(block).height()
            block = block.next()
        return max(line_h, total)

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()

        # When popup is active, only intercept up/down/enter/escape.
        # Left/Right/Home/End pass through to move cursor normally.
        if self._popup_active:
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                direction = "up" if key == Qt.Key.Key_Up else "down"
                self.popup_navigate.emit(direction)
                return
            if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                self.popup_navigate.emit("select")
                return
            if key == Qt.Key.Key_Escape:
                self.popup_navigate.emit("cancel")
                return

        # Send on Enter (no Shift)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                cursor = self.textCursor()
                cursor.insertText("\n")
                return
            elif modifiers == Qt.KeyboardModifier.NoModifier:
                if self._popup_active:
                    self.popup_navigate.emit("select")
                else:
                    self.send_message.emit()
                return

        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            super().keyPressEvent(event)
            self._check_current_token()
            return

        super().keyPressEvent(event)

        if event.text() or key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
        ):
            self._check_current_token()

    def insertFromMimeData(self, source: QMimeData | None) -> None:  # noqa: N802
        super().insertFromMimeData(source)
        self._schedule_sync()

    def _check_current_token(self) -> None:
        """Check for @ or / prefix token and emit appropriate signal."""
        token, start, end = self.current_prefixed_token()

        if not token:
            self._on_popup_closed()
            return

        # Emit position: top-left of input (popup appears above the input field)
        global_pos = self.mapToGlobal(self.rect().topLeft())

        if token.startswith("@"):
            query = token[1:] if len(token) > 1 else ""
            self._popup_kind = "@"
            self.file_reference_requested.emit(query, global_pos)
            self._popup_active = True
        elif token.startswith("/"):
            query = token[1:] if len(token) > 1 else ""
            self._popup_kind = "/"
            self.command_palette_requested.emit(query, global_pos)
            self._popup_active = True
        else:
            self._on_popup_closed()

    def current_prefixed_token(self) -> tuple[str, int, int]:
        """Find @ or / prefixed token spanning the cursor position.

        Searches backwards (inclusive of cursor position) for a @ or /
        at a word boundary, then forwards to find the token end.
        Returns (token, start_pos, end_pos) or ("", -1, -1).
        """
        cursor = self.textCursor()
        position = cursor.position()
        document = self.document()
        doc_len = document.characterCount()

        # Search backwards (inclusive) for @ or / at a word boundary
        prefix_pos = -1
        search_pos = min(position, doc_len - 2)  # -2: skip trailing paragraph sep

        while search_pos >= 0:
            char = document.characterAt(search_pos)
            if char in ("@", "/"):
                # Must be at a word boundary (start of doc or preceded by space)
                if search_pos == 0 or document.characterAt(search_pos - 1) in " \t\n\r":
                    prefix_pos = search_pos
                    break
                # @/ inside a word (e.g. email@example) — keep searching
            elif char in " \t\n\r":
                break  # Hit a space — no prefix token before cursor
            search_pos -= 1

        if prefix_pos < 0:
            return "", -1, -1

        # Find end of token (stop at space, bracket, or paragraph end)
        end = prefix_pos + 1
        while end < doc_len - 1:  # -1: exclude paragraph separator
            char = document.characterAt(end)
            if char in " \t\n\r()[]{}<>\"'":
                break
            end += 1

        cursor.setPosition(prefix_pos, QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        token = cursor.selectedText()

        if token:
            return token, prefix_pos, end
        return "", -1, -1

    def insert_file_reference(self, file_path: Path) -> None:
        try:
            rel_path = file_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = file_path

        filename = file_path.name
        link = f"[@{filename}](project://{rel_path})"

        if not self._replace_current_prefixed_token(link):
            self._on_popup_closed()
            return
        self._on_popup_closed()

    def insert_agent_reference(self, name: str) -> None:
        mention = f"@{name} "
        if not self._replace_current_prefixed_token(mention):
            self._on_popup_closed()
            return
        self._on_popup_closed()

    def _replace_current_prefixed_token(self, replacement: str) -> bool:
        token, start, end = self.current_prefixed_token()
        if not token or start < 0 or end < 0:
            return False

        text = self.toPlainText()
        if replacement.endswith(" ") and end < len(text) and text[end] in " \t\n\r":
            replacement = replacement.rstrip(" ")

        cursor = self.textCursor()
        cursor.setPosition(start, QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(replacement)
        self.setTextCursor(cursor)
        return True

    def _on_popup_closed(self) -> None:
        self._popup_active = False
        self._popup_kind = ""

    def set_popup_active(self, active: bool) -> None:
        self._popup_active = active

    def set_text(self, text: str) -> None:
        """Set the input field text content."""
        self.setPlainText(text)

    def get_plain_text(self) -> str:
        return self.toPlainText()

    def clear_text(self) -> None:
        self.clear()
