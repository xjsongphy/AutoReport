"""Preview widget with a unified editor for all file types."""

from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import subprocess

import pandas as pd
from loguru import logger
from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTableView,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QMessageBox,
    QHBoxLayout,
)

from ..scale import scaled, scaled_size
from ..scintilla_utils import apply_scintilla_style, configure_lexer_colors
from ..theme import get_theme_colors
from .ui_utils import IconActionButton, render_svg_icon


class _TabAffordanceButton(QPushButton):
    """Single dirty-dot/close affordance to avoid cursor flicker from widget swaps."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("●", parent)
        self.setObjectName("tabAffordanceBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(12, 12)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setText("✕")
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setText("●")
        super().leaveEvent(event)


def _create_missing_viewer(path: Path) -> tuple[QLabel, str]:
    label = QLabel(f"文件不存在或已移动:\n{path}")
    label.setObjectName("editorPlaceholder")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label, "missing"


# ================================================================== #
#  File-type routing
# ================================================================== #

# suffix → (lexer_class_name, editable)
_SUFFIX_MAP: dict[str, tuple[str, bool]] = {
    ".py": ("QsciLexerPython", True),
    ".tex": ("QsciLexerTeX", True),
    ".json": ("QsciLexerJSON", True),
    ".yaml": ("QsciLexerYAML", True),
    ".yml": ("QsciLexerYAML", True),
    ".md": ("QsciLexerMarkdown", True),
    ".csv": ("", True),
    ".txt": ("", True),
}

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"})
_SPREADSHEET_SUFFIXES = frozenset({".xlsx", ".xls"})


# ================================================================== #
#  Viewer factory
# ================================================================== #


def _create_scintilla(path: Path, lexer_name: str) -> tuple:
    """Create a QScintilla editor for the given file."""
    from PyQt6.Qsci import QsciScintilla

    c = get_theme_colors()
    sci = QsciScintilla()
    apply_scintilla_style(
        sci,
        object_name="fileEditor",
        line_numbers=True,
        read_only=False,
        content_bg=c["editor_margin"],
    )

    if lexer_name:
        mod = __import__("PyQt6.Qsci", fromlist=[lexer_name])
        lexer_cls = getattr(mod, lexer_name, None)
        if lexer_cls:
            lexer = lexer_cls(sci)
            sci.setLexer(lexer)
            configure_lexer_colors(lexer, paper_color=c["editor_margin"])

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        sci.setText(content)
        # Update margin width after loading content
        from ..scintilla_utils import update_margin_width
        update_margin_width(sci)
        # Auto-update margin width when content changes
        sci.textChanged.connect(lambda: update_margin_width(sci))
    except Exception as e:
        sci.setText(f"无法读取文件: {e}")

    return sci, "scintilla"


def _create_pdf_viewer(path: Path) -> tuple:
    """Create an embedded QPdfView for the given PDF file."""
    from PyQt6.QtPdfWidgets import QPdfView

    c = get_theme_colors()
    doc = QPdfDocument(None)
    doc.load(path)

    view = QPdfView(None)
    view.setObjectName("filePdfView")
    view.setDocument(doc)
    view.setPageMode(QPdfView.PageMode.MultiPage)
    view.setStyleSheet(f"""
        QPdfView#filePdfView {{
            background-color: {c["editor_bg"]};
            border: none;
        }}
    """)

    return view, "pdf"


def _create_image_viewer(path: Path) -> tuple:
    """Create an image viewer with QPixmap."""
    c = get_theme_colors()
    label = QLabel()
    label.setObjectName("fileImageViewer")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(f"""
        QLabel#fileImageViewer {{
            background-color: {c["editor_bg"]};
            border: none;
        }}
    """)

    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        label.setText("无法加载图片")
    else:
        label.setPixmap(pixmap)
        label._source_pixmap = pixmap  # noqa: SLT001 — store for resize scaling

    return label, "image"


def _create_svg_viewer(path: Path) -> tuple:
    """Create an SVG viewer."""
    from PyQt6.QtSvgWidgets import QSvgWidget

    c = get_theme_colors()
    svg = QSvgWidget(str(path))
    svg.setObjectName("fileSvgViewer")
    svg.setStyleSheet(f"""
        QSvgWidget#fileSvgViewer {{
            background-color: {c["editor_bg"]};
            border: none;
        }}
    """)
    return svg, "image"


def _create_spreadsheet_viewer(path: Path) -> tuple:
    """Create a table viewer for xlsx/xls files using pandas."""
    c = get_theme_colors()

    try:
        df = pd.read_excel(path, engine="openpyxl" if path.suffix == ".xlsx" else None)
    except Exception as e:
        label = QLabel(f"无法读取表格: {e}")
        label.setObjectName("fileErrorLabel")
        return label, "table"

    from PyQt6.QtCore import QAbstractTableModel, QModelIndex

    class _PandasModel(QAbstractTableModel):
        def __init__(self, dataframe: pd.DataFrame, parent=None):
            super().__init__(parent)
            self._df = dataframe

        def rowCount(self, parent=QModelIndex()):  # noqa: N802
            return len(self._df)

        def columnCount(self, parent=QModelIndex()):  # noqa: N802
            return len(self._df.columns)

        def data(self, index, role=Qt.ItemDataRole.DisplayRole):
            if role == Qt.ItemDataRole.DisplayRole:
                val = self._df.iloc[index.row(), index.column()]
                return str(val) if not pd.isna(val) else ""
            return None

        def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
            if role == Qt.ItemDataRole.DisplayRole:
                if orientation == Qt.Orientation.Horizontal:
                    return str(self._df.columns[section])
                return str(section + 1)
            return None

    table = QTableView()
    table.setObjectName("fileTableView")
    table.setModel(_PandasModel(df))
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    # Enable horizontal scrollbar when content exceeds width
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    # Make columns resizable to allow horizontal scrolling
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setStretchLastSection(False)
    table.setStyleSheet(f"""
        QTableView#fileTableView {{
            background-color: {c["editor_bg"]};
            color: {c["fg"]};
            border: none;
            gridline-color: {c["border"]};
            font-size: 12px;
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            alternate-background-color: {c["surface"]};
        }}
        QHeaderView::section {{
            background-color: {c["surface"]};
            color: {c["fg"]};
            border: 1px solid {c["border"]};
            padding: 4px 8px;
            font-weight: {c["fw_semibold"]};
        }}
    """)

    return table, "table"


def _create_viewer(path: Path) -> tuple:
    """Create the appropriate viewer widget for a file path.

    Returns (widget, viewer_type).
    """
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _create_pdf_viewer(path)
    if suffix in _IMAGE_SUFFIXES:
        if suffix == ".svg":
            return _create_svg_viewer(path)
        return _create_image_viewer(path)
    if suffix in _SPREADSHEET_SUFFIXES:
        return _create_spreadsheet_viewer(path)

    # Text-based files
    lexer_name, editable = _SUFFIX_MAP.get(suffix, ("", True))
    return _create_scintilla(path, lexer_name)


# ================================================================== #
#  TabState
# ================================================================== #


@dataclass
class TabState:
    path: Path
    pinned: bool = False
    viewer: QWidget = field(default=None)  # type: ignore[assignment]
    viewer_type: str = ""
    modified: bool = False
    saved_text: str = ""
    missing: bool = False


def _tab_key(path: Path) -> str:
    return str(path.resolve())


# ================================================================== #
#  EditorPanel — one panel with tabs + content
# ================================================================== #


class EditorPanel(QWidget):
    """Single editor panel with a tab bar and stacked content viewers."""

    split_requested = pyqtSignal(str)  # file path string
    panel_emptied = pyqtSignal()  # emitted when last tab is closed
    tab_changed = pyqtSignal()  # emitted when tabs are opened/closed/switched

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tabs: dict[str, TabState] = {}  # key = str(path)
        self._tab_order: list[str] = []
        self._active_key: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab bar
        self._tab_bar = QTabBar()
        self._tab_bar.setObjectName("editorTabBar")
        self._tab_bar.setDrawBase(False)
        self._tab_bar.setExpanding(False)
        self._tab_bar.setMovable(True)
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setDocumentMode(True)
        self._tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tabCloseRequested.connect(self._on_close_requested)
        self._tab_bar.tabBarDoubleClicked.connect(self._on_double_click)
        self._tab_bar.customContextMenuRequested.connect(self._on_context_menu)
        self._tab_bar.setVisible(False)
        layout.addWidget(self._tab_bar)

        # Stacked content
        self._stack = QStackedWidget()
        self._stack.setObjectName("editorStack")
        self._stack.setContentsMargins(0, 6, 0, 0)
        layout.addWidget(self._stack, 1)

        # Placeholder
        self._placeholder = QLabel("选择文件查看")
        self._placeholder.setObjectName("editorPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._placeholder)

    @staticmethod
    def _tab_label_for_state(state: TabState) -> str:
        return state.path.name

    def open_file(self, path: Path, preview: bool = True) -> None:
        """Open a file. If preview=True, opens as preview tab (replaces existing preview)."""
        key = _tab_key(path)

        # Already open? Just switch to it.
        if key in self._tabs:
            idx = self._tab_order.index(key)
            self._tab_bar.setCurrentIndex(idx)
            return

        # If current tab is preview, close it first
        if self._active_key and not self._tabs[self._active_key].pinned:
            self._close_tab(self._active_key)

        # Create viewer
        missing = not path.exists()
        viewer, vtype = _create_missing_viewer(path) if missing else _create_viewer(path)
        self._stack.addWidget(viewer)

        state = TabState(path=path, pinned=not preview, viewer=viewer, viewer_type=vtype, missing=missing)
        self._tabs[key] = state
        self._tab_order.append(key)

        # Add tab
        tab_idx = self._tab_bar.addTab(self._tab_label_for_state(state))
        self._tab_bar.setCurrentIndex(tab_idx)
        self._tab_bar.setTabData(tab_idx, key)
        self._tab_bar.setVisible(False)

        if hasattr(viewer, "text") and callable(viewer.text):
            state.saved_text = viewer.text()
        if hasattr(viewer, "textChanged"):
            viewer.textChanged.connect(lambda _k=key: self._on_editor_text_changed(_k))
            self._on_editor_text_changed(key)

        self._active_key = key
        self.tab_changed.emit()

    def update_path(self, old_path: Path, new_path: Path) -> None:
        old_path = old_path.resolve()
        new_path = new_path.resolve()
        changed: list[tuple[str, str, TabState]] = []
        for key, state in list(self._tabs.items()):
            try:
                rel = state.path.resolve().relative_to(old_path)
            except ValueError:
                if state.path.resolve() != old_path:
                    continue
                rel = Path()
            updated_path = new_path / rel if str(rel) else new_path
            new_key = _tab_key(updated_path)
            changed.append((key, new_key, state))

        for old_key, new_key, state in changed:
            self._tabs.pop(old_key, None)
            state.path = Path(new_key)
            state.missing = not state.path.exists()
            self._tabs[new_key] = state
            idx = self._tab_order.index(old_key)
            self._tab_order[idx] = new_key
            if self._active_key == old_key:
                self._active_key = new_key

        if changed:
            self.tab_changed.emit()

    def _set_tab_modified(self, key: str, modified: bool) -> None:
        state = self._tabs.get(key)
        if not state or state.modified == modified:
            return
        state.modified = modified
        try:
            idx = self._tab_order.index(key)
        except ValueError:
            return
        self._tab_bar.setTabText(idx, self._tab_label_for_state(state))
        self.tab_changed.emit()

    def _on_editor_text_changed(self, key: str) -> None:
        state = self._tabs.get(key)
        if not state or not hasattr(state.viewer, "text"):
            return
        try:
            current = state.viewer.text()
        except Exception:
            return
        self._set_tab_modified(key, current != state.saved_text)

    def pin_active_tab(self) -> None:
        """Pin the current preview tab."""
        if self._active_key and self._active_key in self._tabs:
            state = self._tabs[self._active_key]
            if not state.pinned:
                state.pinned = True

    def has_tab(self, path: Path) -> bool:
        return _tab_key(path) in self._tabs

    def tab_count(self) -> int:
        return len(self._tabs)

    def active_path(self) -> Path | None:
        if self._active_key and self._active_key in self._tabs:
            return self._tabs[self._active_key].path
        return None

    def get_active_viewer(self) -> QWidget | None:
        if self._active_key and self._active_key in self._tabs:
            return self._tabs[self._active_key].viewer
        return None

    def move_tab_to(self, path: Path, other: "EditorPanel") -> None:
        """Move a tab from this panel to another panel."""
        key = _tab_key(path)
        if key not in self._tabs:
            return
        state = self._tabs.pop(key)
        old_index = self._tab_order.index(key)
        self._tab_order.remove(key)

        # Remove from our stack and tab bar
        self._tab_bar.removeTab(old_index)
        self._stack.removeWidget(state.viewer)

        # Add to other panel
        other._tabs[key] = state
        other._tab_order.append(key)
        other._stack.addWidget(state.viewer)
        tab_idx = other._tab_bar.addTab(other._tab_label_for_state(state))
        other._tab_bar.setCurrentIndex(tab_idx)
        other._tab_bar.setTabData(tab_idx, key)
        other._tab_bar.setVisible(False)
        other._active_key = key

        # Emit signals for both panels
        self.tab_changed.emit()
        other.tab_changed.emit()

        # Check if we're empty
        if not self._tabs:
            self._active_key = None
            self._tab_bar.setVisible(False)
            self._stack.setCurrentIndex(0)
            self.panel_emptied.emit()

    def close_all_tabs(self) -> None:
        """Close all tabs."""
        for key in list(self._tabs.keys()):
            self._close_tab(key)

    def close_other_tabs(self, keep_path: Path) -> None:
        """Close all tabs except the one matching keep_path."""
        keep_key = _tab_key(keep_path)
        for key in list(self._tabs.keys()):
            if key != keep_key:
                self._close_tab(key)

    def _close_tab(self, key: str) -> None:
        if key not in self._tabs:
            return
        state = self._tabs.pop(key)
        self._tab_order.remove(key)

        # Remove tab bar entry by stored key for deterministic behavior.
        for i in range(self._tab_bar.count()):
            if self._tab_bar.tabData(i) == key:
                self._tab_bar.removeTab(i)
                break

        # Remove widget from stack
        self._stack.removeWidget(state.viewer)
        state.viewer.deleteLater()

        # Update active
        if self._active_key == key:
            if self._tab_order:
                self._active_key = self._tab_order[-1]
                self._tab_bar.setCurrentIndex(len(self._tab_order) - 1)
            else:
                self._active_key = None
                self._tab_bar.setVisible(False)
                self._stack.setCurrentIndex(0)
                self.panel_emptied.emit()

        self.tab_changed.emit()

    def _on_tab_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._tab_order):
            self._stack.setCurrentIndex(0)
            return
        key = self._tab_order[index]
        self._active_key = key
        state = self._tabs[key]
        self._stack.setCurrentWidget(state.viewer)
        self.tab_changed.emit()

    def _on_close_requested(self, index: int) -> None:
        if 0 <= index < len(self._tab_order):
            self._close_tab(self._tab_order[index])

    def _on_double_click(self, index: int) -> None:
        if 0 <= index < len(self._tab_order):
            key = self._tab_order[index]
            state = self._tabs[key]
            if not state.pinned:
                state.pinned = True

    def _on_context_menu(self, pos) -> None:
        index = self._tab_bar.tabAt(pos)
        if index < 0:
            return
        key = self._tab_order[index]
        path = self._tabs[key].path

        menu = QMenu(self)
        menu.setObjectName("tabContextMenu")

        close_act = menu.addAction("关闭")
        close_others_act = menu.addAction("关闭其他")
        close_all_act = menu.addAction("关闭所有")

        action = menu.exec(self._tab_bar.mapToGlobal(pos))
        if action == close_act:
            self._close_tab(key)
        elif action == close_others_act:
            self.close_other_tabs(path)
        elif action == close_all_act:
            self.close_all_tabs()
        # Single editor mode: no split action.

    def apply_style(self) -> None:
        c = get_theme_colors()
        self._tab_bar.setStyleSheet(f"""
            QTabBar#editorTabBar {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
                min-height: 35px;
            }}
            QTabBar#editorTabBar::tab {{
                background-color: {c["surface"]};
                color: {c["tab_inactive_fg"]};
                border: none;
                border-right: 1px solid {c["border"]};
                padding: 6px 8px;
                min-width: 52px;
                max-width: 200px;
                min-height: 32px;
                margin: 1px 0 0 0;
            }}
            QTabBar#editorTabBar::tab:selected {{
                background-color: {c["tab_active_bg"]};
                color: {c["tab_active_fg"]};
                border-top: 2px solid {c["accent"]};
                border-right: 1px solid {c["border"]};
                border-bottom: 1px solid {c["tab_active_bg"]};
                margin: 1px 0 0 0;
            }}
            QTabBar#editorTabBar::tab:!selected:hover {{
                background-color: {c["tab_active_bg"]};
            }}
            QTabBar#editorTabBar::close-button {{
                subcontrol-position: right;
            }}
        """)
        self._placeholder.setStyleSheet(f"""
            QLabel#editorPlaceholder {{
                color: {c["muted"]};
                font-size: 13px;
                background-color: {c["editor_bg"]};
            }}
        """)


# ================================================================== #
#  PreviewWidget — top-level, same external API
# ================================================================== #


class PreviewWidget(QWidget):
    """Unified editor pane with tabs, regardless of file type."""

    selection_changed = pyqtSignal(str, str, int, int)
    file_changed = pyqtSignal(Path)  # Emitted when current file changes

    def __init__(self, workspace: Path):
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self._current_file: Path | None = None
        self._active_action_kind: str = ""
        self._tab_state_path = self.workspace / ".autoreport" / "open_tabs.json"
        self._restoring_tabs = False

        # Single editor panel
        self._panels: list[EditorPanel] = []
        self._general_splitter: QSplitter | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Unified header bar with title and tabs
        header = QWidget(self)
        header.setObjectName("previewHeader")
        header.setFixedHeight(36)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 12, 1)
        hl.setSpacing(4)

        # Unified tab bar for all open files
        self._unified_tab_bar = QTabBar()
        self._unified_tab_bar.setObjectName("previewTabBar")
        self._unified_tab_bar.setDrawBase(False)
        self._unified_tab_bar.setExpanding(False)
        self._unified_tab_bar.setMovable(True)
        self._unified_tab_bar.setTabsClosable(True)
        self._unified_tab_bar.setDocumentMode(True)
        self._unified_tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._unified_tab_bar.currentChanged.connect(self._on_unified_tab_changed)
        self._unified_tab_bar.tabCloseRequested.connect(self._on_unified_tab_close)
        self._unified_tab_bar.tabBarDoubleClicked.connect(self._on_unified_tab_double_click)
        self._unified_tab_bar.customContextMenuRequested.connect(self._on_unified_tab_context_menu)
        self._unified_tab_bar.setTabsClosable(False)
        self._unified_tab_bar.setMouseTracking(True)
        self._unified_tab_bar.installEventFilter(self)
        hl.addWidget(self._unified_tab_bar, 1)
        self._unified_tab_bar.setVisible(False)
        self._run_button = IconActionButton(
            text="",
            tooltip="编译 / 运行当前文件",
            object_name="explorerToolbarBtn",
            button_size=(22, 22),
            icon_size=(16, 16),
        )
        self._run_button.clicked.connect(self._on_run_clicked)
        self._run_button.setVisible(False)
        hl.addWidget(self._run_button)
        self._preview_button = IconActionButton(
            text="",
            tooltip="预览当前文件",
            object_name="explorerToolbarBtn",
            button_size=(22, 22),
            icon_size=(16, 16),
        )
        self._preview_button.clicked.connect(self._on_preview_clicked)
        self._preview_button.setVisible(False)
        hl.addWidget(self._preview_button)

        layout.addWidget(header)
        layout.addWidget(self._build_general_container(), 1)

        self._apply_style()

    def _build_general_container(self) -> QWidget:
        container = QWidget(self)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self._setup_general_mode()
        cl.addWidget(self._general_splitter, 1)
        return container

    def _setup_general_mode(self) -> None:
        self._general_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._general_splitter.setObjectName("editorSplitter")

        # Left panel (always present)
        left = EditorPanel()
        left.panel_emptied.connect(self._on_panel_emptied)
        left.tab_changed.connect(self._sync_tabs_from_panels)
        self._panels.append(left)
        self._general_splitter.addWidget(left)


    # ------------------------------------------------------------------ #
    #  Style
    # ------------------------------------------------------------------ #

    def _apply_style(self) -> None:
        c = get_theme_colors()
        self.setStyleSheet(f"""
            PreviewWidget {{
                background-color: {c["bg"]};
            }}
            #previewHeader {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
                padding: 0;
                padding-right: 1px;
            }}
            #previewFileCardsScroll {{
                background-color: transparent;
                border: none;
            }}
            #previewFileCardsWidget {{
                background-color: transparent;
            }}
            #previewSettingsBtn {{
                background-color: transparent;
                border: none;
                border-radius: {c["radius_sm"]};
                padding: 4px;
            }}
            #previewSettingsBtn:hover {{
                background-color: {c["hover"]};
            }}
            QSplitter#editorSplitter::handle {{
                background-color: {c["border"]};
                width: 2px;
            }}
            QTabBar#previewTabBar {{
                background-color: {c["panel_bg"]};
                border: none;
                min-height: 35px;
            }}
            QTabBar#previewTabBar::tab {{
                background-color: {c["panel_bg"]};
                color: {c["tab_inactive_fg"]};
                border: none;
                border-right: 1px solid {c["border"]};
                padding: 0 6px;
                min-height: 32px;
                margin: 1px 0 0 0;
                border-radius: 0px;
            }}
            QTabBar#previewTabBar::tab:selected {{
                background-color: {c["tab_active_bg"]};
                color: {c["tab_active_fg"]};
                border-top: 2px solid {c["accent"]};
                border-right: 1px solid {c["border"]};
                border-bottom: 1px solid {c["tab_active_bg"]};
                margin: 1px 0 0 0;
            }}
            QTabBar#previewTabBar::tab:!selected:hover {{
                background-color: {c["tab_active_bg"]};
            }}
            QTabBar#previewTabBar::tab:selected:hover {{
                background-color: {c["tab_active_bg"]};
            }}
            QTabBar#previewTabBar::close-button {{
                subcontrol-position: right;
                margin-right: 0px;
            }}
            #explorerToolbarBtn {{
                background-color: transparent;
                border: none;
                border-radius: {c["radius_sm"]};
                font-size: 14px;
                padding: 0;
                color: {c["fg"]};
            }}
            #explorerToolbarBtn:hover {{
                background-color: {c["tree_hover"]};
            }}
            QPushButton#tabAffordanceBtn {{
                background-color: transparent;
                border: none;
                border-radius: 3px;
                color: #ffffff;
                padding: 0;
                margin: 0;
                font-size: 11px;
            }}
            QPushButton#tabAffordanceBtn:hover {{
                background-color: {c["muted"]};
                color: #ffffff;
            }}
            QLabel#tabMissingBadge {{
                color: {c["status_error"]};
                background: transparent;
                border: none;
                font-weight: {c["fw_bold"]};
                font-size: 11px;
                padding: 0 3px 0 0;
            }}
            QLabel#tabDuplicatePath {{
                color: {c["muted"]};
                background: transparent;
                border: none;
                font-size: 11px;
                padding: 0 4px 0 0;
            }}
            QLabel#tabAffordanceSpacer {{
                color: transparent;
                background: transparent;
                border: none;
                font-size: 12px;
                padding: 0;
                margin: 0;
            }}
        """)

        for panel in self._panels:
            panel.apply_style()

    # ------------------------------------------------------------------ #
    #  File switching
    # ------------------------------------------------------------------ #

    def load_file(self, file_path: Path) -> None:
        file_path = Path(file_path).resolve()
        if not self.isVisible():
            self.show()
        self._current_file = file_path
        self._panels[-1].open_file(file_path, preview=False)
        self._connect_selection_tracking()
        self._sync_tabs_from_panels()

        # Emit file changed signal
        self.file_changed.emit(file_path)

    def _add_unified_tab(self, file_path: Path) -> None:
        """Add a tab to the unified tab bar."""
        # Check if already exists
        for i in range(self._unified_tab_bar.count()):
            if self._unified_tab_bar.tabData(i) == str(file_path):
                self._unified_tab_bar.setCurrentIndex(i)
                return

        # Add new tab
        tab_idx = self._unified_tab_bar.addTab(file_path.name)
        self._unified_tab_bar.setTabData(tab_idx, str(file_path))
        self._unified_tab_bar.setCurrentIndex(tab_idx)

    def _sync_tabs_from_panels(self) -> None:
        """Sync unified tab bar with tabs from all panels."""
        active_key = _tab_key(self._current_file) if self._current_file else None
        if not active_key:
            for panel in self._panels:
                if panel._active_key:
                    active_key = panel._active_key
                    break

        with QSignalBlocker(self._unified_tab_bar):
            while self._unified_tab_bar.count() > 0:
                self._unified_tab_bar.removeTab(0)

            current_index = -1
            for panel in self._panels:
                for key in panel._tab_order:
                    state = panel._tabs[key]
                    label = state.path.name
                    tab_idx = self._unified_tab_bar.addTab(label)
                    self._unified_tab_bar.setTabData(tab_idx, key)
                    if state.missing or not state.path.exists():
                        state.missing = True
                        self._unified_tab_bar.setTabTextColor(tab_idx, QColor(get_theme_colors()["status_error"]))
                    if key == active_key or (current_index < 0 and key == panel._active_key):
                        current_index = tab_idx

            if current_index >= 0:
                self._unified_tab_bar.setCurrentIndex(current_index)
        self._unified_tab_bar.setVisible(self._unified_tab_bar.count() > 0)
        self._refresh_unified_tab_affordances()
        self._update_file_actions()
        if not self._restoring_tabs:
            self.save_open_tabs()

        if self._unified_tab_bar.currentIndex() >= 0:
            current_key = self._unified_tab_bar.tabData(self._unified_tab_bar.currentIndex())
            self._current_file = Path(current_key) if current_key else None
        elif self._unified_tab_bar.count() == 0:
            self._current_file = None

    def _on_unified_tab_changed(self, index: int) -> None:
        """Handle unified tab bar change."""
        if index < 0:
            self._current_file = None
            self.file_changed.emit(Path())  # Emit with empty path
            return

        file_path_str = self._unified_tab_bar.tabData(index)
        if not file_path_str:
            self._current_file = None
            self.file_changed.emit(Path())  # Emit with empty path
            return

        file_path = Path(file_path_str)
        self._current_file = file_path

        # Find the panel that has this file and switch to it
        for panel in self._panels:
            key = _tab_key(file_path)
            if key in panel._tabs:
                idx = panel._tab_order.index(key)
                panel._tab_bar.setCurrentIndex(idx)
                break

        # Emit file changed signal
        self.file_changed.emit(file_path)
        self._connect_selection_tracking()
        self._refresh_unified_tab_affordances()
        self._update_file_actions()

    def _on_unified_tab_double_click(self, index: int) -> None:
        """Pin a preview tab and switch to it on double-click."""
        if index < 0:
            return

        file_path_str = self._unified_tab_bar.tabData(index)
        if not file_path_str:
            return

        self._on_unified_tab_changed(index)
        key = _tab_key(Path(file_path_str))
        for panel in self._panels:
            if key in panel._tabs:
                panel._tabs[key].pinned = True
                break

    def _on_unified_tab_close(self, index: int) -> None:
        """Handle unified tab close."""
        file_path_str = self._unified_tab_bar.tabData(index)
        if not file_path_str:
            return

        file_path = Path(file_path_str)

        # Close tab in panel
        for panel in self._panels:
            key = _tab_key(file_path)
            if key in panel._tabs:
                panel._close_tab(key)
                break
        # Sync tabs
        self._sync_tabs_from_panels()

        # Emit file changed signal with None or current active file
        active_file = self.current_file
        self.file_changed.emit(active_file if active_file else Path())
        self._refresh_unified_tab_affordances()
        self._update_file_actions()

    def _on_unified_tab_close_by_key(self, key: str) -> None:
        for i in range(self._unified_tab_bar.count()):
            if self._unified_tab_bar.tabData(i) == key:
                self._on_unified_tab_close(i)
                return

    def update_open_path(self, old_path: Path, new_path: Path) -> None:
        for panel in self._panels:
            panel.update_path(old_path, new_path)
        old_resolved = old_path.resolve()
        if self._current_file and self._current_file.resolve() == old_resolved:
            self._current_file = new_path.resolve()
        self._sync_tabs_from_panels()

    def save_open_tabs(self) -> None:
        tabs = []
        for panel in self._panels:
            for key in panel._tab_order:
                state = panel._tabs[key]
                try:
                    rel_path = str(state.path.relative_to(self.workspace))
                except ValueError:
                    rel_path = str(state.path)
                tabs.append(rel_path)
        active = None
        if self.current_file:
            try:
                active = str(self.current_file.relative_to(self.workspace))
            except ValueError:
                active = str(self.current_file)
        data = {"tabs": tabs, "active": active}
        try:
            self._tab_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._tab_state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("Failed to save open tabs: {}", self._tab_state_path)

    def restore_open_tabs(self) -> None:
        if not self._tab_state_path.exists():
            return
        try:
            data = json.loads(self._tab_state_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Failed to read open tabs: {}", self._tab_state_path)
            return
        tabs = data.get("tabs") if isinstance(data, dict) else None
        if not isinstance(tabs, list):
            return
        active = data.get("active") if isinstance(data, dict) else None
        self._restoring_tabs = True
        try:
            for item in tabs:
                if not isinstance(item, str) or not item:
                    continue
                path = Path(item)
                if not path.is_absolute():
                    path = self.workspace / path
                self.load_file(path)
            if isinstance(active, str) and active:
                active_path = Path(active)
                if not active_path.is_absolute():
                    active_path = self.workspace / active_path
                key = _tab_key(active_path)
                for i in range(self._unified_tab_bar.count()):
                    if self._unified_tab_bar.tabData(i) == key:
                        self._unified_tab_bar.setCurrentIndex(i)
                        break
        finally:
            self._restoring_tabs = False
        self._sync_tabs_from_panels()

    def _on_unified_tab_context_menu(self, pos) -> None:
        """Show context menu for unified tab bar."""
        index = self._unified_tab_bar.tabAt(pos)
        if index < 0:
            return

        file_path_str = self._unified_tab_bar.tabData(index)
        if not file_path_str:
            return

        file_path = Path(file_path_str)

        menu = QMenu(self)
        menu.setObjectName("tabContextMenu")

        close_act = menu.addAction("关闭")
        close_others_act = menu.addAction("关闭其他")
        close_all_act = menu.addAction("关闭所有")

        action = menu.exec(self._unified_tab_bar.mapToGlobal(pos))

        if action == close_act:
            self._on_unified_tab_close(index)
        elif action == close_others_act:
            # Close all except this one
            for i in range(self._unified_tab_bar.count() - 1, -1, -1):
                if i != index:
                    self._on_unified_tab_close(i)
        elif action == close_all_act:
            # Close all tabs
            for i in range(self._unified_tab_bar.count() - 1, -1, -1):
                self._on_unified_tab_close(i)

    def _find_tab_state(self, key: str) -> TabState | None:
        for panel in self._panels:
            state = panel._tabs.get(key)
            if state is not None:
                return state
        return None

    def _refresh_unified_tab_affordances(self) -> None:
        duplicate_names = self._duplicate_tab_names()

        def _wrap_affordance(
            inner: QWidget,
            hand_cursor: bool,
            *,
            path_text: str = "",
            missing: bool = False,
        ) -> QWidget:
            host = QWidget(self._unified_tab_bar)
            hl = QHBoxLayout(host)
            hl.setContentsMargins(0, 0, 6, 0)
            hl.setSpacing(0)
            hl.addStretch(1)
            if path_text:
                path_label = QLabel(path_text, host)
                path_label.setObjectName("tabDuplicatePath")
                path_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                path_label.setMaximumWidth(140)
                hl.addWidget(path_label)
            if missing:
                missing_label = QLabel("D", host)
                missing_label.setObjectName("tabMissingBadge")
                missing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hl.addWidget(missing_label)
            hl.addWidget(inner)
            host.setFixedSize(18 + (140 if path_text else 0) + (12 if missing else 0), 12)
            if hand_cursor:
                host.setCursor(Qt.CursorShape.PointingHandCursor)
                inner.setCursor(Qt.CursorShape.PointingHandCursor)
            return host

        for i in range(self._unified_tab_bar.count()):
            key = self._unified_tab_bar.tabData(i)
            if not key:
                self._unified_tab_bar.setTabButton(i, QTabBar.ButtonPosition.RightSide, None)
                continue
            state = self._find_tab_state(key)
            path_text = self._duplicate_path_text(state) if state and state.path.name in duplicate_names else ""
            missing = bool(state and (state.missing or not state.path.exists()))
            if state and state.modified:
                btn = _TabAffordanceButton(self._unified_tab_bar)
                btn.clicked.connect(lambda _=False, _k=key: self._on_unified_tab_close_by_key(_k))
                self._unified_tab_bar.setTabButton(
                    i,
                    QTabBar.ButtonPosition.RightSide,
                    _wrap_affordance(btn, True, path_text=path_text, missing=missing),
                )
            elif self._unified_tab_bar.currentIndex() == i:
                btn = QPushButton("✕", self._unified_tab_bar)
                btn.setObjectName("tabAffordanceBtn")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedSize(12, 12)
                btn.clicked.connect(lambda _=False, _k=key: self._on_unified_tab_close_by_key(_k))
                self._unified_tab_bar.setTabButton(
                    i,
                    QTabBar.ButtonPosition.RightSide,
                    _wrap_affordance(btn, True, path_text=path_text, missing=missing),
                )
            elif missing:
                btn = QPushButton("✕", self._unified_tab_bar)
                btn.setObjectName("tabAffordanceBtn")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedSize(12, 12)
                btn.clicked.connect(lambda _=False, _k=key: self._on_unified_tab_close_by_key(_k))
                self._unified_tab_bar.setTabButton(
                    i,
                    QTabBar.ButtonPosition.RightSide,
                    _wrap_affordance(btn, True, path_text=path_text, missing=True),
                )
            else:
                spacer = QLabel("●", self._unified_tab_bar)
                spacer.setObjectName("tabAffordanceSpacer")
                spacer.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spacer.setFixedSize(12, 12)
                self._unified_tab_bar.setTabButton(
                    i,
                    QTabBar.ButtonPosition.RightSide,
                    _wrap_affordance(spacer, False, path_text=path_text),
                )

    def _duplicate_tab_names(self) -> set[str]:
        counts: dict[str, int] = {}
        for panel in self._panels:
            for state in panel._tabs.values():
                counts[state.path.name] = counts.get(state.path.name, 0) + 1
        return {name for name, count in counts.items() if count > 1}

    def _duplicate_path_text(self, state: TabState | None) -> str:
        if state is None:
            return ""
        try:
            rel = state.path.relative_to(self.workspace)
        except ValueError:
            rel = state.path
        parent = rel.parent
        if str(parent) in ("", "."):
            return ""
        return str(parent)

    def eventFilter(self, obj, event):  # noqa: N802
        return super().eventFilter(obj, event)

    def _on_panel_emptied(self) -> None:
        pass

    def _on_split_requested(self, _file_path: str) -> None:
        # Split mode was removed; keep a no-op handler for signal compatibility.
        return

    def _update_file_actions(self) -> None:
        c = get_theme_colors()
        self._active_action_kind = ""
        self._run_button.setVisible(False)
        self._preview_button.setVisible(False)
        self._run_button.setIcon(render_svg_icon("run", QColor(c["fg"]), size=16))
        self._preview_button.setIcon(render_svg_icon("preview", QColor(c["fg"]), size=16))
        if not self._current_file:
            return

        suffix = self._current_file.suffix.lower()
        if suffix == ".tex":
            self._active_action_kind = "tex"
            self._run_button.setVisible(True)
            self._preview_button.setVisible(True)
        elif suffix == ".py":
            self._active_action_kind = "python"
            self._run_button.setVisible(True)

    def _on_run_clicked(self) -> None:
        if not self._current_file:
            return
        if self._active_action_kind == "tex":
            self._compile_tex(self._current_file)
            return
        if self._active_action_kind == "python":
            try:
                subprocess.Popen(["python", str(self._current_file)], cwd=str(self._current_file.parent))
            except Exception as exc:
                QMessageBox.warning(self, "运行失败", f"无法运行 Python 文件:\n{exc}")

    def _on_preview_clicked(self) -> None:
        if not self._current_file:
            return
        if self._active_action_kind != "tex":
            return
        pdf_path = self._current_file.with_suffix(".pdf")
        if not pdf_path.exists():
            QMessageBox.information(self, "未找到预览文件", f"请先编译生成 PDF:\n{pdf_path.name}")
            return
        self.load_file(pdf_path)

    def _compile_tex(self, tex_path: Path) -> None:
        compiler = shutil.which("xelatex") or shutil.which("lualatex") or shutil.which("pdflatex")
        if not compiler:
            QMessageBox.warning(self, "编译失败", "未检测到 LaTeX 编译器（xelatex/lualatex/pdflatex）。")
            return
        try:
            subprocess.run(
                [compiler, "-interaction=nonstopmode", tex_path.name],
                cwd=str(tex_path.parent),
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            QMessageBox.information(self, "编译完成", f"{tex_path.name} 已编译完成。")
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or exc.stdout or "").splitlines()[-6:]
            detail = "\n".join(tail) if tail else "无详细输出"
            QMessageBox.warning(self, "编译失败", f"{tex_path.name}\n\n{detail}")
        except Exception as exc:
            QMessageBox.warning(self, "编译失败", f"{tex_path.name}\n\n{exc}")

    # ------------------------------------------------------------------ #
    #  Selection tracking (for general mode editors)
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self) -> None:
        if not self._current_file:
            return

        panel = self._panels[-1] if self._panels else None
        if not panel:
            return

        viewer = panel.get_active_viewer()
        if not viewer:
            return

        from PyQt6.Qsci import QsciScintilla

        if isinstance(viewer, QsciScintilla):
            selected_text = viewer.selectedText()
            rel_path = str(self._current_file.relative_to(self.workspace))
            if not selected_text:
                self.selection_changed.emit(rel_path, "", 0, 0)
                return
            line_from, _, line_to, _ = viewer.getSelection()
            start_line = line_from + 1
            end_line = line_to + 1
            self.selection_changed.emit(rel_path, selected_text, start_line, end_line)

    def _connect_selection_tracking(self) -> None:
        if not self._panels:
            return
        viewer = self._panels[-1].get_active_viewer()
        if not viewer or viewer.property("selection_tracking_connected"):
            return

        from PyQt6.Qsci import QsciScintilla

        if isinstance(viewer, QsciScintilla):
            viewer.selectionChanged.connect(self._on_selection_changed)
            viewer.setProperty("selection_tracking_connected", True)

    # ------------------------------------------------------------------ #
    #  Public API (preserved)
    # ------------------------------------------------------------------ #

    def get_selected_context(self) -> tuple[str, str, int, int] | None:
        if not self._current_file:
            return None

        if self._panels:
            viewer = self._panels[-1].get_active_viewer()
            from PyQt6.Qsci import QsciScintilla

            if isinstance(viewer, QsciScintilla):
                text = viewer.selectedText()
                if text:
                    line_from, _, line_to, _ = viewer.getSelection()
                    rel = str(self._current_file.relative_to(self.workspace))
                    return (rel, text, line_from + 1, line_to + 1)
        return None

    def clear_selection(self) -> None:
        if self._panels:
            viewer = self._panels[-1].get_active_viewer()
            from PyQt6.Qsci import QsciScintilla

            if isinstance(viewer, QsciScintilla):
                viewer.setSelection(-1, -1, -1, -1)

    def save_current_file(self) -> bool:
        """Save active text editor content to disk.

        Returns True when a file was saved; False when no editable text file is active.
        """
        if not self._current_file:
            return False

        from PyQt6.Qsci import QsciScintilla

        key = _tab_key(self._current_file)
        for panel in self._panels:
            state = panel._tabs.get(key)
            if state is None:
                continue
            if not isinstance(state.viewer, QsciScintilla):
                return False

            try:
                self._current_file.write_text(state.viewer.text(), encoding="utf-8")
            except Exception:
                logger.exception("Failed saving file: {}", self._current_file)
                return False

            state.viewer.setModified(False)
            panel._set_tab_modified(key, False)
            state.saved_text = state.viewer.text()
            self._sync_tabs_from_panels()
            panel.tab_changed.emit()
            return True
        return False

    def refresh_pdf(self) -> None:
        # Kept for API compatibility; unified editor has no dedicated PDF refresh path.
        return

    @property
    def current_file(self) -> Path | None:
        if self._panels:
            return self._panels[-1].active_path()
        return None
