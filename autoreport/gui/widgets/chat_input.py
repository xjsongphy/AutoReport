"""Enhanced chat input widget with @ file reference support."""

from pathlib import Path
from typing import override

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit


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
        self.setMinimumHeight(28)
        self.setMaximumHeight(100)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )
        self.document().setDocumentMargin(0)

        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        input_bg = "#1f1f1f" if dark else "#ffffff"
        input_fg = "#cccccc" if dark else "#616161"
        input_border = "#3c3c3c" if dark else "#e0e0e0"
        focus_border = "#0078d4" if dark else "#0090ff"

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid {input_border};
                border-radius: 8px;
                padding: 4px 6px;
                background-color: {input_bg};
                color: {input_fg};
                font-size: 13px;
                font-family: "Segoe UI", "SF Pro", sans-serif;
            }}
            QPlainTextEdit:focus {{
                border: 1px solid {focus_border};
            }}
        """)

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()

        # Popup navigation: forward to popup, don't insert into text
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
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End):
                # Allow cursor movement + re-check token
                super().keyPressEvent(event)
                self._check_current_token()
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

        cursor = self.textCursor()
        cursor.setPosition(start)
        rect = self.cursorRect(cursor)
        global_pos = self.mapToGlobal(rect.bottomLeft())

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
        cursor = self.textCursor()
        position = cursor.position()
        document = self.document()

        # Walk backwards to find the @ or / prefix, tracking start position
        start = position
        while start > 0:
            char = document.characterAt(start - 1)
            if char in ("@", "/"):
                start -= 1  # Point to the @/ character itself
                break
            elif char in " \t\n\r":
                return "", -1, -1
            elif char in "()[]{}<>\"'":
                return "", -1, -1
            start -= 1
        else:
            return "", -1, -1

        # Walk forwards from cursor to find token end (exclude trailing paragraph sep)
        end = position
        doc_len = document.characterCount()
        while end < doc_len - 1:  # -1 excludes the implicit paragraph separator
            char = document.characterAt(end)
            if char in " \t\n\r()[]{}<>\"'":
                break
            end += 1

        cursor.setPosition(start, QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        token = cursor.selectedText()

        space_before = False
        if start == 0:
            space_before = True
        else:
            char_before = document.characterAt(start - 1)
            space_before = char_before in " \t\n\r"

        if space_before and token:
            return token, start, end

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

        # Use document character positions (not Python string len)
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

    def get_plain_text(self) -> str:
        return self.toPlainText()

    def clear_text(self) -> None:
        self.clear()
