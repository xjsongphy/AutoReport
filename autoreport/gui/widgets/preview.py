"""Preview widget with a unified editor for all file types."""

from dataclasses import dataclass, field
import json
from pathlib import Path
from pathlib import PureWindowsPath
import shutil
import subprocess

import pandas as pd
from loguru import logger
from PyQt6.QtCore import QEvent, QSignalBlocker, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QFrame,
    QHeaderView,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..scintilla_utils import apply_scintilla_style, configure_lexer_colors
from ..theme import get_theme_colors, scrollbar_stylesheet
from .ui_utils import IconActionButton, create_isolated_context_menu, render_svg_icon


def question_box(*args, **kwargs):
    from ..dialogs import question_box as _question_box
    return _question_box(*args, **kwargs)


def warning_box(*args, **kwargs):
    from ..dialogs import warning_box as _warning_box
    return _warning_box(*args, **kwargs)


def information_box(*args, **kwargs):
    from ..dialogs import information_box as _information_box
    return _information_box(*args, **kwargs)


class _EmbeddedImageLabel(QLabel):
    """Image label that always fits image into available viewport."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._source_pixmap: QPixmap | None = None
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setScaledContents(False)

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self._apply_scaled_pixmap()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_scaled_pixmap()

    def _apply_scaled_pixmap(self) -> None:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return
        target = self.size()
        if target.width() <= 1 or target.height() <= 1:
            return
        dpr = max(1.0, self.devicePixelRatioF())
        target_px_w = max(1, int(target.width() * dpr))
        target_px_h = max(1, int(target.height() * dpr))
        source_px_w = self._source_pixmap.width()
        source_px_h = self._source_pixmap.height()

        # Do not upscale beyond source resolution by default; this avoids
        # blurry rendering when the viewport is larger than the image.
        if source_px_w <= target_px_w and source_px_h <= target_px_h:
            display = self._source_pixmap
        else:
            display = self._source_pixmap.scaled(
                target_px_w,
                target_px_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        display.setDevicePixelRatio(dpr)
        self.setPixmap(display)


class _TabAffordanceButton(QPushButton):
    """Dirty-dot affordance shown when a tab has unsaved changes."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("•", parent)
        self.setObjectName("tabAffordanceBtn")
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFixedSize(12, 12)
        self.setEnabled(False)


