"""Preview widget with VS Code-style split editor and multi-format file viewing.

General mode: horizontal splitter with up to 2 EditorPanels (tab bars + stacked content).
Tex mode: vertical splitter with QScintilla (top) + QPdfView (bottom) + compile button.
"""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from loguru import logger
from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..icons import get_run_icon
from ..scale import scaled, scaled_size
from ..scintilla_utils import apply_scintilla_style, configure_lexer_colors
from ..theme import get_theme_colors
from .ui_utils import IconActionButton, NoWheelComboBox, combo_box_qss, filled_button_qss

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

    sci = QsciScintilla()
    apply_scintilla_style(sci, object_name="fileEditor", line_numbers=True, read_only=False)

    if lexer_name:
        mod = __import__("PyQt6.Qsci", fromlist=[lexer_name])
        lexer_cls = getattr(mod, lexer_name, None)
        if lexer_cls:
            lexer = lexer_cls(sci)
            sci.setLexer(lexer)
            configure_lexer_colors(lexer)

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
        layout.addWidget(self._stack, 1)

        # Placeholder
        self._placeholder = QLabel("选择文件查看")
        self._placeholder.setObjectName("editorPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._placeholder)

    def open_file(self, path: Path, preview: bool = True) -> None:
        """Open a file. If preview=True, opens as preview tab (replaces existing preview)."""
        key = str(path.resolve())

        # Already open? Just switch to it.
        if key in self._tabs:
            idx = self._tab_order.index(key)
            self._tab_bar.setCurrentIndex(idx)
            return

        # If current tab is preview, close it first
        if self._active_key and not self._tabs[self._active_key].pinned:
            self._close_tab(self._active_key)

        # Create viewer
        viewer, vtype = _create_viewer(path)
        self._stack.addWidget(viewer)

        state = TabState(path=path, pinned=not preview, viewer=viewer, viewer_type=vtype)
        self._tabs[key] = state
        self._tab_order.append(key)

        # Add tab
        tab_idx = self._tab_bar.addTab(path.name)
        self._tab_bar.setCurrentIndex(tab_idx)
        self._tab_bar.setTabToolTip(tab_idx, str(path))
        self._tab_bar.setVisible(True)

        if preview:
            # PyQt6 doesn't have tabFont(), use stylesheet for italic preview tabs
            self._tab_bar.setTabData(tab_idx, "preview")

        self._active_key = key
        self.tab_changed.emit()

    def pin_active_tab(self) -> None:
        """Pin the current preview tab."""
        if self._active_key and self._active_key in self._tabs:
            state = self._tabs[self._active_key]
            if not state.pinned:
                state.pinned = True
                idx = self._tab_order.index(self._active_key)
                self._tab_bar.setTabData(idx, "pinned")

    def has_tab(self, path: Path) -> bool:
        return str(path.resolve()) in self._tabs

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
        key = str(path.resolve())
        if key not in self._tabs:
            return
        state = self._tabs.pop(key)
        self._tab_order.remove(key)

        # Remove from our stack and tab bar
        self._tab_bar.removeTab(self._tab_order.index(key) if key in self._tab_order else 0)
        self._stack.removeWidget(state.viewer)

        # Add to other panel
        other._tabs[key] = state
        other._tab_order.append(key)
        other._stack.addWidget(state.viewer)
        tab_idx = other._tab_bar.addTab(path.name)
        other._tab_bar.setCurrentIndex(tab_idx)
        other._tab_bar.setTabToolTip(tab_idx, str(path))
        other._tab_bar.setVisible(True)
        if not state.pinned:
            other._tab_bar.setTabData(tab_idx, "preview")
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
        keep_key = str(keep_path.resolve())
        for key in list(self._tabs.keys()):
            if key != keep_key:
                self._close_tab(key)

    def _close_tab(self, key: str) -> None:
        if key not in self._tabs:
            return
        state = self._tabs.pop(key)
        self._tab_order.remove(key)

        # Remove tab bar entry
        for i in range(self._tab_bar.count()):
            if self._tab_bar.tabToolTip(i) == key or self._tab_bar.tabText(i) == state.path.name:
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
                self._tab_bar.setTabData(index, "pinned")

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
        menu.addSeparator()
        split_act = menu.addAction("向右拆分")

        action = menu.exec(self._tab_bar.mapToGlobal(pos))
        if action == close_act:
            self._close_tab(key)
        elif action == close_others_act:
            self.close_other_tabs(path)
        elif action == close_all_act:
            self.close_all_tabs()
        elif action == split_act:
            self.split_requested.emit(key)

    def apply_style(self) -> None:
        c = get_theme_colors()
        self._tab_bar.setStyleSheet(f"""
            QTabBar#editorTabBar {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
                height: 35px;
            }}
            QTabBar#editorTabBar::tab {{
                background-color: {c["tab_inactive_bg"]};
                color: {c["tab_inactive_fg"]};
                border: none;
                border-right: 1px solid {c["border"]};
                padding: 6px 16px;
                min-width: 80px;
                max-width: 200px;
            }}
            QTabBar#editorTabBar::tab:selected {{
                background-color: {c["tab_active_bg"]};
                color: {c["tab_active_fg"]};
                border-top: 2px solid {c["accent"]};
            }}
            QTabBar#editorTabBar::close-button {{
                image: none;
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
    """Preview widget with VS Code-style split editor."""

    selection_changed = pyqtSignal(str, str, int, int)
    file_changed = pyqtSignal(Path)  # Emitted when current file changes

    def __init__(self, workspace: Path):
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self._current_directory = "data"
        self._current_file: Path | None = None
        self._current_pdf: Path | None = None
        self._synctex_available: bool | None = None

        # General mode panels
        self._panels: list[EditorPanel] = []
        self._general_splitter: QSplitter | None = None

        # Tex mode components (lazy)
        self._tex_widget: QWidget | None = None
        self._tex_scintilla = None
        self._tex_pdf_view = None
        self._tex_pdf_document = None
        self._tex_process = None

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
        hl.setContentsMargins(12, 0, 12, 0)
        hl.setSpacing(0)

        # Title label - "预览"
        self._title_label = QLabel("预览")
        self._title_label.setObjectName("previewTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        hl.addWidget(self._title_label)

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
        self._unified_tab_bar.customContextMenuRequested.connect(self._on_unified_tab_context_menu)
        hl.addWidget(self._unified_tab_bar, 1)

        # TeX mode controls (hidden by default)
        self._compile_btn = QPushButton()
        self._compile_btn.setObjectName("compileBtn")
        self._compile_btn.setFixedSize(scaled(32), scaled(28))
        self._compile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._compile_btn.setIcon(get_run_icon())
        self._compile_btn.setToolTip("编译")
        self._compile_btn.clicked.connect(self._compile_tex)
        self._compile_btn.setVisible(False)
        hl.addWidget(self._compile_btn)

        layout.addWidget(header)

        # Mode stack
        self._mode_stack = QStackedWidget()
        layout.addWidget(self._mode_stack, 1)

        # Page 0: General mode (splitter with EditorPanels)
        self._setup_general_mode()
        # Page 1: Tex mode (lazy, created on first access)

        self._apply_style()

    def _setup_general_mode(self) -> None:
        self._general_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._general_splitter.setObjectName("editorSplitter")

        # Left panel (always present)
        left = EditorPanel()
        left.split_requested.connect(self._on_split_requested)
        left.panel_emptied.connect(self._on_panel_emptied)
        left.tab_changed.connect(self._sync_tabs_from_panels)
        self._panels.append(left)
        self._general_splitter.addWidget(left)

        self._mode_stack.addWidget(self._general_splitter)  # page 0

    # ------------------------------------------------------------------ #
    #  Tex mode (lazy init)
    # ------------------------------------------------------------------ #

    def _ensure_tex_mode(self) -> None:
        if self._tex_widget is not None:
            return

        from PyQt6.Qsci import QsciLexerTeX, QsciScintilla
        from PyQt6.QtPdfWidgets import QPdfView
        from PyQt6.QtGui import QColor, QFont

        c = get_theme_colors()
        self._tex_widget = QWidget(self)
        tex_layout = QVBoxLayout(self._tex_widget)
        tex_layout.setContentsMargins(0, 0, 0, 0)
        tex_layout.setSpacing(0)

        # TeX section (single editor pane by default)
        tex_section = QWidget(self)
        tsl = QVBoxLayout(tex_section)
        tsl.setContentsMargins(0, 0, 0, 0)
        tsl.setSpacing(0)

        self._tex_scintilla = QsciScintilla()
        apply_scintilla_style(self._tex_scintilla, object_name="texEditor", line_numbers=True, read_only=False)

        # Configure lexer with theme colors
        lexer = QsciLexerTeX(self._tex_scintilla)
        self._tex_scintilla.setLexer(lexer)
        self._tex_scintilla.marginClicked.connect(self._on_tex_margin_clicked)
        configure_lexer_colors(lexer)

        # Update margin width when content changes
        from ..scintilla_utils import update_margin_width
        self._tex_scintilla.textChanged.connect(lambda: update_margin_width(self._tex_scintilla))

        tsl.addWidget(self._tex_scintilla, 1)

        # PDF viewer kept for compile preview refresh, but not shown side-by-side by default.
        self._tex_pdf_document = QPdfDocument(None)
        self._tex_pdf_view = QPdfView(None)
        self._tex_pdf_view.setObjectName("texPdfView")
        self._tex_pdf_view.setDocument(self._tex_pdf_document)
        self._tex_pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self._tex_pdf_view.setStyleSheet(f"""
            QPdfView#texPdfView {{
                background-color: {c["editor_bg"]};
                border: none;
            }}
        """)

        tex_layout.addWidget(tex_section, 1)

        self._mode_stack.addWidget(self._tex_widget)  # page 1

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
                padding-right: 1px;
            }}
            #previewTitle {{
                font-size: 13px;
                font-weight: {c["fw_semibold"]};
                color: {c["fg"]};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
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
                border-radius: 4px;
                padding: 4px;
            }}
            #previewSettingsBtn:hover {{
                background-color: {c["hover"]};
            }}
            {combo_box_qss(
                "#engineCombo",
                border_color=c["input_border"],
                background_color=c["input_bg"],
                foreground_color=c["fg"],
                hover_border_color=c["accent"],
                selection_bg=c["hover"],
                selection_fg=c["fg"],
                font_size=12,
                padding="4px 24px 4px 8px",
            )}
            {filled_button_qss(
                "#compileBtn",
                bg=c["send_bg"],
                fg="#ffffff",
                hover_bg=c["send_hover"],
                disabled_bg=c["muted"],
                disabled_fg=c["editor_bg"],
            )}
            QSplitter#editorSplitter::handle {{
                background-color: {c["border"]};
                width: 2px;
            }}
            QTabBar#previewTabBar {{
                background-color: transparent;
                border: none;
            }}
            QTabBar#previewTabBar::tab {{
                background-color: {c["tab_inactive_bg"]};
                color: {c["tab_inactive_fg"]};
                border: none;
                border-right: 1px solid {c["border"]};
                padding: 6px 12px;
                margin-right: 2px;
                border-radius: 4px;
            }}
            QTabBar#previewTabBar::tab:selected {{
                background-color: {c["tab_active_bg"]};
                color: {c["tab_active_fg"]};
                border-top: 2px solid {c["accent"]};
            }}
            QTabBar#previewTabBar::tab:hover {{
                background-color: {c["hover"]};
            }}
        """)

        for panel in self._panels:
            panel.apply_style()

    # ------------------------------------------------------------------ #
    #  Directory / file switching
    # ------------------------------------------------------------------ #

    def set_directory(self, directory: str) -> None:
        self._current_directory = directory
        self._current_file = None
        self._current_pdf = None

        # Always show "预览" as title
        self._title_label.setText("预览")

        # Clear unified tab bar (QTabBar has no clear() method, remove tabs one by one)
        while self._unified_tab_bar.count() > 0:
            self._unified_tab_bar.removeTab(0)

        if directory == "tex":
            self._ensure_tex_mode()
            self._mode_stack.setCurrentIndex(1)
            self._compile_btn.setVisible(True)
        else:
            self._mode_stack.setCurrentIndex(0)
            self._compile_btn.setVisible(False)

        logger.debug("Preview directory: {}", directory)

    def load_file(self, file_path: Path) -> None:
        file_path = Path(file_path).resolve()
        self._current_file = file_path

        if self._current_directory == "tex":
            self._load_tex_file(file_path)
            # Add tab for tex file
            self._add_unified_tab(file_path)
        else:
            # Open in panel
            self._panels[-1].open_file(file_path, preview=True)
            # Sync tabs from panel to unified tab bar
            self._sync_tabs_from_panels()

        # Emit file changed signal
        self.file_changed.emit(file_path)

    def _add_unified_tab(self, file_path: Path) -> None:
        """Add a tab to the unified tab bar."""
        # Check if already exists
        for i in range(self._unified_tab_bar.count()):
            if self._unified_tab_bar.tabToolTip(i) == str(file_path):
                self._unified_tab_bar.setCurrentIndex(i)
                return

        # Add new tab
        tab_idx = self._unified_tab_bar.addTab(file_path.name)
        self._unified_tab_bar.setTabToolTip(tab_idx, str(file_path))
        self._unified_tab_bar.setCurrentIndex(tab_idx)

    def _sync_tabs_from_panels(self) -> None:
        """Sync unified tab bar with tabs from all panels."""
        # Clear current tabs
        self._unified_tab_bar.clear()

        # Collect all open files from panels
        for panel in self._panels:
            for key, state in panel._tabs.items():
                tab_idx = self._unified_tab_bar.addTab(state.path.name)
                self._unified_tab_bar.setTabToolTip(tab_idx, str(state.path))
                if key == panel._active_key:
                    self._unified_tab_bar.setCurrentIndex(tab_idx)

    def _on_unified_tab_changed(self, index: int) -> None:
        """Handle unified tab bar change."""
        if index < 0:
            self._current_file = None
            self.file_changed.emit(Path())  # Emit with empty path
            return

        file_path_str = self._unified_tab_bar.tabToolTip(index)
        if not file_path_str:
            self._current_file = None
            self.file_changed.emit(Path())  # Emit with empty path
            return

        file_path = Path(file_path_str)
        self._current_file = file_path

        if self._current_directory == "tex":
            # Switch tex file
            self._load_tex_file(file_path)
        else:
            # Find the panel that has this file and switch to it
            for panel in self._panels:
                key = str(file_path.resolve())
                if key in panel._tabs:
                    idx = panel._tab_order.index(key)
                    panel._tab_bar.setCurrentIndex(idx)
                    break

        # Emit file changed signal
        self.file_changed.emit(file_path)

    def _on_unified_tab_close(self, index: int) -> None:
        """Handle unified tab close."""
        file_path_str = self._unified_tab_bar.tabToolTip(index)
        if not file_path_str:
            return

        file_path = Path(file_path_str)

        if self._current_directory == "tex":
            # Clear tex file
            self._unified_tab_bar.removeTab(index)
            self._current_file = None
        else:
            # Close tab in panel
            for panel in self._panels:
                key = str(file_path.resolve())
                if key in panel._tabs:
                    panel._close_tab(key)
                    break
            # Sync tabs
            self._sync_tabs_from_panels()

        # Emit file changed signal with None or current active file
        active_file = self.current_file
        self.file_changed.emit(active_file if active_file else Path())

    def _on_unified_tab_context_menu(self, pos) -> None:
        """Show context menu for unified tab bar."""
        index = self._unified_tab_bar.tabAt(pos)
        if index < 0:
            return

        file_path_str = self._unified_tab_bar.tabToolTip(index)
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

    def _load_tex_file(self, path: Path) -> None:
        self._ensure_tex_mode()
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            self._current_pdf = path
            self._tex_pdf_document.close()
            status = self._tex_pdf_document.load(path)
            if status != QPdfDocument.Status.Ready:
                logger.warning("PDF load status: {} for {}", status, path)
        elif suffix == ".tex":
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                self._tex_scintilla.setText(content)
                self._find_matching_pdf(path)
            except Exception as e:
                self._tex_scintilla.setText(f"无法读取文件: {e}")
                logger.error("Failed to load tex: {}", e)
        else:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                self._tex_scintilla.setText(content)
            except Exception as e:
                self._tex_scintilla.setText(f"无法读取文件: {e}")

    def _find_matching_pdf(self, tex_path: Path) -> None:
        pdf_path = tex_path.with_suffix(".pdf")
        if pdf_path.exists():
            self._current_pdf = pdf_path
            self._tex_pdf_document.close()
            self._tex_pdf_document.load(pdf_path)
            return

        tex_dir = tex_path.parent
        pdfs = list(tex_dir.glob("*.pdf"))
        if len(pdfs) == 1:
            self._current_pdf = pdfs[0]
            self._tex_pdf_document.close()
            self._tex_pdf_document.load(pdfs[0])

    # ------------------------------------------------------------------ #
    #  Tex compile
    # ------------------------------------------------------------------ #

    def _compile_tex(self) -> None:
        if not self._current_file or self._current_file.suffix.lower() != ".tex":
            QMessageBox.information(self, "编译", "请先打开一个 .tex 文件")
            return

        if (
            self._tex_process is not None
            and self._tex_process.state() != self._tex_process.state().NotRunning
        ):
            return  # Already compiling

        engine = "xelatex"  # Default to xelatex
        tex_path = self._current_file
        work_dir = str(tex_path.parent)

        from PyQt6.QtCore import QProcess

        self._tex_process = QProcess(self)
        self._tex_process.setWorkingDirectory(work_dir)
        self._tex_process.finished.connect(self._on_compile_finished)
        self._compile_btn.setEnabled(False)

        args = [
            "-synctex=1",
            "-interaction=nonstopmode",
            tex_path.name,
        ]
        self._tex_process.start(engine, args)
        logger.info("Compiling: {} {}", engine, " ".join(args))

    def _on_compile_finished(self, exit_code, exit_status) -> None:
        self._compile_btn.setEnabled(True)

        if exit_code == 0:
            logger.info("TeX compilation succeeded")
            self.refresh_pdf()
        else:
            stderr = ""
            if self._tex_process:
                stderr = bytes(self._tex_process.readAllStandardError()).decode(
                    "utf-8", errors="replace"
                )
            logger.warning("TeX compilation failed (exit {}): {}", exit_code, stderr[:500])
            QMessageBox.warning(
                self,
                "编译失败",
                f"编译退出码: {exit_code}\n\n{stderr[:1000]}",
            )

    # ------------------------------------------------------------------ #
    #  Split logic
    # ------------------------------------------------------------------ #

    def _on_split_requested(self, file_key: str) -> None:
        """Handle split-right request from an EditorPanel."""
        if len(self._panels) >= 2:
            # Already split — move tab to right panel
            path = Path(file_key)
            left = self._panels[0]
            right = self._panels[1]
            left.move_tab_to(path, right)
            self._sync_tabs_from_panels()
            return

        # Create right panel
        path = Path(file_key)
        left = self._panels[0]
        right = EditorPanel()
        right.split_requested.connect(self._on_split_requested)
        right.panel_emptied.connect(self._on_right_panel_emptied)
        right.tab_changed.connect(self._sync_tabs_from_panels)
        right.apply_style()
        self._panels.append(right)
        self._general_splitter.addWidget(right)
        self._general_splitter.setSizes([self.width() // 2, self.width() // 2])

        left.move_tab_to(path, right)

    def _on_panel_emptied(self) -> None:
        """Left panel emptied — nothing to do (keep it for new files)."""
        pass

    def _on_right_panel_emptied(self) -> None:
        """Right panel emptied — remove it."""
        if len(self._panels) < 2:
            return
        right = self._panels.pop()
        self._general_splitter.removeWidget(right)
        right.deleteLater()

    # ------------------------------------------------------------------ #
    #  SyncTeX
    # ------------------------------------------------------------------ #

    def _check_synctex(self) -> bool:
        if self._synctex_available is None:
            self._synctex_available = shutil.which("synctex") is not None
            if not self._synctex_available:
                logger.info("synctex not found — SyncTeX disabled")
        return self._synctex_available

    def _on_tex_margin_clicked(self, margin, line, state) -> None:
        if not self._current_file or not self._current_pdf:
            return
        mods = self._tex_scintilla.modifiers
        if mods & Qt.KeyboardModifier.ControlModifier:
            self._synctex_forward_search(line + 1)

    def _synctex_forward_search(self, line: int) -> None:
        if not self._check_synctex() or not self._current_file or not self._current_pdf:
            return
        try:
            result = subprocess.run(
                [
                    "synctex",
                    "view",
                    "-i",
                    f"{line}:0:{self._current_file}",
                    "-o",
                    str(self._current_pdf),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(self._current_file.parent),
            )
            if result.returncode != 0:
                return
            page = self._parse_synctex_view_output(result.stdout)
            if page is not None and self._tex_pdf_view:
                self._tex_pdf_view.pageNavigator().jump(page - 1, QPointF(0, 0), 0)
                logger.debug("SyncTeX forward: line {} → page {}", line, page)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("SyncTeX forward failed: {}", e)

    def _parse_synctex_view_output(self, output: str) -> int | None:
        for line in output.strip().splitlines():
            if line.startswith("Page:"):
                try:
                    return int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
        return None

    def synctex_inverse_search(self, page: int, x: float, y: float) -> None:
        if not self._check_synctex() or not self._current_pdf:
            return
        try:
            result = subprocess.run(
                [
                    "synctex",
                    "edit",
                    "-p",
                    str(page),
                    "-x",
                    f"0:{x}:{y}",
                    "-o",
                    str(self._current_pdf),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(self._current_pdf.parent),
            )
            if result.returncode != 0:
                return
            line, _ = self._parse_synctex_edit_output(result.stdout)
            if line is not None and self._tex_scintilla:
                self._tex_scintilla.ensureLineVisible(line - 1)
                self._tex_scintilla.setCursorPosition(line - 1, 0)
                self._tex_scintilla.setSelection(line - 1, 0, line, 0)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("SyncTeX inverse failed: {}", e)

    def _parse_synctex_edit_output(self, output: str) -> tuple[int | None, str | None]:
        line_num = None
        file_path = None
        for ln in output.strip().splitlines():
            if ln.startswith("Line:"):
                try:
                    line_num = int(ln.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
            elif ln.startswith("Input:"):
                file_path = ln.split(":", 1)[1].strip()
        return line_num, file_path

    # ------------------------------------------------------------------ #
    #  Selection tracking (for general mode editors)
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self) -> None:
        if not self._current_file:
            return

        panel = self._panels[-1] if self._current_directory != "tex" else None
        if not panel:
            return

        viewer = panel.get_active_viewer()
        if not viewer:
            return

        from PyQt6.Qsci import QsciScintilla

        if isinstance(viewer, QsciScintilla):
            selected_text = viewer.selectedText()
            if not selected_text:
                return
            line_from, _, line_to, _ = viewer.getSelection()
            start_line = line_from + 1
            end_line = line_to + 1
            rel_path = str(self._current_file.relative_to(self.workspace))
            self.selection_changed.emit(rel_path, selected_text, start_line, end_line)

    # ------------------------------------------------------------------ #
    #  Public API (preserved)
    # ------------------------------------------------------------------ #

    def get_selected_context(self) -> tuple[str, str, int, int] | None:
        if not self._current_file:
            return None

        # General mode
        if self._current_directory != "tex" and self._panels:
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
        if self._current_directory == "tex" and self._tex_scintilla:
            self._tex_scintilla.setSelection(-1, -1, -1, -1)
        elif self._panels:
            viewer = self._panels[-1].get_active_viewer()
            from PyQt6.Qsci import QsciScintilla

            if isinstance(viewer, QsciScintilla):
                viewer.setSelection(-1, -1, -1, -1)

    def refresh_pdf(self) -> None:
        if self._current_directory == "tex" and self._current_pdf and self._current_pdf.exists():
            self._tex_pdf_document.close()
            self._tex_pdf_document.load(self._current_pdf)

    @property
    def current_directory(self) -> str:
        return self._current_directory

    @property
    def current_file(self) -> Path | None:
        if self._current_directory != "tex" and self._panels:
            return self._panels[-1].active_path()
        return self._current_file
