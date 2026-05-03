"""Enhanced chat input widget with @ file reference support."""

from pathlib import Path
from typing import override

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit


class ChatInput(QPlainTextEdit):
    """Enhanced input widget with @ file reference support.

    Detects @ symbol and triggers file search popup.
    Based on Codex's chat_composer pattern.
    """

    # Signal emitted when @ token is detected: (query, cursor_global_position)
    file_reference_requested = pyqtSignal(str, QPoint)

    # Signal emitted when user wants to send message
    send_message = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize chat input widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._popup_active = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setPlaceholderText("Message…  (@ file, Enter send)")
        self.setMinimumHeight(36)
        self.setMaximumHeight(160)

        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        # Codex/GitHub palette
        input_bg = "#0d1117" if dark else "#ffffff"
        input_fg = "#e6edf3" if dark else "#1f2328"
        input_border = "#30363d" if dark else "#d0d7de"
        focus_border = "#58a6ff" if dark else "#0969da"

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid {input_border};
                border-radius: 8px;
                padding: 6px 10px;
                background-color: {input_bg};
                color: {input_fg};
                font-size: 13px;
                font-family: "Segoe UI", "SF Pro", sans-serif;
            }}
            QPlainTextEdit:focus {{
                border: 2px solid {focus_border};
                padding: 5px 9px;
            }}
        """)

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press events.

        Args:
            event: Key event.
        """
        key = event.key()
        modifiers = event.modifiers()

        # If popup is active, let popup handle navigation keys
        if self._popup_active:
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Escape, Qt.Key.Key_Enter, Qt.Key.Key_Return):
                super().keyPressEvent(event)
                return

        # Handle Enter/Return keys
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Check for Shift modifier (including Ctrl+Shift, etc.)
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter (or Ctrl+Shift+Enter): insert newline
                cursor = self.textCursor()
                cursor.insertText("\n")
                return
            elif modifiers == Qt.KeyboardModifier.NoModifier:
                # Plain Enter: send message
                self.send_message.emit()
                return
            # Other combinations fall through to default

        # Handle backspace/delete for @ token tracking
        if key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
            # Let default handling happen first
            super().keyPressEvent(event)
            # Then check for @ token state
            self._check_for_at_token()
            return

        # Default handling for other keys
        super().keyPressEvent(event)

        # Check for @ token after text insertion
        if event.text():
            self._check_for_at_token()

    def _check_for_at_token(self) -> None:
        """Check if cursor is at or after an @ token and emit signal if found."""
        token, start, end = self.current_prefixed_token()

        if token and token.startswith("@"):
            # Extract query (everything after @)
            query = token[1:] if len(token) > 1 else ""

            # Get cursor position for popup
            cursor = self.textCursor()
            cursor.setPosition(start)

            # Calculate global position for popup
            rect = self.cursorRect(cursor)
            global_pos = self.mapToGlobal(rect.bottomLeft())

            self.file_reference_requested.emit(query, global_pos)
            self._popup_active = True
        else:
            self._on_popup_closed()

    def current_prefixed_token(self) -> tuple[str, int, int]:
        """Find @ token near cursor position.

        Similar to Codex's current_prefixed_token() function.

        Returns:
            Tuple of (token_text, start_position, end_position).
            Returns ("", -1, -1) if no @ token found.
        """
        cursor = self.textCursor()
        position = cursor.position()
        document = self.document()

        # Scan backwards from cursor to find @
        start = position
        while start > 0:
            char = document.characterAt(start - 1)
            if char == "@":
                # Found @ symbol
                break
            elif char in " \t\n\r":
                # Hit whitespace, no @ token
                return "", -1, -1
            elif char in "()[]{}<>\"'":
                # Hit punctuation, no @ token
                return "", -1, -1
            start -= 1
        else:
            # Didn't find @ symbol
            return "", -1, -1

        # Now scan forward to find end of token
        end = position
        while end < document.characterCount():
            char = document.characterAt(end)
            if char in " \t\n\r()[]{}<>\"'":
                break
            end += 1

        # Extract token text
        cursor.setPosition(start, QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        token = cursor.selectedText()

        # Verify space before @ (or @ at start of line/document)
        space_before = False
        if start == 0:
            space_before = True
        else:
            char_before = document.characterAt(start - 1)
            space_before = char_before in " \t\n\r"

        # Only trigger if @ has space before or is at start
        if space_before:
            return token, start, end

        return "", -1, -1

    def insert_file_reference(self, file_path: Path) -> None:
        """Insert file reference markdown link at current cursor position.

        Args:
            file_path: File path to reference.
        """
        token, start, end = self.current_prefixed_token()

        if token and token.startswith("@"):
            # Replace @ token with markdown link
            try:
                rel_path = file_path.relative_to(Path.cwd())
            except ValueError:
                rel_path = file_path

            # Format: [@filename](project://path/to/file)
            filename = file_path.name
            link = f"[@{filename}](project://{rel_path})"

            cursor = self.textCursor()
            cursor.setPosition(start, QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(link)

            # Move cursor after inserted link
            cursor.setPosition(start + len(link))
            self.setTextCursor(cursor)

        self._on_popup_closed()

    def _on_popup_closed(self) -> None:
        """Handle popup being closed."""
        self._popup_active = False

    def set_popup_active(self, active: bool) -> None:
        """Set popup active state (external control).

        Args:
            active: Whether popup is active.
        """
        self._popup_active = active

    def get_plain_text(self) -> str:
        """Get plain text content.

        Returns:
            Plain text content of input.
        """
        return self.toPlainText()

    def clear_text(self) -> None:
        """Clear text content."""
        self.clear()
