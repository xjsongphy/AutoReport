"""File tree widget for project directory structure."""

from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QDragEnterEvent, QDropEvent


# Fixed directory structure
FIXED_DIRECTORIES = ["data", "references", "theory", "code", "tex"]


class FileTreeWidget(QWidget):
    """File tree widget showing project structure."""

    directory_selected = pyqtSignal(str)

    def __init__(self, workspace: Path):
        """Initialize file tree widget.

        Args:
            workspace: Project workspace directory.
        """
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self._setup_ui()

        # Initialize directories
        self._init_directories()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title
        title = QLabel("项目文件")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["名称", "大小"])
        self.tree.setColumnWidth(0, 150)
        self.tree.setColumnWidth(1, 60)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

        # Hide header
        self.tree.header().hide()

    def _init_directories(self) -> None:
        """Initialize fixed directory structure."""
        for dir_name in FIXED_DIRECTORIES:
            dir_path = self.workspace / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

            item = QTreeWidgetItem(self.tree)
            item.setText(0, dir_name)
            item.setIcon(0, self._get_directory_icon(dir_name))
            item.setData(0, Qt.ItemDataRole.UserRole, dir_name)

            # Add subdirectory for data/processed
            if dir_name == "data":
                processed_path = dir_path / "processed"
                processed_path.mkdir(parents=True, exist_ok=True)

                processed_item = QTreeWidgetItem(item)
                processed_item.setText(0, "processed")
                processed_item.setIcon(0, self._get_directory_icon("processed"))
                processed_item.setData(0, Qt.ItemDataRole.UserRole, "data/processed")

    def _get_directory_icon(self, dir_name: str) -> QIcon:
        """Get icon for directory.

        Args:
            dir_name: Directory name.

        Returns:
            QIcon for directory.
        """
        # TODO: Add proper icons
        from PyQt6.QtGui import QPixmap
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.gray)
        return QIcon(pixmap)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item click.

        Args:
            item: Clicked tree item.
            column: Column index.
        """
        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        if dir_name:
            # Extract top-level directory
            top_level = dir_name.split("/")[0]
            self.directory_selected.emit(top_level)

    def refresh(self) -> None:
        """Refresh file tree contents."""
        # TODO: Implement file listing
        pass
