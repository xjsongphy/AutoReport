"""File tree widget for project directory structure."""

from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Fixed directory structure
FIXED_DIRECTORIES = ["data", "references", "theory", "code", "tex"]

# Directory display labels
DIR_LABELS = {
    "data": "数据 (data)",
    "references": "参考资料 (references)",
    "theory": "理论推导 (theory)",
    "code": "代码与图像 (code)",
    "tex": "报告 (tex)",
    "processed": "分析结果 (processed)",
}


def _draw_folder_icon(color: QColor, size: int = 64) -> QIcon:
    """Draw a folder icon with the given color."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 2)
    p.setPen(pen)
    p.setBrush(color.lighter(160))
    # Folder back (tab)
    tab = QPainterPath()
    tab.moveTo(6, 14)
    tab.lineTo(6, 10)
    tab.quadTo(6, 6, 10, 6)
    tab.lineTo(24, 6)
    tab.lineTo(28, 10)
    tab.lineTo(28, 14)
    p.drawPath(tab)
    # Folder body
    body = QPainterPath()
    body.moveTo(4, 14)
    body.lineTo(4, size - 6)
    body.quadTo(4, size - 4, 6, size - 4)
    body.lineTo(size - 6, size - 4)
    body.quadTo(size - 4, size - 4, size - 4, size - 6)
    body.lineTo(size - 4, 14)
    body.closeSubpath()
    p.drawPath(body)
    p.end()
    return QIcon(pixmap)


def _draw_file_icon(color: QColor, size: int = 64) -> QIcon:
    """Draw a file icon with the given color."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 2)
    p.setPen(pen)
    # File body with dog-ear corner
    body = QPainterPath()
    body.moveTo(8, 4)
    body.lineTo(size - 18, 4)
    body.lineTo(size - 4, 18)
    body.lineTo(size - 4, size - 4)
    body.lineTo(8, size - 4)
    body.closeSubpath()
    p.drawPath(body)
    # Dog-ear fold triangle
    fold = QPainterPath()
    fold.moveTo(size - 18, 4)
    fold.lineTo(size - 18, 18)
    fold.lineTo(size - 4, 18)
    fold.closeSubpath()
    p.setBrush(color.lighter(140))
    p.drawPath(fold)
    p.end()
    return QIcon(pixmap)


# Icon cache
_FOLDER_ICON: QIcon | None = None
_FILE_ICONS: dict[str, QIcon] = {}


def _get_folder_icon() -> QIcon:
    """Get cached folder icon."""
    global _FOLDER_ICON
    if _FOLDER_ICON is None:
        _FOLDER_ICON = _draw_folder_icon(QColor("#e8a84c"))
    return _FOLDER_ICON


def _get_file_icon(ext: str) -> QIcon:
    """Get cached file icon by extension."""
    ext = ext.lower()
    if ext not in _FILE_ICONS:
        color_map = {
            ".py": "#3572a5",
            ".txt": "#888",
            ".md": "#083fa1",
            ".csv": "#36a33b",
            ".json": "#e8a84c",
            ".yaml": "#cb171e",
            ".yml": "#cb171e",
            ".tex": "#3d6117",
            ".pdf": "#b00",
            ".png": "#a040a0",
            ".jpg": "#a040a0",
            ".jpeg": "#a040a0",
        }
        color = QColor(color_map.get(ext, "#999"))
        _FILE_ICONS[ext] = _draw_file_icon(color)
    return _FILE_ICONS[ext]


