"""Preview widget for displaying file contents."""

from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)


class PreviewWidget(QWidget):
    """Preview widget for file contents."""

    def __init__(self, workspace: Path):
        """Initialize preview widget.

        Args:
            workspace: Project workspace directory.
        """
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self._current_directory = "data"
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title
        title = QLabel("预览")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # Stacked widget for different directory types
        self._content_widget = QWidget()
        layout.addWidget(self._content_widget)

    def set_directory(self, directory: str) -> None:
        """Set current directory to preview.

        Args:
            directory: Directory name (data, refs, theory, code, tex).
        """
        self._current_directory = directory
        logger.debug("Preview directory: {}", directory)

        # Clear and recreate content
        # TODO: Implement directory-specific preview
        layout = self._content_widget.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        new_layout = QVBoxLayout(self._content_widget)

        if directory == "data":
            label = QLabel("数据文件预览")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            new_layout.addWidget(label)
        elif directory == "refs":
            label = QLabel("参考资料预览")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            new_layout.addWidget(label)
        elif directory == "theory":
            label = QLabel("理论推导内容")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            new_layout.addWidget(label)
        elif directory == "code":
            label = QLabel("代码和图片")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            new_layout.addWidget(label)
        elif directory == "tex":
            label = QLabel("LaTeX 源码和 PDF")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            new_layout.addWidget(label)
