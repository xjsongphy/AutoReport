"""File tree widget for project directory structure.

Based on VSCode explorer design:
- 22px row height
- 16px icons with proper alignment
- Flexbox-like layout for icon + text
- Text overflow ellipsis
- Subtle hover/focus states
- Qt built-in branch indicators (selection extends to branch area)
- Drag and drop file import support
"""

import shutil
from pathlib import Path

from loguru import logger
from PyQt6.QtCore import QFileSystemWatcher, QMimeData, QRectF, QSize, Qt, pyqtSignal

from autoreport.utils.logging_config import ui_logger
from PyQt6.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..theme import get_theme_colors


# ================================================================== #
#  VSCode-style SVG icon rendering
# ================================================================== #


def _draw_codicon_icon(name: str, color: QColor, size: int = 16) -> QIcon:
    """Draw a VSCode Codicon icon using SVG vector rendering.

    Loads the SVG files from the codicons package and renders them as
    vector graphics for smooth, scalable icons.
    """
    from PyQt6.QtSvg import QSvgRenderer
    from pathlib import Path

    # Map icon names to SVG files
    svg_files = {
        "new-file": "new-file.svg",
        "new-folder": "new-folder.svg",
        "refresh": "refresh.svg",
        "collapse-all": None,  # Not used currently
    }

    svg_file = svg_files.get(name)
    if not svg_file:
        # Fallback: simple text icon
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setPen(color)
        p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "?")
        p.end()
        return QIcon(pixmap)

    # Get SVG file path (relative to this file)
    svg_path = Path(__file__).parent / svg_file

    # Load and render SVG
    renderer = QSvgRenderer(str(svg_path))

    # Create high-DPI pixmap using device pixel ratio for crisp rendering
    app = QApplication.instance()
    dpr = float(app.devicePixelRatio() if app else 1.0)
    px_size = max(1, int(round(size * dpr)))
    pixmap = QPixmap(px_size, px_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Apply color by using composition mode
    # First render the icon in grayscale, then tint it
    renderer.render(p, QRectF(0.0, 0.0, float(px_size), float(px_size)))

    # Tint the rendered icon with the desired color
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(pixmap.rect(), color)

    p.end()

    return QIcon(pixmap)

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


class _ChevronTreeWidget(QTreeWidget):
    """QTreeWidget with drag-drop support for the file tree."""

    def __init__(self, file_tree_widget=None, parent=None):
        super().__init__(parent)
        self._file_tree_widget = file_tree_widget

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter - accept file URLs."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Handle drag move - accept file URLs."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop - process dropped files."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            if self._file_tree_widget:
                self._file_tree_widget._handle_drop(event)
        super().dropEvent(event)


def _get_file_icon(ext: str, style: QStyle = None) -> QIcon:
    """Get file icon by extension using QStyle standard icons."""
    if style is None:
        from PyQt6.QtWidgets import QApplication
        style = QApplication.style()

    ext = ext.lower()
    # Map extensions to QStyle standard icons
    icon_map = {
        ".py": QStyle.StandardPixmap.SP_FileIcon,
        ".txt": QStyle.StandardPixmap.SP_FileIcon,
        ".md": QStyle.StandardPixmap.SP_FileIcon,
        ".csv": QStyle.StandardPixmap.SP_FileIcon,
        ".json": QStyle.StandardPixmap.SP_FileIcon,
        ".yaml": QStyle.StandardPixmap.SP_FileIcon,
        ".yml": QStyle.StandardPixmap.SP_FileIcon,
        ".tex": QStyle.StandardPixmap.SP_FileIcon,
        ".pdf": QStyle.StandardPixmap.SP_FileIcon,
        ".png": QStyle.StandardPixmap.SP_FileIcon,
        ".jpg": QStyle.StandardPixmap.SP_FileIcon,
        ".jpeg": QStyle.StandardPixmap.SP_FileIcon,
        ".gif": QStyle.StandardPixmap.SP_FileIcon,
        ".svg": QStyle.StandardPixmap.SP_FileIcon,
        ".bmp": QStyle.StandardPixmap.SP_FileIcon,
        ".html": QStyle.StandardPixmap.SP_FileIcon,
        ".css": QStyle.StandardPixmap.SP_FileIcon,
        ".js": QStyle.StandardPixmap.SP_FileIcon,
        ".ts": QStyle.StandardPixmap.SP_FileIcon,
    }
    standard_icon = icon_map.get(ext, QStyle.StandardPixmap.SP_FileIcon)
    return style.standardIcon(standard_icon)


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
        self._editing_item: QTreeWidgetItem | None = None  # Track item being edited
        self._setup_ui()
        self._init_directories()
        self._setup_file_watcher()

    def _setup_ui(self) -> None:
        """Setup user interface (VSCode explorer style)."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Explorer header (VSCode style) with toolbar
        header = QWidget()
        header.setObjectName("explorerHeader")
        header.setFixedHeight(36)
        header.setMinimumWidth(180)  # Ensure enough space for title + buttons
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(12, 0, 12, 0)
        hlayout.setSpacing(4)

        title = QLabel("EXPLORER")
        title.setObjectName("explorerTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        hlayout.addWidget(title)

        hlayout.addStretch()

        # Toolbar buttons (using VSCode Codicons)
        self._new_file_btn = QPushButton()
        self._new_file_btn.setObjectName("explorerToolbarBtn")
        self._new_file_btn.setToolTip("新建文件")
        self._new_file_btn.setFixedSize(22, 22)
        self._new_file_btn.setIconSize(QSize(16, 16))
        self._new_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_file_btn.clicked.connect(self._new_file)
        hlayout.addWidget(self._new_file_btn)

        self._new_folder_btn = QPushButton()
        self._new_folder_btn.setObjectName("explorerToolbarBtn")
        self._new_folder_btn.setToolTip("新建文件夹")
        self._new_folder_btn.setFixedSize(22, 22)
        self._new_folder_btn.setIconSize(QSize(16, 16))
        self._new_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_folder_btn.clicked.connect(self._new_folder)
        hlayout.addWidget(self._new_folder_btn)

        self._refresh_btn = QPushButton()
        self._refresh_btn.setObjectName("explorerToolbarBtn")
        self._refresh_btn.setToolTip("刷新")
        self._refresh_btn.setFixedSize(22, 22)
        self._refresh_btn.setIconSize(QSize(16, 16))
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self.refresh)
        hlayout.addWidget(self._refresh_btn)

        # Set icons on toolbar buttons
        self._setup_toolbar_icons()

        layout.addWidget(header)

        # File tree with drag-drop support
        self.tree = _ChevronTreeWidget(file_tree_widget=self)
        self.tree.setObjectName("fileTree")
        self.tree.setHeaderLabels(["名称"])
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setIndentation(12)  # VSCode: 12px indentation
        self.tree.setRootIsDecorated(True)
        self.tree.setItemsExpandable(True)
        self.tree.setAnimated(False)  # Disable expand/collapse animation
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        # Enable inline editing
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.EditKeyPressed)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        self.tree.header().hide()

        self._apply_style()

    def _apply_style(self) -> None:
        """Apply VSCode explorer style."""
        c = get_theme_colors()

        self.setStyleSheet(f"""
            /* Base styles */
            QWidget {{
                background-color: {c["surface"]};
                color: {c["fg"]};
            }}

            /* Explorer header */
            #explorerHeader {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
            }}

            #explorerTitle {{
                font-size: 11px;
                font-weight: 600;
                color: {c["fg"]};
                text-transform: uppercase;
                letter-spacing: 1px;
            }}

            /* Explorer toolbar buttons (VSCode Codicons) */
            #explorerToolbarBtn {{
                background-color: transparent;
                border: none;
                border-radius: 3px;
                font-family: "codicon", "Segoe UI Symbol", "Apple Symbols", sans-serif;
                font-size: 18px;
                padding: 0;
                color: {c["fg"]};
            }}
            #explorerToolbarBtn:hover {{
                background-color: {c["tree_hover"]};
            }}

            /* File tree */
            #fileTree {{
                background-color: {c["surface"]};
                border: none;
                outline: none;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
                selection-background-color: {c["tree_sel_bg"]};
                selection-color: {c["tree_sel_fg"]};
            }}

            /* Tree items - VSCode 22px row height */
            #fileTree::item {{
                height: 22px;
                border: none;
                padding: 0 4px;
                border-radius: 3px;
                show-decoration-selected: 1;
            }}

            #fileTree::item:hover {{
                background-color: {c["tree_hover"]};
            }}

            #fileTree::item:selected {{
                background-color: {c["tree_sel_bg"]};
                color: {c["tree_sel_fg"]};
                border-left: none;
                border-right: none;
                border-top: none;
                border-bottom: none;
            }}

            #fileTree::item:selected:hover {{
                background-color: {c["tree_sel_bg"]};
            }}

            /* Scrollbar */
            QScrollBar:vertical {{
                background-color: {c["surface"]};
                width: 10px;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background-color: {c["muted"]};
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

            /* Context Menu */
            #explorerContextMenu {{
                background-color: {c["bg"]};
                border: 1px solid {c["border"]};
                border-radius: 6px;
                padding: 4px;
            }}
            #explorerContextMenu::item {{
                padding: 6px 24px;
                border-radius: 3px;
            }}
            #explorerContextMenu::item:selected {{
                background-color: {c["tree_sel_bg"]};
                color: {c["tree_sel_fg"]};
            }}
        """)

        # Set row height
        self.tree.setIconSize(QSize(16, 16))

        # Update toolbar icons for current theme
        self._setup_toolbar_icons()

    def _setup_toolbar_icons(self) -> None:
        """Set icons on toolbar buttons using VSCode Codicon style."""
        theme = get_theme_colors()
        icon_color = QColor(theme["fg"])

        self._new_file_btn.setIcon(_draw_codicon_icon("new-file", icon_color))
        self._new_folder_btn.setIcon(_draw_codicon_icon("new-folder", icon_color))
        self._refresh_btn.setIcon(_draw_codicon_icon("refresh", icon_color))

    def _init_directories(self) -> None:
        """Initialize fixed directory structure."""
        from PyQt6.QtWidgets import QApplication
        style = QApplication.style()

        for dir_name in FIXED_DIRECTORIES:
            dir_path = self.workspace / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

            item = QTreeWidgetItem(self.tree)
            item.setText(0, DIR_LABELS.get(dir_name, dir_name))
            # Folders don't show icons (only chevron arrows)
            item.setData(0, Qt.ItemDataRole.UserRole, dir_name)
            item.setToolTip(0, DIR_DESCRIPTIONS.get(dir_name, dir_name))

            # Add subdirectory for data/processed
            if dir_name == "data":
                processed_path = dir_path / "processed"
                processed_path.mkdir(parents=True, exist_ok=True)

                processed_item = QTreeWidgetItem(item)
                processed_item.setText(0, DIR_LABELS.get("processed", "processed"))
                # Folders don't show icons
                processed_item.setData(0, Qt.ItemDataRole.UserRole, "data/processed")
                processed_item.setToolTip(0, DIR_DESCRIPTIONS.get("processed", ""))

    def _setup_file_watcher(self) -> None:
        """Setup QFileSystemWatcher to detect external file changes."""
        self._file_watcher = QFileSystemWatcher(self)
        # Watch all fixed directories
        for dir_name in FIXED_DIRECTORIES:
            dir_path = str(self.workspace / dir_name)
            self._file_watcher.addPath(dir_path)
        # Watch data/processed subdirectory
        self._file_watcher.addPath(str(self.workspace / "data" / "processed"))
        # Connect signal to refresh on change
        self._file_watcher.directoryChanged.connect(self._on_directory_changed)

    def _on_directory_changed(self, path: str) -> None:
        """Handle directory change - refresh the tree if directory is currently expanded."""
        path_obj = Path(path)
        # Find which directory changed
        rel_path = str(path_obj.relative_to(self.workspace))

        # Check if this directory is currently expanded
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item_dir = item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir == rel_path and item.isExpanded():
                # Refresh this specific directory
                item.setExpanded(False)
                item.setExpanded(True)
                break
            # Check subdirectories (like data/processed)
            for j in range(item.childCount()):
                child = item.child(j)
                child_dir = child.data(0, Qt.ItemDataRole.UserRole)
                if child_dir == rel_path and child.isExpanded():
                    child.setExpanded(False)
                    child.setExpanded(True)
                    break

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item click - toggle folder expansion or select file."""
        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        logger.debug("FileTree: clicked item, dir_name={}", dir_name)
        if not dir_name:
            ui_logger.debug("FileTree: clicked item without dir_name")
            return

        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path_str:
            file_path = Path(file_path_str)
            if file_path.is_file():
                ui_logger.debug("FileTree: selected file {}", file_path.name)
                logger.debug("FileTree: selected file: {}", file_path)
                self.file_selected.emit(file_path)
                top_level = dir_name.split("/")[0]
                if top_level in FIXED_DIRECTORIES:
                    ui_logger.debug("FileTree: switched to directory {}", top_level)
                    logger.debug("FileTree: emitting directory_selected: {}", top_level)
                    self.directory_selected.emit(top_level)
            return

        # Directory clicked - toggle expansion
        top_level = dir_name.split("/")[0]
        if "/" in dir_name:
            ui_logger.debug("FileTree: clicked sub-directory {}, emitting {}", dir_name, top_level)
            logger.debug("FileTree: sub-directory clicked: {}, emitting: {}", dir_name, top_level)
            self.directory_selected.emit(top_level)
        elif dir_name in FIXED_DIRECTORIES:
            ui_logger.debug("FileTree: clicked directory {}, emitting {}", dir_name, dir_name)
            logger.debug("FileTree: directory clicked: {}, emitting: {}", dir_name, dir_name)
            self.directory_selected.emit(dir_name)

        # Toggle expand/collapse (VSCode behavior)
        item.setExpanded(not item.isExpanded())

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle inline edit completion - create new file/folder or rename."""
        # Prevent recursive calls during editing
        if self._editing_item is not None and self._editing_item != item:
            return

        new_name = item.text(0).strip()
        if not new_name:
            # Remove item if name is empty (user cancelled)
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            self._editing_item = None
            return

        # Check if this is a new item (no UserRole data set yet)
        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)

        if not dir_name and not file_path_str:
            # This is a new item being created
            self._editing_item = item
            parent = item.parent()
            if parent:
                parent_dir = parent.data(0, Qt.ItemDataRole.UserRole)
                if parent_dir:
                    parent_path = self.workspace / parent_dir
                    # Check if it's a file or folder based on name
                    if "." in new_name:
                        # It's a file
                        new_file = parent_path / new_name
                        try:
                            new_file.touch()
                            # Update item data
                            from PyQt6.QtWidgets import QApplication
                            style = QApplication.style()
                            item.setIcon(0, _get_file_icon(new_file.suffix, style))
                            item.setData(0, Qt.ItemDataRole.UserRole, parent_dir)
                            item.setData(0, Qt.ItemDataRole.UserRole + 1, str(new_file))
                            logger.info("Created file: {}", new_file)
                        except Exception as e:
                            QMessageBox.warning(self, "创建失败", f"无法创建文件:\n{e}")
                            parent.removeChild(item)
                    else:
                        # It's a folder
                        new_folder = parent_path / new_name
                        try:
                            new_folder.mkdir(exist_ok=True)
                            # Update item data
                            new_dir_name = f"{parent_dir}/{new_name}" if "/" in parent_dir else new_name
                            item.setData(0, Qt.ItemDataRole.UserRole, new_dir_name)
                            logger.info("Created folder: {}", new_folder)
                        except Exception as e:
                            QMessageBox.warning(self, "创建失败", f"无法创建文件夹:\n{e}")
                            parent.removeChild(item)
            self._editing_item = None
            return

        # Existing item rename logic - only proceed if name actually changed
        original_name = ""
        if file_path_str:
            original_name = Path(file_path_str).name
        elif dir_name:
            if "/" in dir_name:
                original_name = dir_name.split("/")[-1]
            else:
                original_name = DIR_LABELS.get(dir_name, dir_name)

        if original_name.lower() == new_name.lower():
            # Name hasn't actually changed (case-insensitive comparison)
            self._editing_item = None
            return

        self._editing_item = item

        if file_path_str:
            # Renaming a file
            old_path = Path(file_path_str)
            new_path = old_path.parent / new_name
            if old_path != new_path and new_path.exists():
                QMessageBox.warning(self, "重命名失败", f"文件名 '{new_name}' 已存在")
                self._revert_item_name(item)
                self._editing_item = None
                return
            try:
                old_path.rename(new_path)
                item.setData(0, Qt.ItemDataRole.UserRole + 1, str(new_path))
                logger.info("Renamed file: {} -> {}", old_path, new_path)
            except Exception as e:
                QMessageBox.warning(self, "重命名失败", f"无法重命名:\n{e}")
                self._revert_item_name(item)
                self._editing_item = None
        elif dir_name:
            # Renaming a directory
            old_path = self.workspace / dir_name
            new_path = old_path.parent / new_name
            if old_path != new_path and new_path.exists():
                QMessageBox.warning(self, "重命名失败", f"文件夹名 '{new_name}' 已存在")
                self._revert_item_name(item)
                self._editing_item = None
                return
            try:
                old_path.rename(new_path)
                # Update the user role data
                if "/" in dir_name:
                    parts = dir_name.split("/")
                    parts[-1] = new_name
                    new_dir_name = "/".join(parts)
                else:
                    new_dir_name = new_name
                item.setData(0, Qt.ItemDataRole.UserRole, new_dir_name)
                logger.info("Renamed directory: {} -> {}", old_path, new_path)
            except Exception as e:
                QMessageBox.warning(self, "重命名失败", f"无法重命名:\n{e}")
                self._revert_item_name(item)
                self._editing_item = None

        self._editing_item = None

    def _revert_item_name(self, item: QTreeWidgetItem) -> None:
        """Revert item name to original after failed edit."""
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path_str:
            item.setText(0, Path(file_path_str).name)
            return

        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        if dir_name:
            if "/" in dir_name:
                item.setText(0, dir_name.split("/")[-1])
            else:
                item.setText(0, DIR_LABELS.get(dir_name, dir_name))

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Handle item expansion to load files."""
        from PyQt6.QtWidgets import QApplication
        style = QApplication.style()

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
                    # Folders don't show icons
                    rel = str(entry.relative_to(self.workspace))
                    child.setData(0, Qt.ItemDataRole.UserRole, rel)
                else:
                    # Files show type-specific icons
                    child.setIcon(0, _get_file_icon(entry.suffix, style))
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

    def _handle_drop(self, event: QDropEvent) -> None:
        """Handle file drop event - import files into the project.

        VS Code-style behavior:
        - Files dropped on directory -> copy to that directory
        - Files dropped on root -> determine target based on file type
        - Shows progress dialog for copy operation
        """
        mime = event.mimeData()
        urls = mime.urls()
        if not urls:
            return

        # Get target directory
        target_item = self.tree.itemAt(event.position())
        target_dir_name = None

        if target_item:
            dir_name = target_item.data(0, Qt.ItemDataRole.UserRole)
            if dir_name:
                target_dir_name = dir_name

        # Determine target directory
        if target_dir_name:
            target_dir = self.workspace / target_dir_name
        else:
            # Auto-determine target based on file type
            # For now, default to references
            target_dir = self.workspace / "references"

        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)

        # Extract file paths from URLs
        source_files = []
        for url in urls:
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if local_path:
                    source_files.append(Path(local_path))

        if not source_files:
            return

        # Copy files with progress dialog
        self._copy_files_with_progress(source_files, target_dir)

        # Refresh the tree to show new files
        self.refresh()

    def _copy_files_with_progress(self, source_files: list[Path], target_dir: Path) -> None:
        """Copy files to target directory with progress dialog."""
        progress = QProgressDialog("Copying files...", "Cancel", 0, len(source_files), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowTitle("Import Files")
        progress.show()

        copied_count = 0
        failed_files = []

        for i, source_file in enumerate(source_files):
            if progress.wasCanceled():
                break

            progress.setLabelText(f"Copying {source_file.name}...")
            source_file_name = source_file.name
            target_file = target_dir / source_file_name

            try:
                # Handle name conflicts
                if target_file.exists():
                    base, ext = source_file.stem, source_file.suffix
                    counter = 1
                    while target_file.exists():
                        target_file = target_dir / f"{base}_{counter}{ext}"
                        counter += 1

                shutil.copy2(source_file, target_file)
                copied_count += 1
            except Exception as e:
                logger.warning("Failed to copy {} to {}: {}", source_file, target_dir, e)
                failed_files.append(source_file_name)

            progress.setValue(i + 1)

        progress.close()

        if failed_files:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Copy Failed",
                f"Failed to copy {len(failed_files)} file(s):\n" + "\n".join(failed_files[:5])
            )
        elif copied_count > 0:
            logger.info("Copied {} file(s) to {}", copied_count, target_dir)

    # ------------------------------------------------------------------ #
    #  Context Menu
    # ------------------------------------------------------------------ #

    def _show_context_menu(self, pos) -> None:
        """Show context menu for right-click on item."""
        item = self.tree.itemAt(pos)
        if not item:
            return

        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)

        menu = QMenu(self)
        menu.setObjectName("explorerContextMenu")

        if file_path_str:
            # File item
            file_path = Path(file_path_str)
            rename_action = menu.addAction("重命名")
            delete_action = menu.addAction("删除")

            action = menu.exec(self.tree.mapToGlobal(pos))
            if action == rename_action:
                self._rename_file(file_path, item)
            elif action == delete_action:
                self._delete_file(file_path, item)
        elif dir_name:
            # Directory item
            new_file_action = menu.addAction("新建文件")
            new_folder_action = menu.addAction("新建文件夹")

            if dir_name not in FIXED_DIRECTORIES:
                rename_action = menu.addAction("重命名")
                delete_action = menu.addAction("删除")
            else:
                menu.addSeparator()
                rename_action = None
                delete_action = None

            action = menu.exec(self.tree.mapToGlobal(pos))
            if action == new_file_action:
                self._new_file_in_dir(dir_name)
            elif action == new_folder_action:
                self._new_folder_in_dir(dir_name)
            elif action == rename_action:
                dir_path = self.workspace / dir_name
                self._rename_directory(dir_path, item)
            elif action == delete_action:
                dir_path = self.workspace / dir_name
                self._delete_directory(dir_path, item)

    # ------------------------------------------------------------------ #
    #  File Operations
    # ------------------------------------------------------------------ #

    def _new_file(self) -> None:
        """Create new file in references directory (default)."""
        self._new_file_in_dir("references")

    def _new_folder(self) -> None:
        """Create new folder in references directory (default)."""
        self._new_folder_in_dir("references")

    def _new_file_in_dir(self, dir_name: str) -> None:
        """Create new file in specified directory using inline edit."""
        from PyQt6.QtWidgets import QApplication
        style = QApplication.style()

        dir_path = self.workspace / dir_name
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)

        # Expand the directory first
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item_dir = item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir == dir_name and not item.isExpanded():
                item.setExpanded(True)
                break

        # Create placeholder item with inline edit (no default name for VSCode-style auto-cancel)
        new_item = QTreeWidgetItem()
        new_item.setText(0, "")
        new_item.setIcon(0, _get_file_icon(".txt", style))
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable)

        # Find the directory item
        for i in range(root.childCount()):
            item = root.child(i)
            item_dir = item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir == dir_name:
                item.addChild(new_item)
                self.tree.setCurrentItem(new_item)
                self.tree.editItem(new_item, 0)
                break

    def _new_folder_in_dir(self, dir_name: str) -> None:
        """Create new folder in specified directory using inline edit."""
        dir_path = self.workspace / dir_name
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)

        # Expand the directory first
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item_dir = item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir == dir_name and not item.isExpanded():
                item.setExpanded(True)
                break

        # Create placeholder item with inline edit (no default name for VSCode-style auto-cancel)
        new_item = QTreeWidgetItem()
        new_item.setText(0, "")
        # Folders don't show icons
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable)

        # Find the directory item
        for i in range(root.childCount()):
            item = root.child(i)
            item_dir = item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir == dir_name:
                item.addChild(new_item)
                self.tree.setCurrentItem(new_item)
                self.tree.editItem(new_item, 0)
                break

    def _rename_file(self, file_path: Path, item: QTreeWidgetItem) -> None:
        """Rename a file using inline edit."""
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.tree.editItem(item, 0)

    def _delete_file(self, file_path: Path, item: QTreeWidgetItem) -> None:
        """Delete a file."""
        reply = QMessageBox.question(
            self,
            "删除文件",
            f"确定要删除 '{file_path.name}' 吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                file_path.unlink()
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:
                    root = self.tree.invisibleRootItem()
                    root.removeChild(item)
                logger.info("Deleted file: {}", file_path)
            except Exception as e:
                QMessageBox.warning(self, "删除失败", f"无法删除文件:\n{e}")

    def _rename_directory(self, dir_path: Path, item: QTreeWidgetItem) -> None:
        """Rename a directory using inline edit."""
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.tree.editItem(item, 0)

    def _delete_directory(self, dir_path: Path, item: QTreeWidgetItem) -> None:
        """Delete a directory."""
        reply = QMessageBox.question(
            self,
            "删除文件夹",
            f"确定要删除 '{dir_path.name}' 及其所有内容吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(dir_path)
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:
                    root = self.tree.invisibleRootItem()
                    root.removeChild(item)
                logger.info("Deleted directory: {}", dir_path)
            except Exception as e:
                QMessageBox.warning(self, "删除失败", f"无法删除文件夹:\n{e}")
