"""File tree widget for project directory structure.

Based on VSCode explorer design:
- 22px row height
- 16px icons with proper alignment
- Flexbox-like layout for icon + text
- Text overflow ellipsis
- Subtle hover/focus states
"""

from pathlib import Path

from loguru import logger
from PyQt6.QtCore import QSize, Qt, pyqtSignal
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

# Directory display labels (VSCode style: concise, title case)
DIR_LABELS = {
    "data": "Data",
    "references": "References",
    "theory": "Theory",
    "code": "Code",
    "tex": "Tex",
    "processed": "Processed",
}

# Directory descriptions (for tooltips)
DIR_DESCRIPTIONS = {
    "data": "实验数据",
    "references": "参考资料",
    "theory": "理论推导",
    "code": "代码与图像",
    "tex": "报告",
    "processed": "分析结果",
}


def _draw_folder_icon(color: QColor, size: int = 16) -> QIcon:
    """Draw a VSCode-style folder icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # VSCode folder style - simpler, cleaner
    pen = QPen(color, 1.2)
    p.setPen(pen)
    p.setBrush(QColor(0, 0, 0, 0))

    # Folder back (tab)
    tab = QPainterPath()
    tab.moveTo(1, 3)
    tab.lineTo(1, 1.5)
    tab.quadTo(1, 1, 1.5, 1)
    tab.lineTo(6, 1)
    tab.lineTo(7.5, 2.5)
    tab.lineTo(7.5, 3)
    p.drawPath(tab)

    # Folder body
    body = QPainterPath()
    body.moveTo(0.5, 3)
    body.lineTo(0.5, size - 1.5)
    body.quadTo(0.5, size - 0.5, 1.5, size - 0.5)
    body.lineTo(size - 1.5, size - 0.5)
    body.quadTo(size - 0.5, size - 0.5, size - 0.5, size - 1.5)
    body.lineTo(size - 0.5, 3)
    body.closeSubpath()
    p.drawPath(body)

    p.end()
    return QIcon(pixmap)


def _draw_file_icon(color: QColor, size: int = 16) -> QIcon:
    """Draw a VSCode-style file icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # File body with dog-ear corner (VSCode style)
    pen = QPen(color, 1.2)
    p.setPen(pen)
    p.setBrush(QColor(0, 0, 0, 0))

    body = QPainterPath()
    body.moveTo(2, 1)
    body.lineTo(size - 4.5, 1)
    body.lineTo(size - 1, 4.5)
    body.lineTo(size - 1, size - 1)
    body.lineTo(2, size - 1)
    body.closeSubpath()
    p.drawPath(body)

    # Dog-ear fold
    fold = QPainterPath()
    fold.moveTo(size - 4.5, 1)
    fold.lineTo(size - 4.5, 4.5)
    fold.lineTo(size - 1, 4.5)
    fold.closeSubpath()
    p.setBrush(color.lighter(150))
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
        # VSCode folder color
        _FOLDER_ICON = _draw_folder_icon(QColor("#dcb67a"))
    return _FOLDER_ICON


def _get_file_icon(ext: str) -> QIcon:
    """Get cached file icon by extension (VSCode file colors)."""
    ext = ext.lower()
    if ext not in _FILE_ICONS:
        # VSCode file icon colors
        color_map = {
            ".py": "#3776ab",      # Python blue
            ".txt": "#616161",      # Default gray
            ".md": "#519aba",       # Markdown blue
            ".csv": "#89e059",      # CSV green
            ".json": "#f1e05a",     # JSON yellow
            ".yaml": "#cb171e",     # YAML red
            ".yml": "#cb171e",
            ".tex": "#3d6117",      # LaTeX green
            ".pdf": "#d9373c",      # PDF red
            ".png": "#a074c4",      # Image purple
            ".jpg": "#a074c4",
            ".jpeg": "#a074c4",
            ".gif": "#a074c4",
            ".svg": "#a074c4",
            ".html": "#e34c26",     # HTML orange
            ".css": "#563d7c",      # CSS purple
            ".js": "#f1e05a",       # JS yellow
            ".ts": "#2b7489",       # TS blue
        }
        color = QColor(color_map.get(ext, "#616161"))
        _FILE_ICONS[ext] = _draw_file_icon(color)
    return _FILE_ICONS[ext]


