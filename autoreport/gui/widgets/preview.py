"""Preview widget for displaying file contents with selection tracking."""

from pathlib import Path

from loguru import logger
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class PreviewWidget(QWidget):
    """Enhanced preview widget with text editing and selection tracking."""

    # Signal emitted when text is selected: (file_path, selected_text, start_line, end_line)
    selection_changed = pyqtSignal(str, str, int, int)

    def __init__(self, workspace: Path):
        """Initialize preview widget.

        Args:
            workspace: Project workspace directory.
        """
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self._current_directory = "data"
        self._current_file: Path | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title
        title = QLabel("预览")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # File label
        self._file_label = QLabel()
        self._file_label.setStyleSheet("color: gray; font-size: 11px;")
        self._file_label.setVisible(False)
        layout.addWidget(self._file_label)

        # Text editor for content
        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.selectionChanged.connect(self._on_selection_changed)
        self._editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
                font-size: 12px;
            }
        """)
        layout.addWidget(self._editor)

    def set_directory(self, directory: str) -> None:
        """Set current directory to preview.

        Args:
            directory: Directory name (data, references, theory, code, tex).
        """
        self._current_directory = directory
        self._current_file = None
        self._file_label.setVisible(False)
        self._editor.clear()
        logger.debug("Preview directory: {}", directory)

        # Show directory prompt
        prompts = {
            "data": "数据文件预览 - 从左侧选择文件",
            "references": "参考资料预览 - 从左侧选择文件",
            "theory": "理论推导内容 - 从左侧选择文件",
            "code": "代码和图片 - 从左侧选择文件",
            "tex": "LaTeX 源码和 PDF - 从左侧选择文件",
        }
        self._editor.setPlaceholderText(prompts.get(directory, "从左侧选择文件"))

    def load_file(self, file_path: Path) -> None:
        """Load file into editor.

        Args:
            file_path: Path to file to load.
        """
        self._current_file = Path(file_path).resolve()
        self._file_label.setText(f"文件: {self._current_file.relative_to(self.workspace)}")
        self._file_label.setVisible(True)

        try:
            # Try to read as text
            content = self._current_file.read_text(encoding="utf-8", errors="replace")
            self._editor.setPlainText(content)
            logger.debug("Loaded file: {}", self._current_file)
        except Exception as e:
            self._editor.setPlainText(f"无法读取文件: {e}")
            logger.error("Failed to load file {}: {}", self._current_file, e)

    def _on_selection_changed(self) -> None:
        """Handle selection change in editor."""
        if not self._current_file:
            return

        cursor = self._editor.textCursor()
        selected_text = cursor.selectedText()

        if not selected_text:
            return

        # Get line numbers
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        start_cursor = QTextCursor(self._editor.document())
        start_cursor.setPosition(start)
        start_line = start_cursor.blockNumber() + 1

        end_cursor = QTextCursor(self._editor.document())
        end_cursor.setPosition(end)
        end_line = end_cursor.blockNumber() + 1

        # Emit signal
        rel_path = str(self._current_file.relative_to(self.workspace))
        self.selection_changed.emit(rel_path, selected_text, start_line, end_line)

    def get_selected_context(self) -> tuple[str, str, int, int] | None:
        """Get current selection context.

        Returns:
            Tuple of (file_path, selected_text, start_line, end_line) or None.
        """
        if not self._current_file:
            return None

        cursor = self._editor.textCursor()
        selected_text = cursor.selectedText()

        if not selected_text:
            return None

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        start_cursor = QTextCursor(self._editor.document())
        start_cursor.setPosition(start)
        start_line = start_cursor.blockNumber() + 1

        end_cursor = QTextCursor(self._editor.document())
        end_cursor.setPosition(end)
        end_line = end_cursor.blockNumber() + 1

        rel_path = str(self._current_file.relative_to(self.workspace))
        return (rel_path, selected_text, start_line, end_line)

    def clear_selection(self) -> None:
        """Clear current selection."""
        cursor = self._editor.textCursor()
        cursor.clearSelection()
        self._editor.setTextCursor(cursor)

    @property
    def current_directory(self) -> str:
        """Get current directory."""
        return self._current_directory

    @property
    def current_file(self) -> Path | None:
        """Get current file path."""
        return self._current_file
