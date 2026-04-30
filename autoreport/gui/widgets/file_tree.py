"""File tree widget for project directory structure."""

from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Fixed directory structure
FIXED_DIRECTORIES = ["data", "references", "theory", "code", "tex"]


class FileTreeWidget(QWidget):
    """File tree widget showing project structure."""

    directory_selected = pyqtSignal(str)
    file_selected = pyqtSignal(Path)  # New signal for file selection

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
        self.tree.itemExpanded.connect(self._on_item_expanded)
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
        if not dir_name:
            return

        # Check if this is a file
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path_str:
            # This is a file click
            file_path = Path(file_path_str)
            if file_path.is_file():
                self.file_selected.emit(file_path)

                # Also emit directory for preview context
                top_level = dir_name.split("/")[0]
                if top_level in FIXED_DIRECTORIES:
                    self.directory_selected.emit(top_level)
            return

        # Extract top-level directory
        top_level = dir_name.split("/")[0]

        # Check if this is a directory or file
        if "/" in dir_name:
            # This is a subdirectory
            self.directory_selected.emit(top_level)
        elif dir_name in FIXED_DIRECTORIES:
            # This is a top-level directory
            self.directory_selected.emit(dir_name)
        else:
            # This might be a file (when we add file support)
            logger.debug("Item clicked: {}", dir_name)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Handle item expansion to load files.

        Args:
            item: Expanded tree item.
        """
        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not dir_name:
            return

        # Get directory path
        if "/" in dir_name:
            dir_path = self.workspace / dir_name
        else:
            dir_path = self.workspace / dir_name

        if not dir_path.is_dir():
            return

        # Clear existing children (they will be re-added)
        while item.childCount() > 0:
            item.removeChild(item.child(0))

        # Add files and subdirectories
        try:
            for entry in sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                # Skip hidden files and processed directory (already added)
                if entry.name.startswith(".") or entry.name == "processed":
                    continue

                child = QTreeWidgetItem(item)
                child.setText(0, entry.name)

                if entry.is_dir():
                    child.setIcon(0, self._get_directory_icon(entry.name))
                    child.setData(0, Qt.ItemDataRole.UserRole, str(entry.relative_to(self.workspace)))
                    # Add placeholder child to show expand indicator
                    QTreeWidgetItem(child)
                else:
                    # File
                    child.setIcon(0, self._get_file_icon(entry))
                    child.setData(0, Qt.ItemDataRole.UserRole, str(entry.parent.relative_to(self.workspace)))

                    # Store full file path for selection
                    child.setData(0, Qt.ItemDataRole.UserRole + 1, str(entry))

        except PermissionError as e:
            logger.warning("Permission denied accessing {}: {}", dir_path, e)

    def _get_file_icon(self, file_path: Path) -> QIcon:
        """Get icon for file.

        Args:
            file_path: File path.

        Returns:
            QIcon for file.
        """
        from PyQt6.QtGui import QPixmap

        # Color-code by extension
        ext = file_path.suffix.lower()
        color_map = {
            ".py": Qt.GlobalColor.blue,
            ".txt": Qt.GlobalColor.gray,
            ".md": Qt.GlobalColor.darkGreen,
            ".csv": Qt.GlobalColor.green,
            ".json": Qt.GlobalColor.yellow,
            ".yaml": Qt.GlobalColor.yellow,
            ".yml": Qt.GlobalColor.yellow,
            ".tex": Qt.GlobalColor.red,
            ".pdf": Qt.GlobalColor.darkRed,
            ".png": Qt.GlobalColor.magenta,
            ".jpg": Qt.GlobalColor.magenta,
            ".jpeg": Qt.GlobalColor.magenta,
        }

        pixmap = QPixmap(16, 16)
        pixmap.fill(color_map.get(ext, Qt.GlobalColor.lightGray))
        return QIcon(pixmap)

    def refresh(self) -> None:
        """Refresh file tree contents."""
        # Collapse and re-expand items to refresh
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            was_expanded = item.isExpanded()
            if was_expanded:
                item.setExpanded(False)
                item.setExpanded(True)

    def get_selected_file(self) -> Path | None:
        """Get currently selected file path.

        Returns:
            Selected file path or None.
        """
        item = self.tree.currentItem()
        if not item:
            return None

        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path_str:
            return Path(file_path_str)
        return None