class FileTreeWidget(QWidget):
    """File tree widget showing project structure (VSCode explorer style)."""

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
        """Setup user interface (VSCode explorer style)."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Explorer header (VSCode style)
        header = QWidget()
        header.setObjectName("explorerHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 6)

        title = QLabel("EXPLORER")
        title.setObjectName("explorerTitle")
        header_layout.addWidget(title)

        layout.addWidget(header)

        # File tree
        self.tree = QTreeWidget()
        self.tree.setObjectName("fileTree")
        self.tree.setHeaderLabels(["名称"])
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setIndentation(12)  # VSCode: 12px indentation
        self.tree.setAnimated(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        layout.addWidget(self.tree)

        self.tree.header().hide()

        self._apply_style()

    def _apply_style(self) -> None:
        """Apply VSCode explorer style."""
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        # VSCode color palette
        c = {
            "bg": "#252526" if dark else "#f3f3f3",
            "bg_header": "#252526" if dark else "#f3f3f3",
            "bg_header_alt": "#2d2d2d" if dark else "#ececec",
            "fg": "#cccccc" if dark else "#616161",
            "fg_dim": "#858585" if dark else "#858585",
            "title": "#bbbbbb" if dark else "#616161",
            "border": "#3c3c3c" if dark else "#e0e0e0",
            "hover": "#2a2d2e" if dark else "#e8e8e8",
            "sel_bg": "#094771" if dark else "#cce4f7",
            "sel_fg": "#ffffff" if dark else "#003660",
            "focus_border": "#3794ff" if dark else "#0066bf",
        }

        self.setStyleSheet(f"""
            /* Base styles */
            QWidget {{
                background-color: {c["bg"]};
                color: {c["fg"]};
            }}

            /* Explorer header */
            #explorerHeader {{
                background-color: {c["bg_header"]};
                border-bottom: 1px solid {c["border"]};
            }}

            #explorerTitle {{
                font-size: 11px;
                font-weight: 600;
                color: {c["title"]};
                text-transform: uppercase;
                letter-spacing: 1px;
                padding: 0;
            }}

            /* File tree */
            #fileTree {{
                background-color: {c["bg"]};
                border: none;
                outline: none;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
                selection-background-color: {c["sel_bg"]};
                selection-color: {c["sel_fg"]};
            }}

            /* Tree items - VSCode 22px row height */
            #fileTree::item {{
                height: 22px;
                border: none;
                padding: 0 4px;
                border-radius: 3px;
            }}

            #fileTree::item:hover {{
                background-color: {c["hover"]};
            }}

            #fileTree::item:selected {{
                background-color: {c["sel_bg"]};
                color: {c["sel_fg"]};
            }}

            #fileTree::item:selected:hover {{
                background-color: {c["sel_bg"]};
            }}

            /* Branch arrows (expand/collapse) */
            #fileTree::branch {{
                background: none;
            }}

            #fileTree::branch:has-children:!has-siblings:closed,
            #fileTree::branch:closed:has-children:has-siblings {{
                image: none;
                border: none;
            }}

            #fileTree::branch:open:has-children:!has-siblings,
            #fileTree::branch:open:has-children:has-siblings {{
                image: none;
                border: none;
            }}

            /* Scrollbar */
            QScrollBar:vertical {{
                background-color: {c["bg"]};
                width: 10px;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background-color: {c["fg_dim"]};
                min-height: 30px;
                border-radius: 5px;
            }}

            QScrollBar::handle:vertical:hover {{
                background-color: {c["fg"]};
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        # Set row height
        self.tree.setIconSize(QSize(16, 16))

    def _init_directories(self) -> None:
        """Initialize fixed directory structure."""
        for dir_name in FIXED_DIRECTORIES:
            dir_path = self.workspace / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

            item = QTreeWidgetItem(self.tree)
            item.setText(0, DIR_LABELS.get(dir_name, dir_name))
            item.setIcon(0, _get_folder_icon())
            item.setData(0, Qt.ItemDataRole.UserRole, dir_name)
            item.setToolTip(0, DIR_DESCRIPTIONS.get(dir_name, dir_name))
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
                processed_item.setToolTip(0, DIR_DESCRIPTIONS.get("processed", ""))
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

        # Add files and subdirectories (sorted: dirs first, then files, case-insensitive)
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
                child.setToolTip(0, entry.name)

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
