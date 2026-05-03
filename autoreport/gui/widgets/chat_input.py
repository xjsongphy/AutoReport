"""Enhanced chat input widget with @ file reference support."""

from pathlib import Path
from typing import override

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit


class ChatInput(QPlainTextEdit):
    """Enhanced input widget with @ file reference support.

    Detects @ symbol and triggers file search popup.
    Styled to match VS Code's .chat-input-container.
    """

    # Signal emitted when @ token is detected: (query, cursor_global_position)
    file_reference_requested = pyqtSignal(str, QPoint)

    # Signal emitted when user wants to send message
    send_message = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_active = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setPlaceholderText("Message Copilot…")
        # VS Code: single-line start, auto-expand max 4 lines
        self.setMinimumHeight(28)
        self.setMaximumHeight(100)  # ~4 lines
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )
        self.document().setDocumentMargin(0)

        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        # Match VS Code CSS variables
        input_bg = "#1e1e1e" if dark else "#ffffff"
        input_fg = "#cccccc" if dark else "#616161"
        input_border = "#3c3c3c" if dark else "#e0e0e0"
        focus_border = "#007fd4" if dark else "#0090ff"
        placeholder_fg = "#6e7681" if dark else "#8b949e"

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid {input_border};
                border-radius: 8px;
                /* VS Code: padding: 0 6px 6px 6px — top padding inside editor */
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

        if self._popup_active:
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Escape, Qt.Key.Key_Enter, Qt.Key.Key_Return):
                super().keyPressEvent(event)
                return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                cursor = self.textCursor()
                cursor.insertText("\n")
                return
            elif modifiers == Qt.KeyboardModifier.NoModifier:
                self.send_message.emit()
                return

        if key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
            super().keyPressEvent(event)
            self._check_for_at_token()
            return

        super().keyPressEvent(event)

        if event.text():
            self._check_for_at_token()

    def _check_for_at_token(self) -> None:
        token, start, end = self.current_prefixed_token()

        if token and token.startswith("@"):
            query = token[1:] if len(token) > 1 else ""
            cursor = self.textCursor()
            cursor.setPosition(start)
            rect = self.cursorRect(cursor)
            global_pos = self.mapToGlobal(rect.bottomLeft())
            self.file_reference_requested.emit(query, global_pos)
            self._popup_active = True
        else:
            self._on_popup_closed()

    def current_prefixed_token(self) -> tuple[str, int, int]:
        cursor = self.textCursor()
        position = cursor.position()
        document = self.document()

        start = position
        while start > 0:
            char = document.characterAt(start - 1)
            if char == "@":
                break
            elif char in " \t\n\r":
                return "", -1, -1
            elif char in "()[]{}<>\"'":
                return "", -1, -1
            start -= 1
        else:
            return "", -1, -1

        end = position
        while end < document.characterCount():
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

        if space_before:
            return token, start, end

        return "", -1, -1

    def insert_file_reference(self, file_path: Path) -> None:
        token, start, end = self.current_prefixed_token()

        if token and token.startswith("@"):
            try:
                rel_path = file_path.relative_to(Path.cwd())
            except ValueError:
                rel_path = file_path

            filename = file_path.name
            link = f"[@{filename}](project://{rel_path})"

            cursor = self.textCursor()
            cursor.setPosition(start, QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(link)

            cursor.setPosition(start + len(link))
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
