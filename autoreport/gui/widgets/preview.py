"""Preview widget for displaying file contents with selection tracking."""

from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal
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
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self._current_directory = "data"
        self._current_file: Path | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab bar header (VSCode editor tab style)
        header = QWidget()
        header.setObjectName("previewHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 4)

        self._title_label = QLabel("预览")
        self._title_label.setObjectName("previewTitle")
        header_layout.addWidget(self._title_label)

        self._file_label = QLabel()
        self._file_label.setObjectName("previewFile")
        self._file_label.setVisible(False)
        header_layout.addWidget(self._file_label)

        layout.addWidget(header)

        # Editor
        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.setObjectName("previewEditor")
        self._editor.selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._editor, 1)

        self._apply_style()

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        c = {
            "bg": "#1e1e1e" if dark else "#ffffff",
            "header": "#252526" if dark else "#f3f3f3",
            "border": "#3c3c3c" if dark else "#e0e0e0",
            "title": "#ffffff" if dark else "#1a1a1a",
            "file": "#858585" if dark else "#888888",
            "fg": "#d4d4d4" if dark else "#333333",
            "sel_bg": "#264f78" if dark else "#add6ff",
            "sel_fg": "#ffffff" if dark else "#000000",
        }

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {c["bg"]};
            }}
            #previewHeader {{
                background-color: {c["header"]};
                border-bottom: 1px solid {c["border"]};
            }}
            #previewTitle {{
                font-size: 13px;
                font-weight: 600;
                color: {c["title"]};
            }}
            #previewFile {{
                font-size: 11px;
                color: {c["file"]};
                font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            }}
            #previewEditor {{
                background-color: {c["bg"]};
                border: none;
                color: {c["fg"]};
                font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
                font-size: 13px;
                padding: 8px;
                selection-background-color: {c["sel_bg"]};
                selection-color: {c["sel_fg"]};
            }}
        """)

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
