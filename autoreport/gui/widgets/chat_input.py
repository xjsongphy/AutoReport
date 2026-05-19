"""Enhanced chat input widget with @ file reference support."""

from pathlib import Path
from typing import override

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from ..theme import get_theme_colors


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_active = False
        self._popup_kind: str = ""  # "@" or "/"
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setPlaceholderText("Message…  (@ file, / command)")
        self.setMinimumHeight(64)
        self.setMaximumHeight(64)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )
        self.document().setDocumentMargin(0)

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
        """)

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

        if event.text():
            self._check_current_token()

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
        text = self.toPlainText()
        kind = getattr(self, "_popup_kind", "@")
        at_idx = text.rfind(kind)
        if at_idx < 0:
            self._on_popup_closed()
            return

        try:
            rel_path = file_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = file_path

        filename = file_path.name
        link = f"[@{filename}](project://{rel_path})"

        end = at_idx + 1
        while end < len(text) and text[end] not in " \t\n\r":
            end += 1

        doc_len = self.document().characterCount()
        cursor = self.textCursor()
        cursor.setPosition(at_idx, QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(min(end, doc_len - 1), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(link)
        self.setTextCursor(cursor)
        self._on_popup_closed()

    def insert_agent_reference(self, name: str) -> None:
        text = self.toPlainText()
        kind = getattr(self, "_popup_kind", "@")
        at_idx = text.rfind(kind)
        if at_idx < 0:
            self._on_popup_closed()
            return

        mention = f"@{name} "
        end = at_idx + 1
        while end < len(text) and text[end] not in " \t\n\r":
            end += 1

        doc_len = self.document().characterCount()
        cursor = self.textCursor()
        cursor.setPosition(at_idx, QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(min(end, doc_len - 1), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(mention)
        self.setTextCursor(cursor)
        self._on_popup_closed()

    def _on_popup_closed(self) -> None:
        self._popup_active = False

    def set_popup_active(self, active: bool) -> None:
        self._popup_active = active

    def set_text(self, text: str) -> None:
        """Set the input field text content."""
        self.setPlainText(text)

    def get_plain_text(self) -> str:
        return self.toPlainText()

    def clear_text(self) -> None:
        self.clear()