class _TabCloseButton(QPushButton):
    """Close affordance shown for hovered/active tabs."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("✕", parent)
        self.setObjectName("tabAffordanceBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(12, 12)
def _create_missing_viewer(path: Path) -> tuple[QLabel, str]:
    label = QLabel(f"文件不存在或已移动\n{path}")
    label.setObjectName("editorPlaceholder")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label, "missing"


# ================================================================== #
#  File-type routing
# ================================================================== #

# suffix 鈫?(lexer_class_name, editable)
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
        content_bg=c["editor_bg"],
    )

    if lexer_name:
        mod = __import__("PyQt6.Qsci", fromlist=[lexer_name])
        lexer_cls = getattr(mod, lexer_name, None)
        if lexer_cls:
            lexer = lexer_cls(sci)
            sci.setLexer(lexer)
            configure_lexer_colors(lexer, paper_color=c["editor_bg"])

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        sci.setText(content)
        # Update margin width after loading content
        from ..scintilla_utils import update_margin_width
        update_margin_width(sci)
        # Auto-update margin width when content changes
        sci.textChanged.connect(lambda: update_margin_width(sci))
        if lexer_name == "QsciLexerTeX":
            # TeX: QScintilla lumps \commands into the Text style, so color
            # them post-lex like VSCode (support.function.general.tex -> gold).
            from ..scintilla_utils import attach_tex_command_coloring
            attach_tex_command_coloring(sci)
        elif lexer_name == "QsciLexerMarkdown":
            # Markdown: VSCode colors whole heading lines and embeds language
            # grammars inside ```lang blocks; both done post-lex.
            from ..scintilla_utils import attach_markdown_post_styling
            attach_markdown_post_styling(sci)
    except Exception as e:
        sci.setText(f"无法读取文件: {e}")

    return sci, "scintilla"


def _create_pdf_viewer(path: Path) -> tuple:
    """Create an embedded QPdfView for the given PDF file."""
    from PyQt6.QtPdfWidgets import QPdfView

    c = get_theme_colors()
    doc = QPdfDocument(None)
    # QPdfDocument.load expects str/QIODevice, not pathlib.Path.
    doc.load(str(path))
    if doc.status() != QPdfDocument.Status.Ready:
        label = QLabel(f"PDF 预览失败：{path.name}")
        label.setObjectName("editorPlaceholder")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label, "pdf"

    view = QPdfView(None)
    view.setObjectName("filePdfView")
    view.setDocument(doc)
    # Keep a strong reference to avoid document being GC'd and rendering blank.
    view._pdf_document = doc  # noqa: SLT001
    view.setPageMode(QPdfView.PageMode.MultiPage)
    view.setZoomMode(QPdfView.ZoomMode.FitInView)
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
    label = _EmbeddedImageLabel()
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
        label.set_source_pixmap(pixmap)

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
#  EditorPanel 鈥?one panel with tabs + content
# ================================================================== #


class EditorPanel(QWidget):
    """Single editor panel with a tab bar and stacked content viewers."""

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
        except Exception as e:
            logger.debug("Failed reading viewer text for modified check: {}", e)
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

    def apply_tab_order(self, new_order: list[str]) -> None:
        """Apply a new tab ordering (e.g. after a drag-reorder).

        Reorders ``_tab_order`` and rebuilds the (hidden) per-panel tab bar so
        its indices stay aligned with ``_tab_order`` — many operations look up a
        key's position in ``_tab_order`` and feed it back into the tab bar.
        ``new_order`` must be a permutation of the current keys.  This is silent:
        it does not emit ``tab_changed``, so the caller is responsible for any
        follow-up sync/persistence.
        """
        if not new_order or set(new_order) != set(self._tab_order):
            return
        if list(new_order) == self._tab_order:
            return
        self._tab_order = list(new_order)
        active_key = self._active_key
        with QSignalBlocker(self._tab_bar):
            while self._tab_bar.count():
                self._tab_bar.removeTab(0)
            for key in self._tab_order:
                state = self._tabs[key]
                idx = self._tab_bar.addTab(self._tab_label_for_state(state))
                self._tab_bar.setTabData(idx, key)
            if active_key in self._tab_order:
                self._tab_bar.setCurrentIndex(self._tab_order.index(active_key))

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

        menu = create_isolated_context_menu(self)

        close_act = menu.addAction("Close")
        close_others_act = menu.addAction("Close Others")
        close_all_act = menu.addAction("Close All")

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
                border-top: 2px solid {c["buttonBlue"]};
                border-right: 1px solid {c["border"]};
                border-bottom: 1px solid {c["tab_active_bg"]};
                margin: 1px 0 0 0;
            }}
            QTabBar#editorTabBar::tab:!selected:hover {{
                background-color: {c["hover"]};
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
#  PreviewWidget 鈥?top-level, same external API
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
        self._tab_area_hovered = False
        self._tab_hovered_index = -1

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
        self._unified_tab_bar.setUsesScrollButtons(False)
        self._unified_tab_bar.setElideMode(Qt.TextElideMode.ElideNone)
        self._unified_tab_bar.setDocumentMode(True)
        self._unified_tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._unified_tab_bar.currentChanged.connect(self._on_unified_tab_changed)
        self._unified_tab_bar.tabCloseRequested.connect(self._on_unified_tab_close)
        self._unified_tab_bar.tabBarDoubleClicked.connect(self._on_unified_tab_double_click)
        self._unified_tab_bar.tabMoved.connect(self._on_unified_tab_moved)
        self._unified_tab_bar.customContextMenuRequested.connect(self._on_unified_tab_context_menu)
        self._unified_tab_bar.setTabsClosable(False)
        self._unified_tab_bar.setMouseTracking(True)
        self._unified_tab_bar.installEventFilter(self)
        self._unified_tab_bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._tab_scroll = QScrollArea(self)
        self._tab_scroll.setObjectName("previewTabScrollArea")
        self._tab_scroll.setWidget(self._unified_tab_bar)
        self._tab_scroll.setWidgetResizable(False)
        self._tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tab_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._tab_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tab_scroll.viewport().setMouseTracking(True)
        self._tab_scroll.installEventFilter(self)
        self._tab_scroll.viewport().installEventFilter(self)

        hl.addWidget(self._tab_scroll, 1)
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

    def _update_tab_scrollbar_visibility(self) -> None:
        """Show horizontal tab scrollbar only when hovering the tab-strip area."""
        hovered = (
            self._tab_scroll.underMouse()
            or self._tab_scroll.viewport().underMouse()
            or self._unified_tab_bar.underMouse()
        )
        self._tab_area_hovered = hovered
        policy = (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if hovered
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        if self._tab_scroll.horizontalScrollBarPolicy() != policy:
            self._tab_scroll.setHorizontalScrollBarPolicy(policy)

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
                background-color: {c["surface"]};
                border: none;
                min-height: 35px;
            }}
            QTabBar#previewTabBar::tab {{
                background-color: {c["surface"]};
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
                border-top: 2px solid {c["buttonBlue"]};
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
            QTabBar#previewTabBar QToolButton {{
                width: 0px;
                max-width: 0px;
                border: none;
                padding: 0;
                margin: 0;
            }}
            QScrollArea#previewTabScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollArea#previewTabScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            {scrollbar_stylesheet(
                selector="QScrollArea#previewTabScrollArea QScrollBar",
                orientation="horizontal",
                background_color="transparent",
                thickness="6px",
                min_handle_extent="24px",
                radius="0px",
                colors=c,
            )}
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
                color: {c["tab_inactive_fg"]};
                padding: 0;
                margin: 0;
                font-size: 11px;
            }}
            QPushButton#tabAffordanceBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
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
                padding: 0 1px 0 0;
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

        # Force the tab-strip horizontal scrollbar to a transparent trough
        # directly on the widget — the descendant-selector rule above is
        # unreliable across QScrollArea's viewport boundary.
        self._tab_scroll.horizontalScrollBar().setStyleSheet(
            scrollbar_stylesheet(
                orientation="horizontal",
                background_color="transparent",
                thickness="6px",
                min_handle_extent="24px",
                radius="0px",
                colors=c,
            )
        )

        for panel in self._panels:
            panel.apply_style()

    # ------------------------------------------------------------------ #
    #  File switching
    # ------------------------------------------------------------------ #

    def _resolve_cross_platform_path(self, value: str | Path) -> Path:
        """Resolve persisted/opened file paths across Windows/macOS separators.

        - Normalizes backslashes to forward slashes for project-relative paths.
        - Maps relative paths into current workspace.
        - Best-effort maps Windows absolute paths to current workspace suffix.
        """
        raw = str(value).strip()
        if not raw:
            return self.workspace

        if raw.startswith("project://"):
            raw = raw[len("project://"):]

        normalized = raw.replace("\\", "/")
        path = Path(normalized)
        if path.is_absolute():
            return path.resolve()

        # On POSIX, Windows absolute paths (e.g. C:\repo\...) are not absolute.
        win_path = PureWindowsPath(raw)
        if win_path.is_absolute():
            win_parts = [p for p in win_path.parts if p != win_path.anchor]
            workspace_name = self.workspace.name
            if workspace_name in win_parts:
                idx = win_parts.index(workspace_name)
                rel = Path(*win_parts[idx + 1:]) if idx + 1 < len(win_parts) else Path()
                return (self.workspace / rel).resolve()
            # Fallback: keep basename to avoid impossible cross-disk absolute mapping.
            return (self.workspace / win_path.name).resolve()

        return (self.workspace / path).resolve()

    def load_file(self, file_path: Path) -> None:
        file_path = self._resolve_cross_platform_path(file_path)
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
                    if key == active_key or (current_index < 0 and key == panel._active_key):
                        current_index = tab_idx

            if current_index >= 0:
                self._unified_tab_bar.setCurrentIndex(current_index)
            self._apply_unified_tab_text_colors()
        self._unified_tab_bar.setVisible(self._unified_tab_bar.count() > 0)
        self._refresh_unified_tab_affordances()
        self._sync_unified_tab_bar_width()
        self._update_file_actions()
        if not self._restoring_tabs:
            self.save_open_tabs()

        if self._unified_tab_bar.currentIndex() >= 0:
            current_key = self._unified_tab_bar.tabData(self._unified_tab_bar.currentIndex())
            self._current_file = Path(current_key) if current_key else None
        elif self._unified_tab_bar.count() == 0:
            self._current_file = None

    def _on_unified_tab_moved(self, from_index: int, to_index: int) -> None:
        """Persist a drag-reorder back into the panels' ``_tab_order``.

        ``QTabBar`` moves the tab visually on drag, but ``_tab_order`` is the
        source of truth — without this handler the next ``_sync_tabs_from_panels``
        rebuild would snap the tab back to its old position.  We read the new
        arrangement straight off the unified bar (Qt carries ``tabData`` with the
        moved tab) and mirror it into each owning panel, then persist.
        """
        global_order = [
            self._unified_tab_bar.tabData(i)
            for i in range(self._unified_tab_bar.count())
        ]
        global_order = [k for k in global_order if k]
        if not global_order:
            return
        for panel in self._panels:
            new_order = [k for k in global_order if k in panel._tabs]
            panel.apply_tab_order(new_order)
        if not self._restoring_tabs:
            self.save_open_tabs()

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
        self._apply_unified_tab_text_colors()
        self._refresh_unified_tab_affordances()
        self._update_file_actions()

    def _apply_unified_tab_text_colors(self) -> None:
        c = get_theme_colors()
        active = self._unified_tab_bar.currentIndex()
        for i in range(self._unified_tab_bar.count()):
            key = self._unified_tab_bar.tabData(i)
            state = self._find_tab_state(key) if key else None
            if state and (state.missing or not state.path.exists()):
                color = QColor(c["status_error"])
            elif i == active:
                color = QColor(c["tab_active_fg"])
            else:
                color = QColor(c["tab_inactive_fg"])
            self._unified_tab_bar.setTabTextColor(i, color)

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

    def _on_unified_tab_close(self, index: int) -> bool:
        """Handle unified tab close."""
        file_path_str = self._unified_tab_bar.tabData(index)
        if not file_path_str:
            return False

        file_path = Path(file_path_str)
        key = _tab_key(file_path)
        state = self._find_tab_state(key)
        if state and state.modified:
            choice = self._confirm_close_modified_tab(state.path)
            if choice == QMessageBox.StandardButton.Cancel:
                return False
            if choice == QMessageBox.StandardButton.Save:
                if not self._save_tab_by_key(key):
                    return False

        # Close tab in panel
        for panel in self._panels:
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
        return True

    def _on_unified_tab_close_by_key(self, key: str) -> None:
        for i in range(self._unified_tab_bar.count()):
            if self._unified_tab_bar.tabData(i) == key:
                self._on_unified_tab_close(i)
                return

    def _confirm_close_modified_tab(self, path: Path) -> QMessageBox.StandardButton:
        return question_box(
            self,
            "保存更改",
            f"是否保存对 {path.name} 的更改？",
            buttons=(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
            ),
            default=QMessageBox.StandardButton.Save,
            affirmative=QMessageBox.StandardButton.Save,
        )

    def _save_tab_by_key(self, key: str) -> bool:
        state = self._find_tab_state(key)
        if state is None:
            return True
        viewer = state.viewer
        if not hasattr(viewer, "text"):
            return True
        try:
            content = viewer.text()
            state.path.write_text(content, encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to save file {}: {}", state.path, exc)
            warning_box(self, "保存失败", f"无法保存文件:\n{state.path}\n\n{exc}")
            return False
        state.saved_text = content
        state.modified = False
        for panel in self._panels:
            if key in panel._tabs:
                panel._set_tab_modified(key, False)
                break
        self._sync_tabs_from_panels()
        return True

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
            # Prevent per-tab file_changed emissions while replaying tabs.
            with QSignalBlocker(self):
                for item in tabs:
                    if not isinstance(item, str) or not item:
                        continue
                    path = self._resolve_cross_platform_path(item)
                    self.load_file(path)
                if isinstance(active, str) and active:
                    active_path = self._resolve_cross_platform_path(active)
                    key = _tab_key(active_path)
                    for i in range(self._unified_tab_bar.count()):
                        if self._unified_tab_bar.tabData(i) == key:
                            self._unified_tab_bar.setCurrentIndex(i)
                            break
        finally:
            self._restoring_tabs = False
        self._sync_tabs_from_panels()
        # Emit once with the final active tab only.
        active_file = self.current_file
        if active_file:
            self.file_changed.emit(active_file)

    def _on_unified_tab_context_menu(self, pos) -> None:
        """Show context menu for unified tab bar."""
        index = self._unified_tab_bar.tabAt(pos)
        if index < 0:
            return

        file_path_str = self._unified_tab_bar.tabData(index)
        if not file_path_str:
            return

        file_path = Path(file_path_str)

        menu = create_isolated_context_menu(self)

        close_act = menu.addAction("Close")
        close_others_act = menu.addAction("Close Others")
        close_all_act = menu.addAction("Close All")

        action = menu.exec(self._unified_tab_bar.mapToGlobal(pos))

        if action == close_act:
            self._on_unified_tab_close(index)
        elif action == close_others_act:
            # Close all except this one
            for i in range(self._unified_tab_bar.count() - 1, -1, -1):
                if i != index:
                    if not self._on_unified_tab_close(i):
                        break
        elif action == close_all_act:
            # Close all tabs
            for i in range(self._unified_tab_bar.count() - 1, -1, -1):
                if not self._on_unified_tab_close(i):
                    break

    def _find_tab_state(self, key: str) -> TabState | None:
        for panel in self._panels:
            state = panel._tabs.get(key)
            if state is not None:
                return state
        return None

    def _refresh_unified_tab_affordances(self) -> None:
        duplicate_names = self._duplicate_tab_names()
        current_index = self._unified_tab_bar.currentIndex()

        def _wrap_affordance(
            inner: QWidget,
            hand_cursor: bool,
            *,
            path_text: str = "",
            missing: bool = False,
        ) -> QWidget:
            host = QWidget(self._unified_tab_bar)
            hl = QHBoxLayout(host)
            hl.setContentsMargins(0, 0, 2, 0)
            hl.setSpacing(2)
            hl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            path_width = 0
            path_height = 0
            if path_text:
                path_label = QLabel(path_text, host)
                path_label.setObjectName("tabDuplicatePath")
                path_label.setFont(self._unified_tab_bar.font())
                path_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                path_label.setMinimumWidth(0)
                path_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
                path_label.setWordWrap(False)
                path_label.setTextFormat(Qt.TextFormat.PlainText)
                path_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
                hl.addWidget(path_label, 0, Qt.AlignmentFlag.AlignVCenter)
                path_width = path_label.sizeHint().width()
                path_height = path_label.sizeHint().height()
            missing_height = 0
            if missing:
                missing_label = QLabel("D", host)
                missing_label.setObjectName("tabMissingBadge")
                missing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hl.addWidget(missing_label, 0, Qt.AlignmentFlag.AlignVCenter)
                missing_height = missing_label.sizeHint().height()
            hl.addWidget(inner, 0, Qt.AlignmentFlag.AlignVCenter)
            inner_w = max(12, inner.sizeHint().width())
            host_h = max(12, inner.sizeHint().height(), path_height, missing_height)
            host_w = inner_w + path_width + (12 if missing else 0) + 4
            host.setFixedSize(host_w, host_h)
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
            right = QWidget(self._unified_tab_bar)
            rl = QHBoxLayout(right)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(1)
            if state and state.modified:
                rl.addWidget(_TabAffordanceButton(self._unified_tab_bar))
            show_close = bool(
                i == current_index
                or i == self._tab_hovered_index
                or (state and state.modified)
            )
            if show_close:
                close_btn = _TabCloseButton(self._unified_tab_bar)
                close_btn.clicked.connect(lambda _=False, _k=key: self._on_unified_tab_close_by_key(_k))
                rl.addWidget(close_btn)
            self._unified_tab_bar.setTabButton(
                i,
                QTabBar.ButtonPosition.RightSide,
                _wrap_affordance(
                    right,
                    True,
                    path_text=path_text,
                    missing=missing,
                ),
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
        parts = parent.parts
        if len(parts) == 1:
            return parts[0]
        return f".../{parts[-1]}"

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._unified_tab_bar:
            if event.type() == QEvent.Type.MouseMove:
                idx = self._unified_tab_bar.tabAt(event.position().toPoint())
                if idx != self._tab_hovered_index:
                    self._tab_hovered_index = idx
                    self._refresh_unified_tab_affordances()
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                if self._tab_hovered_index != -1:
                    self._tab_hovered_index = -1
                    self._refresh_unified_tab_affordances()
        if obj in (self._tab_scroll, self._tab_scroll.viewport(), self._unified_tab_bar):
            if event.type() in (QEvent.Type.Wheel, QEvent.Type.NativeGesture):
                horizontal_delta = self._tab_scroll_delta(event)
                if horizontal_delta:
                    self._apply_tab_strip_scroll(horizontal_delta)
                    event.accept()
                    return True
            if event.type() in (
                QEvent.Type.Enter,
                QEvent.Type.HoverEnter,
                QEvent.Type.Leave,
                QEvent.Type.HoverLeave,
                QEvent.Type.MouseMove,
            ):
                QTimer.singleShot(0, self._update_tab_scrollbar_visibility)
        return super().eventFilter(obj, event)

    def _tab_scroll_delta(self, event) -> int:
        if event.type() == QEvent.Type.Wheel:
            angle_delta = event.angleDelta()
            pixel_delta = event.pixelDelta()
            return int(angle_delta.x() or pixel_delta.x() or angle_delta.y() or pixel_delta.y())

        if event.type() == QEvent.Type.NativeGesture:
            if event.gestureType() != Qt.NativeGestureType.PanNativeGesture:
                return 0
            delta = event.delta()
            if hasattr(delta, "x") and delta.x():
                return int(delta.x())
            if event.value():
                return int(event.value())
        return 0

    def _apply_tab_strip_scroll(self, horizontal_delta: int) -> None:
        scroll_bar = self._tab_scroll.horizontalScrollBar()
        if abs(horizontal_delta) >= 120:
            step = scroll_bar.singleStep() or 24
            units = max(1, abs(horizontal_delta) // 120)
            delta = (-1 if horizontal_delta > 0 else 1) * step * units
        else:
            delta = -horizontal_delta
        scroll_bar.setValue(scroll_bar.value() + delta)

    def _sync_unified_tab_bar_width(self) -> None:
        total_w = 0
        for i in range(self._unified_tab_bar.count()):
            total_w += self._unified_tab_bar.tabRect(i).width()
        min_w = max(total_w + 4, self._tab_scroll.viewport().width())
        self._unified_tab_bar.setMinimumWidth(min_w)
        self._unified_tab_bar.resize(min_w, self._unified_tab_bar.sizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_unified_tab_bar_width()

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
                warning_box(self, "Run Failed", f"Unable to run Python file:\n{exc}")

    def _on_preview_clicked(self) -> None:
        if not self._current_file:
            return
        if self._active_action_kind != "tex":
            return
        pdf_path = self._current_file.with_suffix(".pdf")
        if not pdf_path.exists():
            information_box(self, "Preview Not Found", f"Please compile first to generate PDF:\n{pdf_path.name}")
            return
        self.load_file(pdf_path)

    def _compile_tex(self, tex_path: Path) -> None:
        compiler = shutil.which("xelatex") or shutil.which("lualatex") or shutil.which("pdflatex")
        if not compiler:
            warning_box(self, "Compile Failed", "No LaTeX compiler found (xelatex/lualatex/pdflatex).")
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
            information_box(self, "Compile Complete", f"{tex_path.name} compiled successfully.")
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or exc.stdout or "").splitlines()[-6:]
            detail = "\n".join(tail) if tail else "No detailed output."
            warning_box(self, "Compile Failed", f"{tex_path.name}\n\n{detail}")
        except Exception as exc:
            warning_box(self, "Compile Failed", f"{tex_path.name}\n\n{exc}")

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

    @property
    def current_file(self) -> Path | None:
        if self._panels:
            return self._panels[-1].active_path()
        return None
