"""File tree widget for project directory structure.

Uses native QTreeWidget styling with:
- 22px row height
- 16px icons with proper alignment
- Native Qt selection, hover, and branch rendering
- Drag and drop file import support
"""

import shutil
from pathlib import Path

from loguru import logger
from PyQt6.QtCore import QFileSystemWatcher, QMimeData, QSize, Qt, QTimer, pyqtSignal

from autoreport.utils.logging_config import ui_logger
from PyQt6.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemDelegate,
    QApplication,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..theme import get_theme_colors
from .ui_utils import IconActionButton, compact_tooltip_qss, render_svg_icon

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


class _DragDropTreeWidget(QTreeWidget):
    """QTreeWidget with drag-drop support for external file import."""

    def __init__(self, file_tree_widget=None, parent=None):
        super().__init__(parent)
        self._file_tree_widget = file_tree_widget

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            if self._file_tree_widget:
                self._file_tree_widget._handle_drop(event)
        else:
            event.ignore()


def _get_file_icon(ext: str, style: QStyle = None) -> QIcon:
    """Get file icon by extension using QStyle standard icons."""
    if style is None:
        from PyQt6.QtWidgets import QApplication
        style = QApplication.style()

    ext = ext.lower()
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
    """File tree widget showing project structure with native Qt styling."""

    directory_selected = pyqtSignal(str)
    file_selected = pyqtSignal(Path)

    def __init__(self, workspace: Path):
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self._editing_item: QTreeWidgetItem | None = None
        self._pending_new_item: QTreeWidgetItem | None = None
        self._pending_new_kind: str | None = None  # "file" | "folder"
        self._setup_ui()
        self._init_directories()
        self._setup_file_watcher()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Explorer header with toolbar
        header = QWidget()
        header.setObjectName("explorerHeader")
        header.setFixedHeight(36)
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(12, 0, 12, 0)
        hlayout.setSpacing(4)

        title = QLabel("EXPLORER")
        title.setObjectName("explorerTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        hlayout.addWidget(title)

        hlayout.addStretch()

        self._new_file_btn = IconActionButton(
            tooltip="新建文件",
            object_name="explorerToolbarBtn",
            button_size=(22, 22),
            icon_size=(16, 16),
            on_click=self._new_file,
        )
        hlayout.addWidget(self._new_file_btn)

        self._new_folder_btn = IconActionButton(
            tooltip="新建文件夹",
            object_name="explorerToolbarBtn",
            button_size=(22, 22),
            icon_size=(16, 16),
            on_click=self._new_folder,
        )
        hlayout.addWidget(self._new_folder_btn)

        self._refresh_btn = IconActionButton(
            tooltip="刷新",
            object_name="explorerToolbarBtn",
            button_size=(22, 22),
            icon_size=(16, 16),
            on_click=self.refresh,
        )
        hlayout.addWidget(self._refresh_btn)

        self._setup_toolbar_icons()

        layout.addWidget(header)

        # File tree — native QTreeWidget with drag-drop
        self.tree = _DragDropTreeWidget(file_tree_widget=self)
        self.tree.setObjectName("fileTree")
        self.tree.setHeaderLabels(["名称"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setStretchLastSection(True)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setIndentation(20)
        self.tree.setRootIsDecorated(True)
        self.tree.setItemsExpandable(True)
        self.tree.setAnimated(False)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.EditKeyPressed)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDelegate().closeEditor.connect(self._on_close_editor)
        layout.addWidget(self.tree)

        self.tree.header().hide()

        self._apply_style()

    def _apply_style(self) -> None:
        """Apply minimal styling — let Qt handle selection, hover, branches natively."""
        c = get_theme_colors()

        self.setStyleSheet(f"""
            QWidget {{
                color: {c["fg"]};
            }}

            FileTreeWidget {{
                background-color: {c["surface"]};
            }}

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

            /* File tree — native styling with theme colors */
            #fileTree {{
                background-color: {c["surface"]};
                border: none;
                outline: none;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
                alternate-background-color: {c["surface"]};
            }}

            #fileTree::item {{
                height: 22px;
                padding: 0 4px;
            }}

            #fileTree::item:hover {{
                background-color: {c["tree_hover"]};
            }}

            #fileTree::item:selected {{
                background-color: {c["tree_sel_bg"]};
                color: {c["tree_sel_fg"]};
            }}

            #fileTree::item:selected:!active {{
                background-color: {c["tree_sel_bg"]};
                color: {c["fg"]};
            }}

            /* Scrollbar */
            QScrollBar:vertical {{
                background-color: {c["surface"]};
                width: 10px;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background-color: {c["scrollbar"]};
                min-height: 30px;
                border-radius: 5px;
            }}

            QScrollBar::handle:vertical:hover {{
                background-color: {c["scrollbar_hover"]};
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            /* Tooltips */
            {compact_tooltip_qss("QToolTip")}

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

        self.tree.setIconSize(QSize(16, 16))
        self._update_width()
        self._setup_toolbar_icons()

    def _setup_toolbar_icons(self) -> None:
        theme = get_theme_colors()
        icon_color = QColor(theme["fg"])

        self._new_file_btn.setIcon(render_svg_icon("new-file", icon_color))
        self._new_folder_btn.setIcon(render_svg_icon("new-folder", icon_color))
        self._refresh_btn.setIcon(render_svg_icon("refresh", icon_color))

    def _update_width(self) -> None:
        fm = self.fontMetrics()
        title_width = fm.horizontalAdvance("EXPLORER")
        min_width = 12 + title_width + (22 * 3) + (4 * 2) + 12 + 10
        self.setMinimumWidth(min_width)
        self.setMaximumWidth(16777215)

    def _init_directories(self) -> None:
        for dir_name in FIXED_DIRECTORIES:
            dir_path = self.workspace / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

            item = QTreeWidgetItem(self.tree)
            item.setText(0, DIR_LABELS.get(dir_name, dir_name))
            item.setData(0, Qt.ItemDataRole.UserRole, dir_name)
            item.setToolTip(0, DIR_DESCRIPTIONS.get(dir_name, dir_name))
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

            if dir_name == "data":
                processed_path = dir_path / "processed"
                processed_path.mkdir(parents=True, exist_ok=True)

                processed_item = QTreeWidgetItem(item)
                processed_item.setText(0, DIR_LABELS.get("processed", "processed"))
                processed_item.setData(0, Qt.ItemDataRole.UserRole, "data/processed")
                processed_item.setToolTip(0, DIR_DESCRIPTIONS.get("processed", ""))
                processed_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

    def _setup_file_watcher(self) -> None:
        self._file_watcher = QFileSystemWatcher(self)
        for dir_name in FIXED_DIRECTORIES:
            dir_path = str(self.workspace / dir_name)
            self._file_watcher.addPath(dir_path)
        self._file_watcher.addPath(str(self.workspace / "data" / "processed"))
        self._file_watcher.directoryChanged.connect(self._on_directory_changed)

    def _on_directory_changed(self, path: str) -> None:
        path_obj = Path(path)
        rel_path = str(path_obj.relative_to(self.workspace))

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item_dir = item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir == rel_path and item.isExpanded():
                item.setExpanded(False)
                item.setExpanded(True)
                break
            for j in range(item.childCount()):
                child = item.child(j)
                child_dir = child.data(0, Qt.ItemDataRole.UserRole)
                if child_dir == rel_path and child.isExpanded():
                    child.setExpanded(False)
                    child.setExpanded(True)
                    break

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
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

        top_level = dir_name.split("/")[0]
        if "/" in dir_name:
            ui_logger.debug("FileTree: clicked sub-directory {}, emitting {}", dir_name, top_level)
            logger.debug("FileTree: sub-directory clicked: {}, emitting: {}", dir_name, top_level)
            self.directory_selected.emit(top_level)
        elif dir_name in FIXED_DIRECTORIES:
            ui_logger.debug("FileTree: clicked directory {}, emitting {}", dir_name, dir_name)
            logger.debug("FileTree: directory clicked: {}, emitting: {}", dir_name, dir_name)
            self.directory_selected.emit(dir_name)

        # Toggle expansion on single click, but only if click is on the
        # text area (not the decoration/arrow where Qt already toggles).
        from PyQt6.QtGui import QCursor
        cursor_x = self.tree.viewport().mapFromGlobal(QCursor.pos()).x()
        depth = 0
        p = item.parent()
        while p is not None:
            depth += 1
            p = p.parent()
        text_start = (depth + 1) * self.tree.indentation()
        if cursor_x >= text_start:
            item.setExpanded(not item.isExpanded())

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._editing_item is not None and self._editing_item != item:
            return

        new_name = item.text(0).strip()
        if not new_name:
            self._remove_item(item)
            self._editing_item = None
            if self._pending_new_item == item:
                self._pending_new_item = None
                self._pending_new_kind = None
            return

        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)

        if not dir_name and not file_path_str:
            self._editing_item = item
            parent = item.parent()
            if parent:
                parent_dir = parent.data(0, Qt.ItemDataRole.UserRole)
                if parent_dir:
                    parent_path = self.workspace / parent_dir
                    if "." in new_name:
                        new_file = parent_path / new_name
                        try:
                            new_file.touch()
                            from PyQt6.QtWidgets import QApplication
                            style = QApplication.style()
                            item.setIcon(0, _get_file_icon(new_file.suffix, style))
                            item.setData(0, Qt.ItemDataRole.UserRole, parent_dir)
                            item.setData(0, Qt.ItemDataRole.UserRole + 1, str(new_file))
                            logger.info("Created file: {}", new_file)
                        except Exception as e:
                            QMessageBox.warning(self, "创建失败", f"无法创建文件:\n{e}")
                            self._remove_item(item)
                    else:
                        new_folder = parent_path / new_name
                        try:
                            new_folder.mkdir(exist_ok=True)
                            new_dir_name = f"{parent_dir}/{new_name}"
                            item.setData(0, Qt.ItemDataRole.UserRole, new_dir_name)
                            logger.info("Created folder: {}", new_folder)
                        except Exception as e:
                            QMessageBox.warning(self, "创建失败", f"无法创建文件夹:\n{e}")
                            self._remove_item(item)
            if self._pending_new_item == item:
                self._pending_new_item = None
                self._pending_new_kind = None
            self._editing_item = None
            return

        original_name = ""
        if file_path_str:
            original_name = Path(file_path_str).name
        elif dir_name:
            if "/" in dir_name:
                original_name = dir_name.split("/")[-1]
            else:
                original_name = DIR_LABELS.get(dir_name, dir_name)

        if original_name.lower() == new_name.lower():
            self._editing_item = None
            return

        self._editing_item = item

        if file_path_str:
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
            old_path = self.workspace / dir_name
            new_path = old_path.parent / new_name
            if old_path != new_path and new_path.exists():
                QMessageBox.warning(self, "重命名失败", f"文件夹名 '{new_name}' 已存在")
                self._revert_item_name(item)
                self._editing_item = None
                return
            try:
                old_path.rename(new_path)
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

    def _remove_item(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        if parent:
            parent.removeChild(item)
        else:
            self.tree.invisibleRootItem().removeChild(item)
        if self.tree.currentItem() == item:
            self.tree.setCurrentItem(None)

    def _on_close_editor(self, editor, hint: QAbstractItemDelegate.EndEditHint) -> None:
        if self._pending_new_item is None:
            return
        item = self._pending_new_item
        text = item.text(0).strip()
        if not text:
            parent = item.parent()
            self._remove_item(item)
            # Re-apply ShowIndicator so native Qt keeps the arrow visible
            # after the placeholder child was removed.
            if parent and parent.childCount() == 0:
                parent.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                )
        self._pending_new_item = None
        self._pending_new_kind = None

    def _bind_create_editor_live_updates(self, item: QTreeWidgetItem) -> None:
        if self._pending_new_kind != "file":
            return

        def _attach() -> None:
            editor = self.tree.focusWidget()
            if isinstance(editor, QLineEdit):
                def _on_text_changed(text: str) -> None:
                    if self._pending_new_item is not item:
                        return
                    ext = Path(text.strip()).suffix or ".txt"
                    item.setIcon(0, _get_file_icon(ext, QApplication.style()))

                editor.textChanged.connect(_on_text_changed)

        QTimer.singleShot(0, _attach)

    def _revert_item_name(self, item: QTreeWidgetItem) -> None:
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
        from PyQt6.QtWidgets import QApplication
        style = QApplication.style()

        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not dir_name:
            return

        dir_path = self.workspace / dir_name
        if not dir_path.is_dir():
            return

        while item.childCount() > 0:
            child = item.child(0)
            item.removeChild(child)

        # Re-apply ShowIndicator after clearing children so native Qt
        # keeps the arrow visible even for empty directories.
        item.setChildIndicatorPolicy(
            QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
        )

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
                    rel = str(entry.relative_to(self.workspace))
                    child.setData(0, Qt.ItemDataRole.UserRole, rel)
                    child.setText(0, entry.name)
                    child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                else:
                    child.setIcon(0, _get_file_icon(entry.suffix, style))
                    rel = str(entry.parent.relative_to(self.workspace))
                    child.setData(0, Qt.ItemDataRole.UserRole, rel)
                    child.setData(0, Qt.ItemDataRole.UserRole + 1, str(entry))

        except PermissionError as e:
            logger.warning("Permission denied accessing {}: {}", dir_path, e)

    def refresh(self) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.isExpanded():
                item.setExpanded(False)
                item.setExpanded(True)

    def get_selected_file(self) -> Path | None:
        item = self.tree.currentItem()
        if not item:
            return None
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path_str:
            return Path(file_path_str)
        return None

    def _get_selected_dir(self) -> str:
        """Get the directory of the currently selected item, falling back to 'references'."""
        item = self.tree.currentItem()
        if not item:
            return "references"
        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        if dir_name in FIXED_DIRECTORIES:
            return dir_name
        # Walk up to find parent fixed directory
        parent = item.parent()
        while parent is not None:
            parent_dir = parent.data(0, Qt.ItemDataRole.UserRole)
            if parent_dir in FIXED_DIRECTORIES:
                return parent_dir
            parent = parent.parent()
        return "references"

    def _handle_drop(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        urls = mime.urls()
        if not urls:
            return

        target_item = self.tree.itemAt(event.position())
        target_dir_name = self._resolve_target_dir(target_item)

        target_dir = self.workspace / target_dir_name
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)

        source_files = []
        for url in urls:
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if local_path:
                    source_files.append(Path(local_path))

        if not source_files:
            return

        self._copy_files_with_progress(source_files, target_dir)
        self.refresh()

    def _resolve_target_dir(self, target_item) -> str:
        if target_item is None:
            return "references"

        dir_name = target_item.data(0, Qt.ItemDataRole.UserRole)
        if dir_name in FIXED_DIRECTORIES:
            return dir_name

        parent = target_item.parent()
        while parent is not None:
            parent_dir = parent.data(0, Qt.ItemDataRole.UserRole)
            if parent_dir in FIXED_DIRECTORIES:
                return parent_dir
            parent = parent.parent()

        return "references"

    def _copy_files_with_progress(self, source_files: list[Path], target_dir: Path) -> None:
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
        item = self.tree.itemAt(pos)
        if not item:
            return

        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)

        menu = QMenu(self)
        menu.setObjectName("explorerContextMenu")

        if file_path_str:
            file_path = Path(file_path_str)
            rename_action = menu.addAction("重命名")
            delete_action = menu.addAction("删除")

            action = menu.exec(self.tree.mapToGlobal(pos))
            if action == rename_action:
                self._rename_file(file_path, item)
            elif action == delete_action:
                self._delete_file(file_path, item)
        elif dir_name:
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
        self._new_file_in_dir(self._get_selected_dir())

    def _new_folder(self) -> None:
        self._new_folder_in_dir(self._get_selected_dir())

    def _new_file_in_dir(self, dir_name: str) -> None:
        from PyQt6.QtWidgets import QApplication
        style = QApplication.style()

        dir_path = self.workspace / dir_name
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item_dir = item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir == dir_name and not item.isExpanded():
                item.setExpanded(True)
                break

        self._start_inline_create(dir_name=dir_name, is_folder=False, style=style)

    def _new_folder_in_dir(self, dir_name: str) -> None:
        dir_path = self.workspace / dir_name
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item_dir = item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir == dir_name and not item.isExpanded():
                item.setExpanded(True)
                break

        self._start_inline_create(dir_name=dir_name, is_folder=True, style=QApplication.style())

    def _start_inline_create(self, dir_name: str, is_folder: bool, style: QStyle) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent_item = root.child(i)
            item_dir = parent_item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir != dir_name:
                continue

            new_item = QTreeWidgetItem()
            new_item.setText(0, "")
            new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable)
            if is_folder:
                new_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            else:
                new_item.setIcon(0, _get_file_icon(".txt", style))
            parent_item.addChild(new_item)
            parent_item.setExpanded(True)
            self.tree.setCurrentItem(new_item)
            self._pending_new_item = new_item
            self._pending_new_kind = "folder" if is_folder else "file"
            self.tree.editItem(new_item, 0)
            self._bind_create_editor_live_updates(new_item)
            return

    def _rename_file(self, file_path: Path, item: QTreeWidgetItem) -> None:
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.tree.editItem(item, 0)

    def _delete_file(self, file_path: Path, item: QTreeWidgetItem) -> None:
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
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.tree.editItem(item, 0)

    def _delete_directory(self, dir_path: Path, item: QTreeWidgetItem) -> None:
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
