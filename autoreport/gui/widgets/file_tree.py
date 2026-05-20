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
from PyQt6.QtCore import QFileInfo, QFileSystemWatcher, QMimeData, QPoint, QSize, QSignalBlocker, Qt, QTimer, pyqtSignal

from autoreport.utils.logging_config import ui_logger
from PyQt6.QtGui import QColor, QCursor, QDrag, QDragEnterEvent, QDragMoveEvent, QDropEvent, QIcon, QPalette, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QFileIconProvider,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..theme import get_theme_colors
from .ui_utils import UI_HOVER_DELAY_MS, IconActionButton, compact_tooltip_qss, render_svg_icon

# Fixed directory structure
FIXED_DIRECTORIES = ["data", "references", "theory", "code", "tex"]
_FILE_TEXT_ICON_GAP_ADJUST = 28
_FILE_EDITOR_LEFT_ADJUST = -26


# ================================================================== #
#  Custom Delegate for Icon Alignment
# ================================================================== #


class _FileTreeDelegate(QStyledItemDelegate):
    """Delegate that draws file icons aligned with folder arrows.

    Problem: files have icons that push text right; folders don't.
    Fix: suppress Qt's icon, draw text as if no icon, then paint icon
    at the arrow position (center of the indentation column).
    """

    def paint(self, painter, option, index):
        tree_widget = option.widget
        if not tree_widget:
            super().paint(painter, option, index)
            return

        item = tree_widget.itemFromIndex(index)
        has_icon = item is not None and not item.icon(0).isNull()

        if not has_icon:
            super().paint(painter, option, index)
            return

        # Save icon reference
        icon = item.icon(0)
        icon_sz = tree_widget.iconSize()  # QSize(16, 16)

        # Draw selection bg + text without decoration, but do not mutate model
        # data in paint path (that can cause unstable click/edit behavior).
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.icon = QIcon()
        style = opt.widget.style() if opt.widget else QApplication.style()
        # Keep icon fixed; pull text closer so file rows visually match folder rows.
        opt.rect = opt.rect.adjusted(-_FILE_TEXT_ICON_GAP_ADJUST, 0, 0, 0)
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        # Draw icon at the same X as the branch arrow for this depth.
        # Qt draws the arrow centred in the column at  depth * indentation.
        indent = tree_widget.indentation()
        depth = 0
        p = item.parent()
        root = tree_widget.invisibleRootItem()
        while p is not None and p is not root:
            depth += 1
            p = p.parent()

        # Keep icon strictly anchored to the branch column center.
        icon_x = depth * indent + (indent - icon_sz.width()) // 2
        icon_y = option.rect.y() + (option.rect.height() - icon_sz.height()) // 2

        painter.save()
        icon.paint(painter, icon_x, icon_y, icon_sz.width(), icon_sz.height())
        painter.restore()

    def updateEditorGeometry(self, editor, option, index):  # noqa: N802
        super().updateEditorGeometry(editor, option, index)
        tree_widget = option.widget
        if not tree_widget:
            return
        item = tree_widget.itemFromIndex(index)
        if item is None:
            return
        # Leave clear branch/arrow area so expanded arrows are never covered
        # by the inline filename editor.
        if not item.icon(0).isNull():
            rect = editor.geometry()
            editor.setGeometry(rect.adjusted(_FILE_EDITOR_LEFT_ADJUST, 0, 0, 0))

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
    """QTreeWidget with drag-drop support for external file import and internal file moving."""

    def __init__(self, file_tree_widget=None, parent=None):
        super().__init__(parent)
        self._file_tree_widget = file_tree_widget

    def startDrag(self, supportedActions: Qt.DropAction) -> None:
        """Override to create a compact drag preview that doesn't stretch.

        Prevents the drag pixmap from expanding to full filename width.
        """
        current_item = self.currentItem()
        if not current_item:
            return

        # Only block dragging top-level fixed directories.
        # File nodes store parent dir in UserRole, so we must not use UserRole
        # alone to decide draggable status.
        dir_name = current_item.data(0, Qt.ItemDataRole.UserRole)
        file_path_str = current_item.data(0, Qt.ItemDataRole.UserRole + 1)
        is_top_level_fixed_dir = (
            current_item.parent() is None
            and not file_path_str
            and dir_name in FIXED_DIRECTORIES
        )
        if is_top_level_fixed_dir:
            return  # Don't allow dragging fixed directories

        # Get the icon for the item
        icon = current_item.icon(0)
        if icon.isNull():
            # Create a default icon if none exists
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QPainter
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setPen(self.palette().color(QPalette.ColorRole.Text))
            painter.drawRect(0, 0, 15, 15)
            painter.end()
            drag_icon = QIcon(pixmap)
        else:
            # Use the item's icon but limit size
            drag_icon = icon

        # Create a compact pixmap (just the icon, no text)
        drag_pixmap = drag_icon.pixmap(16, 16)

        # Create the drag object with our custom pixmap
        drag = QDrag(self)
        drag.setPixmap(drag_pixmap)
        drag.setHotSpot(QPoint(8, 8))

        # Set mime data (mimeData expects iterable, not single item)
        mime = self.mimeData([current_item])
        drag.setMimeData(mime)

        # Execute the drag
        drag.exec(supportedActions)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        # Accept both external files (urls) and internal items
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        # Check if we're dragging over a valid target
        target_item = self.itemAt(event.position().toPoint())
        if target_item:
            # Check if target is a fixed directory
            target_dir = target_item.data(0, Qt.ItemDataRole.UserRole)
            # Allow dropping into any directory
            if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        target_item = self.itemAt(event.position().toPoint())

        # Handle external file drops
        if event.mimeData().hasUrls():
            if self._file_tree_widget:
                self._file_tree_widget._handle_drop(event)
            event.acceptProposedAction()
            return

        # Handle internal item drops (moving files/folders)
        if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist") and target_item:
            if self._file_tree_widget:
                self._file_tree_widget._handle_internal_move(event, target_item)
            event.acceptProposedAction()
            # Don't call parent's dropEvent - we handle the file move ourselves
            return

        event.ignore()