class FileTreeWidget(QWidget):
    """File tree widget showing project structure."""

    directory_selected = pyqtSignal(str)
    file_selected = pyqtSignal(Path)

    def __init__(self, workspace: Path):
        """Initialize file tree widget.

        Args:
            workspace: Project workspace directory.
        """
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self._setup_ui()
        self._init_directories()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar header bar (VSCode explorer style)
        header = QWidget()
        header.setObjectName("sidebarHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 6)

        title = QLabel("资源管理器")
        title.setObjectName("sidebarTitle")
        header_layout.addWidget(title)

        layout.addWidget(header)

        self.tree = QTreeWidget()
        self.tree.setObjectName("fileTree")
        self.tree.setHeaderLabels(["名称"])
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setIndentation(16)
        self.tree.setAnimated(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        layout.addWidget(self.tree)

        self.tree.header().hide()

        self._apply_style()

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        c = {
            "bg": "#252526" if dark else "#f3f3f3",
            "border": "#3c3c3c" if dark else "#e0e0e0",
            "title": "#bbbbbb" if dark else "#616161",
            "fg": "#cccccc" if dark else "#333333",
            "hover": "#2a2d2e" if dark else "#e8e8e8",
            "sel": "#094771" if dark else "#cce4f7",
            "sel_fg": "#ffffff" if dark else "#000000",
        }

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {c["bg"]};
            }}
            #sidebarHeader {{
                background-color: {c["bg"]};
                border-bottom: 1px solid {c["border"]};
            }}
            #sidebarTitle {{
                font-size: 11px;
                font-weight: 600;
                color: {c["title"]};
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            #fileTree {{
                background-color: {c["bg"]};
                border: none;
                color: {c["fg"]};
                font-size: 13px;
                outline: none;
            }}
            #fileTree::item {{
                padding: 3px 4px;
                border: none;
            }}
            #fileTree::item:hover {{
                background-color: {c["hover"]};
            }}
            #fileTree::item:selected {{
                background-color: {c["sel"]};
                color: {c["sel_fg"]};
            }}
            #fileTree::branch {{
                background-color: {c["bg"]};
            }}
            #fileTree::branch:has-children:!has-siblings:closed,
            #fileTree::branch:closed:has-children:has-siblings {{
                border-image: none;
                image: none;
            }}
            #fileTree::branch:open:has-children:!has-siblings,
            #fileTree::branch:open:has-children:has-siblings {{
                border-image: none;
                image: none;
            }}
        """)

    def _init_directories(self) -> None:
        """Initialize fixed directory structure."""
        for dir_name in FIXED_DIRECTORIES:
            dir_path = self.workspace / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

            item = QTreeWidgetItem(self.tree)
            item.setText(0, DIR_LABELS.get(dir_name, dir_name))
            item.setIcon(0, _get_folder_icon())
            item.setData(0, Qt.ItemDataRole.UserRole, dir_name)
            # Add placeholder child to show expand indicator
            QTreeWidgetItem(item)

            # Add subdirectory for data/processed
            if dir_name == "data":
                processed_path = dir_path / "processed"
                processed_path.mkdir(parents=True, exist_ok=True)

                processed_item = QTreeWidgetItem(item)
                processed_item.setText(0, DIR_LABELS.get("processed", "processed"))
                processed_item.setIcon(0, _get_folder_icon())
                processed_item.setData(0, Qt.ItemDataRole.UserRole, "data/processed")
                QTreeWidgetItem(processed_item)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item click."""
        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not dir_name:
            return

        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path_str:
            file_path = Path(file_path_str)
            if file_path.is_file():
                self.file_selected.emit(file_path)
                top_level = dir_name.split("/")[0]
                if top_level in FIXED_DIRECTORIES:
                    self.directory_selected.emit(top_level)
            return

        top_level = dir_name.split("/")[0]
        if "/" in dir_name:
            self.directory_selected.emit(top_level)
        elif dir_name in FIXED_DIRECTORIES:
            self.directory_selected.emit(dir_name)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Handle item expansion to load files."""
        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not dir_name:
            return

        dir_path = self.workspace / dir_name
        if not dir_path.is_dir():
            return

        # Clear existing children
        while item.childCount() > 0:
            child = item.child(0)
            item.removeChild(child)

        # Add files and subdirectories
        try:
            entries = sorted(
                dir_path.iterdir(),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
            for entry in entries:
                if entry.name.startswith("."):
                    continue

                child = QTreeWidgetItem(item)
                child.setText(0, entry.name)

                if entry.is_dir():
                    child.setIcon(0, _get_folder_icon())
                    rel = str(entry.relative_to(self.workspace))
                    child.setData(0, Qt.ItemDataRole.UserRole, rel)
                    # Placeholder child to show expand indicator
                    QTreeWidgetItem(child)
                else:
                    child.setIcon(0, _get_file_icon(entry.suffix))
                    rel = str(entry.parent.relative_to(self.workspace))
                    child.setData(0, Qt.ItemDataRole.UserRole, rel)
                    child.setData(0, Qt.ItemDataRole.UserRole + 1, str(entry))

        except PermissionError as e:
            logger.warning("Permission denied accessing {}: {}", dir_path, e)

    def refresh(self) -> None:
        """Refresh file tree contents."""
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.isExpanded():
                item.setExpanded(False)
                item.setExpanded(True)

    def get_selected_file(self) -> Path | None:
        """Get currently selected file path."""
        item = self.tree.currentItem()
        if not item:
            return None
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path_str:
            return Path(file_path_str)
        return None
