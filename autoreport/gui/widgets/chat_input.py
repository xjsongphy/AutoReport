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
        """Setup user interface."""
        self.setPlaceholderText("输入消息… (@ 引用文件, Enter 发送)")
        self.setMinimumHeight(40)
        self.setMaximumHeight(120)

        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        # Claude Code theme colors
        claude_orange = "#d97757"
        border = "#3c3c3c" if dark else "#e0e0e0"
        bg = "#252526" if dark else "#ffffff"
        fg = "#cccccc" if dark else "#1a1a1a"
        placeholder = "#858585" if dark else "#858585"

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid {border};
                border-radius: 8px;
                padding: 8px 10px;
                background-color: {bg};
                color: {fg};
                font-size: 13px;
            }}
            QPlainTextEdit:focus {{
                border: 1px solid {claude_orange};
            }}
        """)

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press events.

        Args:
            event: Key event.
        """
        # If popup is active, intercept navigation keys
        if self._popup_active:
            match event.key():
                case Qt.Key.Key_Up | Qt.Key.Key_Down | Qt.Key.Key_Enter | Qt.Key.Key_Return | Qt.Key.Key_Escape:
                    # Don't insert these characters, let parent handle them
                    # for popup navigation
                    super().keyPressEvent(event)
                    return

        # Handle Enter to send (Ctrl+Enter for newline)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key.Enter):
            modifiers = event.modifiers()
            if modifiers == Qt.KeyboardModifier.NoModifier:
                # Enter sends message
                self.send_message.emit()
                return
            elif modifiers == Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier:
                # Ctrl+Shift+Enter for newline
                cursor = self.textCursor()
                cursor.insertText("\n")
                return

        # Handle backspace to clear @ token
        if event.key() == Qt.Key.Key_Backspace:
            cursor = self.textCursor()
            if cursor.hasSelection():
                super().keyPressEvent(event)
                self._check_for_at_token()
                return
            else:
                # Check if we're deleting the @ symbol
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor)
                char = cursor.selectedText()
                if char == "@":
                    # Clear the token tracking
                    self._on_popup_closed()
                super().keyPressEvent(event)
                self._check_for_at_token()
                return

        # Default handling
        super().keyPressEvent(event)

        # Check for @ token after character insertion
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