def _get_file_icon(ext: str, style: QStyle = None, file_path: Path | None = None) -> QIcon:
    """Get file icon by extension, preferring system file-type icons."""
    if style is None:
        from PyQt6.QtWidgets import QApplication
        style = QApplication.style()
    provider = QFileIconProvider()
    if file_path is not None:
        icon = provider.icon(QFileInfo(str(file_path)))
        if not icon.isNull():
            return icon

    ext = ext.lower() or ".txt"
    icon = provider.icon(QFileInfo(f"placeholder{ext}"))
    if not icon.isNull():
        return icon
    return style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)


class FileTreeWidget(QWidget):
    """File tree widget showing project structure with native Qt styling."""

    directory_selected = pyqtSignal(str)
    file_selected = pyqtSignal(Path)
    path_changed = pyqtSignal(Path, Path)

    def __init__(self, workspace: Path):
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self._editing_item: QTreeWidgetItem | None = None
        self._pending_new_item: QTreeWidgetItem | None = None
        self._pending_new_kind: str | None = None  # "file" | "folder"
        self._pending_editor: QLineEdit | None = None
        self._hover_tip: QWidget | None = None
        self._hover_tip_label: QLabel | None = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(UI_HOVER_DELAY_MS)
        self._hover_timer.timeout.connect(self._show_pending_hover_tip)
        self._pending_hover_text = ""
        self._pending_hover_pos = QPoint()
        self._hovered_item: QTreeWidgetItem | None = None
        self._root_selected = False
        self._setup_ui()
        self._init_directories()
        self._setup_file_watcher()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Explorer header with toolbar
        header = QWidget(self)
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
        self.tree.setItemDelegate(_FileTreeDelegate(self.tree))
        self.tree.setHeaderLabels(["名称"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setStretchLastSection(True)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Enable both internal move and external drag-drop
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.setIndentation(14)
        self.tree.setRootIsDecorated(True)
        self.tree.setItemsExpandable(True)
        self.tree.setAnimated(False)
        self.tree.setMouseTracking(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemEntered.connect(self._on_item_entered)
        self.tree.viewport().installEventFilter(self)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.EditKeyPressed)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDelegate().closeEditor.connect(self._on_close_editor)
        layout.addWidget(self.tree)

        # Use native margins to keep top-level branch spacing consistent.
        self.tree.setContentsMargins(0, 0, 0, 0)

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
                font-weight: {c["fw_semibold"]};
                color: {c["fg"]};
                text-transform: uppercase;
                letter-spacing: 1px;
            }}

            #explorerToolbarBtn {{
                background-color: transparent;
                border: none;
                border-radius: {c["radius_sm"]};
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

            /* Inline edit input - gray background with blue border on focus */
            #fileTree QLineEdit {{
                background-color: {c["bg"]};
                color: {c["fg"]};
                border: 1px solid {c["border"]};
                border-radius: {c["radius_sm"]};
                padding: 2px 2px;
                selection-background-color: {c["accent"]};
            }}
            #fileTree QLineEdit:focus {{
                border: 1px solid {c["accent"]};
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
                border-radius: {c["radius_md"]};
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
                border-radius: {c["radius_md"]};
                padding: 4px;
            }}
            #explorerContextMenu::item {{
                padding: 6px 24px;
                border-radius: {c["radius_sm"]};
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
            self._show_directory_indicator(item)

            if dir_name == "data":
                processed_path = dir_path / "processed"
                processed_path.mkdir(parents=True, exist_ok=True)

                processed_item = QTreeWidgetItem(item)
                processed_item.setText(0, DIR_LABELS.get("processed", "processed"))
                processed_item.setData(0, Qt.ItemDataRole.UserRole, "data/processed")
                self._show_directory_indicator(processed_item)

    def _show_directory_indicator(self, item: QTreeWidgetItem) -> None:
        item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

    def _ensure_directory_indicators(self, root: QTreeWidgetItem | None = None) -> None:
        node = root if root is not None else self.tree.invisibleRootItem()
        for i in range(node.childCount()):
            child = node.child(i)
            dir_name = child.data(0, Qt.ItemDataRole.UserRole)
            file_path_str = child.data(0, Qt.ItemDataRole.UserRole + 1)
            if dir_name and not file_path_str:
                self._show_directory_indicator(child)
            self._ensure_directory_indicators(child)

    def _workspace_rel(self, path: Path) -> str:
        return path.relative_to(self.workspace).as_posix()

    @staticmethod
    def _tilde_path(path: Path) -> str:
        resolved = path.resolve()
        home = Path.home().resolve()
        try:
            rel = resolved.relative_to(home)
            return "~" if not rel.parts else f"~/{rel.as_posix()}"
        except ValueError:
            return resolved.as_posix()

    def _hover_text_for_item(self, item: QTreeWidgetItem) -> str:
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path_str:
            return self._tilde_path(Path(file_path_str))

        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        if dir_name:
            return self._tilde_path(self.workspace / dir_name)

        return item.text(0)

    def _collapse_other_top_level_dirs(self, keep_dir: str) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            sibling = root.child(i)
            sibling_dir = sibling.data(0, Qt.ItemDataRole.UserRole)
            if sibling_dir in FIXED_DIRECTORIES and sibling_dir != keep_dir and sibling.isExpanded():
                sibling.setExpanded(False)

    def _setup_file_watcher(self) -> None:
        self._file_watcher = QFileSystemWatcher(self)
        for dir_name in FIXED_DIRECTORIES:
            dir_path = str(self.workspace / dir_name)
            self._file_watcher.addPath(dir_path)
        self._file_watcher.addPath(str(self.workspace / "data" / "processed"))
        self._file_watcher.directoryChanged.connect(self._on_directory_changed)

    def _on_directory_changed(self, path: str) -> None:
        path_obj = Path(path)
        rel_path = self._workspace_rel(path_obj)
        selected_file = None
        selected_dir = None
        current_item = self.tree.currentItem()
        if current_item is not None:
            selected_file = current_item.data(0, Qt.ItemDataRole.UserRole + 1)
            if not selected_file:
                selected_dir = current_item.data(0, Qt.ItemDataRole.UserRole)
        if self._pending_new_item is not None:
            pending_parent = self._pending_new_item.data(0, Qt.ItemDataRole.UserRole + 2)
            if pending_parent == rel_path:
                return

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item_dir = item.data(0, Qt.ItemDataRole.UserRole)
            if item_dir == rel_path and item.isExpanded():
                self._refresh_expanded_item_preserve_state(item)
                break
            for j in range(item.childCount()):
                child = item.child(j)
                child_dir = child.data(0, Qt.ItemDataRole.UserRole)
                if child_dir == rel_path and child.isExpanded():
                    self._refresh_expanded_item_preserve_state(child)
                    break
        self._restore_selection(selected_file, selected_dir)
        self._ensure_directory_indicators()
        self.tree.viewport().update()

    def _restore_selection(self, selected_file: str | None, selected_dir: str | None) -> None:
        if not selected_file and not selected_dir:
            return

        root = self.tree.invisibleRootItem()
        stack = [root]
        while stack:
            node = stack.pop()
            for i in range(node.childCount()):
                child = node.child(i)
                file_path_str = child.data(0, Qt.ItemDataRole.UserRole + 1)
                dir_name = child.data(0, Qt.ItemDataRole.UserRole)
                if selected_file and file_path_str == selected_file:
                    self.tree.setCurrentItem(child)
                    return
                if not selected_file and selected_dir and dir_name == selected_dir:
                    self.tree.setCurrentItem(child)
                    return
                stack.append(child)

    def _refresh_expanded_item_preserve_state(self, item: QTreeWidgetItem) -> None:
        """Refresh an expanded directory item while preserving direct child expansions."""
        expanded_child_dirs: set[str] = set()
        for i in range(item.childCount()):
            child = item.child(i)
            dir_name = child.data(0, Qt.ItemDataRole.UserRole)
            file_path_str = child.data(0, Qt.ItemDataRole.UserRole + 1)
            if dir_name and not file_path_str and child.isExpanded():
                expanded_child_dirs.add(dir_name)

        self._on_item_expanded(item)
        for i in range(item.childCount()):
            child = item.child(i)
            dir_name = child.data(0, Qt.ItemDataRole.UserRole)
            file_path_str = child.data(0, Qt.ItemDataRole.UserRole + 1)
            if dir_name in expanded_child_dirs and not file_path_str:
                child.setExpanded(True)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        self._root_selected = False
        self._ensure_directory_indicators()
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
        cursor_x = self.tree.viewport().mapFromGlobal(QCursor.pos()).x()
        depth = 0
        p = item.parent()
        while p is not None:
            depth += 1
            p = p.parent()
        text_start = (depth + 1) * self.tree.indentation()
        if cursor_x >= text_start:
            item.setExpanded(not item.isExpanded())
        self._ensure_directory_indicators()
        self.tree.viewport().update()

    def _on_item_entered(self, item: QTreeWidgetItem, column: int) -> None:
        """Show compact tooltip close to cursor with full path context."""
        tip = self._hover_text_for_item(item)

        if not tip:
            self._hide_hover_tip()
            return

        self._hovered_item = item
        self._pending_hover_text = tip
        self._pending_hover_pos = QCursor.pos() + QPoint(10, 2)
        self._hover_timer.start()

    def _show_pending_hover_tip(self) -> None:
        if self._pending_hover_text:
            self._show_hover_tip(self._pending_hover_text, self._pending_hover_pos)

    def _show_hover_tip(self, text: str, global_pos: QPoint) -> None:
        if self._hover_tip is None:
            self._hover_tip = QWidget()
            self._hover_tip.setWindowFlags(
                Qt.WindowType.ToolTip
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.NoDropShadowWindowHint
            )
            self._hover_tip.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self._hover_tip.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self._hover_tip.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self._hover_tip.setStyleSheet("background: transparent; border: none;")
            self._hover_tip_label = QLabel(self._hover_tip)
            self._hover_tip_label.setObjectName("fileTreeHoverTip")
            self._hover_tip_label.setStyleSheet(compact_tooltip_qss("QLabel#fileTreeHoverTip"))
        self._hover_tip_label.setText(text)
        self._hover_tip_label.adjustSize()
        self._hover_tip.resize(self._hover_tip_label.size())
        self._hover_tip_label.move(0, 0)
        self._hover_tip.move(global_pos)
        self._hover_tip.show()

    def _hide_hover_tip(self) -> None:
        self._hover_timer.stop()
        self._pending_hover_text = ""
        self._hovered_item = None
        if self._hover_tip is None:
            return
        self._hover_tip.hide()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.tree.viewport():
            if event.type() == event.Type.MouseButtonPress:
                item = self.tree.itemAt(event.pos())
                if item is None:
                    self._root_selected = True
                    self.tree.setCurrentItem(None)
                    self.directory_selected.emit(".")
            if event.type() == event.Type.MouseMove:
                item = self.tree.itemAt(event.pos())
                if item is None:
                    self._hide_hover_tip()
                elif item is not self._hovered_item:
                    self._hide_hover_tip()
                    self._on_item_entered(item, 0)
            if event.type() in (
                event.Type.Leave,
                event.Type.MouseButtonPress,
                event.Type.Wheel,
                event.Type.Hide,
            ):
                self._hide_hover_tip()
        return super().eventFilter(obj, event)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._editing_item is not None and self._editing_item != item:
            return

        new_name = item.text(0).strip()

        dir_name = item.data(0, Qt.ItemDataRole.UserRole)
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)

        # Check if this is a new item being created
        is_new_item = (self._pending_new_item == item and not dir_name and not file_path_str)

        # For new items, only update icon during editing, don't create file yet
        if is_new_item:
            self._editing_item = item
            return  # Don't create file yet, wait for editor to close

        # Empty name for existing items - revert
        if not new_name and not is_new_item:
            self._remove_item(item)
            self._editing_item = None
            if self._pending_new_item == item:
                self._pending_new_item = None
                self._pending_new_kind = None
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
                self.path_changed.emit(old_path, new_path)
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
                self.path_changed.emit(old_path, new_path)
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
        # Ignore close events from unrelated editors.
        if self._pending_editor is not None and editor is not self._pending_editor:
            return
        text = self._pending_new_item.text(0).strip()
        if isinstance(editor, QLineEdit):
            text = editor.text().strip()
            with QSignalBlocker(self.tree):
                self._pending_new_item.setText(0, text)
        if not text:
            self._cancel_pending_new_item()
            return
        self._finalize_pending_new_item()

    def _pending_create_text(self) -> str:
        if self._pending_new_item is None:
            return ""
        editor = self._pending_editor
        if not isinstance(editor, QLineEdit):
            focus_widget = self.tree.focusWidget()
            if isinstance(focus_widget, QLineEdit):
                editor = focus_widget
        if isinstance(editor, QLineEdit):
            return editor.text().strip()
        return self._pending_new_item.text(0).strip()

    def _bind_create_editor_live_updates(self, item: QTreeWidgetItem) -> None:
        def _attach() -> None:
            editor = self.tree.focusWidget()
            if isinstance(editor, QLineEdit):
                self._pending_editor = editor
                editor.destroyed.connect(lambda *_: self._clear_pending_editor(editor))

        QTimer.singleShot(0, _attach)

    def _focus_inline_editor(self) -> None:
        def _apply_focus() -> None:
            editor = self.tree.focusWidget()
            if not isinstance(editor, QLineEdit):
                editor = self.tree.findChild(QLineEdit)
            if isinstance(editor, QLineEdit):
                self._pending_editor = editor
                editor.destroyed.connect(lambda *_: self._clear_pending_editor(editor))
                editor.setFocus(Qt.FocusReason.OtherFocusReason)

        QTimer.singleShot(0, _apply_focus)

    def _clear_pending_editor(self, editor: QLineEdit) -> None:
        if self._pending_editor is editor:
            self._pending_editor = None

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

        # IMPORTANT: Block updates and set ShowIndicator BEFORE clearing children.
        # Qt evaluates arrow visibility based on policy AND current state.
        # If we clear children first, Qt may hide the arrow before we can
        # re-apply the policy, especially during rapid user interactions.
        self.tree.setUpdatesEnabled(False)
        try:
            with QSignalBlocker(self.tree):
                self._show_directory_indicator(item)

                while item.childCount() > 0:
                    child = item.child(0)
                    item.removeChild(child)

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
                        rel = self._workspace_rel(entry)
                        child.setData(0, Qt.ItemDataRole.UserRole, rel)
                        child.setText(0, entry.name)
                        self._show_directory_indicator(child)
                    else:
                        child.setIcon(0, _get_file_icon(entry.suffix, style, entry))
                        rel = self._workspace_rel(entry.parent)
                        child.setData(0, Qt.ItemDataRole.UserRole, rel)
                        child.setData(0, Qt.ItemDataRole.UserRole + 1, str(entry))

        except PermissionError as e:
            logger.warning("Permission denied accessing {}: {}", dir_path, e)
        finally:
            with QSignalBlocker(self.tree):
                self._show_directory_indicator(item)
            self.tree.setUpdatesEnabled(True)
            self.tree.viewport().update()

    def refresh(self) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.isExpanded():
                item.setExpanded(False)
                item.setExpanded(True)
        self._ensure_directory_indicators(root)
        self.tree.viewport().update()

    def get_selected_file(self) -> Path | None:
        item = self.tree.currentItem()
        if not item:
            return None
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path_str:
            return Path(file_path_str)
        return None

    def _get_selected_dir(self) -> str:
        """Get the selected directory path, falling back to 'references'."""
        item = self.tree.currentItem()
        if not item:
            if self._root_selected:
                return "."
            return "references"

        file_path_str = item.data(0, Qt.ItemDataRole.UserRole + 1)
        dir_name = item.data(0, Qt.ItemDataRole.UserRole)

        # Directory node (top-level or nested): use it directly.
        if dir_name and not file_path_str:
            return dir_name

        # File node: use its parent directory role.
        if dir_name:
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

    def _handle_internal_move(self, event: QDropEvent, target_item: QTreeWidgetItem) -> None:
        """Handle internal drag-drop for moving files/folders within the project."""
        # Get the dragged item(s)
        dragged_items = self.tree.selectedItems()
        if not dragged_items:
            return

        # Get target directory
        target_dir_name = target_item.data(0, Qt.ItemDataRole.UserRole)
        if not target_dir_name:
            # Target is a file, get its parent directory
            file_path_str = target_item.data(0, Qt.ItemDataRole.UserRole + 1)
            if file_path_str:
                target_dir_name = target_item.data(0, Qt.ItemDataRole.UserRole)
            else:
                return  # Invalid target

        target_dir = self.workspace / target_dir_name
        moved_paths: list[Path] = []

        # Process each dragged item
        for dragged_item in dragged_items:
            dir_name = dragged_item.data(0, Qt.ItemDataRole.UserRole)
            file_path_str = dragged_item.data(0, Qt.ItemDataRole.UserRole + 1)

            # Determine source path
            if file_path_str:
                # It's a file
                source_path = Path(file_path_str)
            elif dir_name:
                # It's a directory
                source_path = self.workspace / dir_name
            else:
                continue  # Skip invalid items

            # Skip if target is the same as source parent
            if source_path.parent == target_dir:
                continue

            # Check if trying to move into a subdirectory of itself
            try:
                target_dir.relative_to(source_path)
                continue  # Would create a cycle, skip
            except ValueError:
                pass  # Not a subdirectory, OK to move

            # Perform the move
            try:
                target_path = target_dir / source_path.name

                # Handle name conflicts
                if target_path.exists():
                    base, ext = source_path.stem, source_path.suffix
                    counter = 1
                    while target_path.exists():
                        target_path = target_dir / f"{base}_{counter}{ext}"
                        counter += 1

                shutil.move(str(source_path), str(target_path))
                self.path_changed.emit(source_path, target_path)
                moved_paths.append(target_path)
                logger.info("Moved {} to {}", source_path, target_path)
            except Exception as e:
                logger.warning("Failed to move {} to {}: {}", source_path, target_dir, e)
                QMessageBox.warning(
                    self,
                    "移动失败",
                    f"无法移动 '{source_path.name}' 到 '{target_dir_name}':\n{e}"
                )

        self.refresh()
        if moved_paths:
            self._select_moved_path(moved_paths[0])

    def _select_moved_path(self, path: Path) -> None:
        rel_dir = str(path.relative_to(self.workspace).parent)
        if rel_dir == ".":
            rel_dir = ""
        selected_file = str(path) if path.is_file() else None
        selected_dir = str(path.relative_to(self.workspace)) if path.is_dir() else rel_dir
        self._restore_selection(selected_file, selected_dir)
        if path.is_file():
            self.file_selected.emit(path)
        else:
            self.directory_selected.emit(selected_dir or ".")

    def _resolve_target_dir(self, target_item) -> str:
        if target_item is None:
            return "references"

        dir_name = target_item.data(0, Qt.ItemDataRole.UserRole)
        file_path_str = target_item.data(0, Qt.ItemDataRole.UserRole + 1)
        if dir_name and not file_path_str:
            return dir_name
        if dir_name:
            return dir_name

        parent = target_item.parent()
        while parent is not None:
            parent_dir = parent.data(0, Qt.ItemDataRole.UserRole)
            if parent_dir:
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
        # Handle repeated "new file/folder" clicks while an inline-create is pending.
        if self._pending_new_item is not None:
            pending_text = self._pending_create_text()

            if not pending_text:
                self._cancel_pending_new_item()
            else:
                with QSignalBlocker(self.tree):
                    self._pending_new_item.setText(0, pending_text)
                self._finalize_pending_new_item()

        # Find the target directory item (could be nested like data/processed)
        target_item = None

        if "/" in dir_name:
            # Handle nested directories
            parts = dir_name.split("/")
            root = self.tree.invisibleRootItem()
            current = None
            for i in range(root.childCount()):
                if root.child(i).data(0, Qt.ItemDataRole.UserRole) == parts[0]:
                    current = root.child(i)
                    break

            if current and len(parts) > 1:
                # Navigate to subdirectory
                for j in range(current.childCount()):
                    if current.child(j).data(0, Qt.ItemDataRole.UserRole) == dir_name:
                        target_item = current.child(j)
                        break
                if not target_item:
                    # Subdirectory item not found, create it
                    target_item = QTreeWidgetItem(current)
                    target_item.setText(0, DIR_LABELS.get(parts[1], parts[1]))
                    target_item.setData(0, Qt.ItemDataRole.UserRole, dir_name)
                    self._show_directory_indicator(target_item)
            else:
                target_item = current
        else:
            # Top-level directory
            root = self.tree.invisibleRootItem()
            for i in range(root.childCount()):
                item = root.child(i)
                if item.data(0, Qt.ItemDataRole.UserRole) == dir_name:
                    target_item = item
                    break

        if not target_item:
            return

        # Expand and load existing children before inserting the temporary
        # editor item. Expanding after insertion rebuilds children and can
        # remove the inline editor for collapsed nested directories.
        if not target_item.isExpanded():
            target_item.setExpanded(True)

        new_item = QTreeWidgetItem()
        new_item.setText(0, "")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable)
        # Store the parent directory path in UserRole+2 to use during file creation
        new_item.setData(0, Qt.ItemDataRole.UserRole + 2, dir_name)
        if is_folder:
            self._show_directory_indicator(new_item)
        else:
            new_item.setIcon(0, _get_file_icon(".txt", style))
        target_item.addChild(new_item)
        self.tree.setCurrentItem(new_item)
        self._pending_new_item = new_item
        self._pending_new_kind = "folder" if is_folder else "file"
        self.tree.editItem(new_item, 0)
        self._bind_create_editor_live_updates(new_item)
        self._focus_inline_editor()

    def _cancel_pending_new_item(self) -> None:
        if self._pending_new_item is None:
            return
        parent = self._pending_new_item.parent()
        self._remove_item(self._pending_new_item)
        if parent and parent.childCount() == 0:
            self._show_directory_indicator(parent)
        self._pending_new_item = None
        self._pending_new_kind = None
        self._pending_editor = None

    def _finalize_pending_new_item(self) -> None:
        if self._pending_new_item is None:
            return

        item = self._pending_new_item
        new_name = item.text(0).strip()
        parent_dir = item.data(0, Qt.ItemDataRole.UserRole + 2)
        is_folder = self._pending_new_kind == "folder"

        if not new_name or not parent_dir:
            self._cancel_pending_new_item()
            return

        parent_path = self.workspace / parent_dir
        try:
            if is_folder:
                new_folder = parent_path / new_name
                new_folder.mkdir(exist_ok=False)
                new_dir_name = f"{parent_dir}/{new_name}" if parent_dir else new_name
                with QSignalBlocker(self.tree):
                    item.setData(0, Qt.ItemDataRole.UserRole, new_dir_name)
                    item.setData(0, Qt.ItemDataRole.UserRole + 2, "")
                logger.info("Created folder: {}", new_folder)
            else:
                new_file = parent_path / new_name
                new_file.touch(exist_ok=False)
                with QSignalBlocker(self.tree):
                    item.setIcon(0, _get_file_icon(new_file.suffix or ".txt", file_path=new_file))
                    item.setData(0, Qt.ItemDataRole.UserRole, parent_dir)
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, str(new_file))
                    item.setData(0, Qt.ItemDataRole.UserRole + 2, "")
                logger.info("Created file: {}", new_file)
        except FileExistsError:
            kind = "文件夹" if is_folder else "文件"
            QMessageBox.warning(self, "创建失败", f"{kind} '{new_name}' 已存在")
            self._remove_item(item)
        except Exception as e:
            title = "无法创建文件夹" if is_folder else "无法创建文件"
            QMessageBox.warning(self, "创建失败", f"{title}:\n{e}")
            self._remove_item(item)
        finally:
            self._pending_new_item = None
            self._pending_new_kind = None
            self._pending_editor = None

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
