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
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..scale import scaled, scaled_size

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


def _dark_mode() -> bool:
    from PyQt6.QtWidgets import QApplication

    hints = QApplication.styleHints()
    return hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark


def _theme_colors() -> dict[str, str]:
    dark = _dark_mode()
    return {
        "bg": "#1f1f1f" if dark else "#ffffff",
        "surface": "#181818" if dark else "#f3f3f3",
        "card": "#252526" if dark else "#e8e8e8",
        "border": "#2b2b2b" if dark else "#e0e0e0",
        "fg": "#d4d4d4" if dark else "#333333",
        "muted": "#858585" if dark else "#888888",
        "accent": "#0078d4" if dark else "#0090ff",
        "sel_bg": "#264f78" if dark else "#add6ff",
        "tab_active_bg": "#1f1f1f" if dark else "#ffffff",
        "tab_inactive_bg": "#2d2d2d" if dark else "#ececec",
        "tab_active_fg": "#ffffff" if dark else "#1a1a1a",
        "tab_inactive_fg": "#969696" if dark else "#888888",
        "compile_bg": "#0e639c" if dark else "#0078d4",
        "compile_fg": "#ffffff" if dark else "#ffffff",
    }


# ================================================================== #
#  Viewer factory
# ================================================================== #


def _create_scintilla(path: Path, lexer_name: str) -> tuple:
    """Create a QScintilla editor for the given file."""
    from PyQt6.Qsci import QsciScintilla

    c = _theme_colors()
    sci = QsciScintilla()
    sci.setObjectName("fileEditor")
    sci.setUtf8(True)
    sci.setMarginLineNumbers(1, True)
    sci.setMarginWidth(1, "0000")
    sci.setReadOnly(False)

    if lexer_name:
        mod = __import__("PyQt6.Qsci", fromlist=[lexer_name])
        lexer_cls = getattr(mod, lexer_name, None)
        if lexer_cls:
            sci.setLexer(lexer_cls(sci))

    sci.setStyleSheet(f"""
        QsciScintilla#fileEditor {{
            background-color: {c["bg"]};
            color: {c["fg"]};
            border: none;
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            font-size: 13px;
        }}
    """)

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        sci.setText(content)
    except Exception as e:
        sci.setText(f"无法读取文件: {e}")

    return sci, "scintilla"


def _create_pdf_viewer(path: Path) -> tuple:
    """Create an embedded QPdfView for the given PDF file."""
    from PyQt6.QtPdfWidgets import QPdfView

    c = _theme_colors()
    doc = QPdfDocument(None)
    doc.load(path)

    view = QPdfView(None)
    view.setObjectName("filePdfView")
    view.setDocument(doc)
    view.setPageMode(QPdfView.PageMode.MultiPage)
    view.setStyleSheet(f"""
        QPdfView#filePdfView {{
            background-color: {c["bg"]};
            border: none;
        }}
    """)

    return view, "pdf"


def _create_image_viewer(path: Path) -> tuple:
    """Create an image viewer with QPixmap."""
    c = _theme_colors()
    label = QLabel()
    label.setObjectName("fileImageViewer")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(f"""
        QLabel#fileImageViewer {{
            background-color: {c["bg"]};
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

    c = _theme_colors()
    svg = QSvgWidget(str(path))
    svg.setObjectName("fileSvgViewer")
    svg.setStyleSheet(f"""
        QSvgWidget#fileSvgViewer {{
            background-color: {c["bg"]};
            border: none;
        }}
    """)
    return svg, "image"


def _create_spreadsheet_viewer(path: Path) -> tuple:
    """Create a table viewer for xlsx/xls files using pandas."""
    c = _theme_colors()

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
    table.setStyleSheet(f"""
        QTableView#fileTableView {{
            background-color: {c["bg"]};
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
            font-weight: 600;
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
            font = self._tab_bar.tabFont(tab_idx)
            font.setItalic(True)
            self._tab_bar.setTabFont(tab_idx, font)

        self._active_key = key

    def pin_active_tab(self) -> None:
        """Pin the current preview tab."""
        if self._active_key and self._active_key in self._tabs:
            state = self._tabs[self._active_key]
            if not state.pinned:
                state.pinned = True
                idx = self._tab_order.index(self._active_key)
                font = self._tab_bar.tabFont(idx)
                font.setItalic(False)
                self._tab_bar.setTabFont(idx, font)

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
            font = other._tab_bar.tabFont(tab_idx)
            font.setItalic(True)
            other._tab_bar.setTabFont(tab_idx, font)
        other._active_key = key

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

    def _on_tab_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._tab_order):
            self._stack.setCurrentIndex(0)
            return
        key = self._tab_order[index]
        self._active_key = key
        state = self._tabs[key]
        self._stack.setCurrentWidget(state.viewer)

    def _on_close_requested(self, index: int) -> None:
        if 0 <= index < len(self._tab_order):
            self._close_tab(self._tab_order[index])

    def _on_double_click(self, index: int) -> None:
        if 0 <= index < len(self._tab_order):
            key = self._tab_order[index]
            state = self._tabs[key]
            if not state.pinned:
                state.pinned = True
                font = self._tab_bar.tabFont(index)
                font.setItalic(False)
                self._tab_bar.setTabFont(index, font)

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
        c = _theme_colors()
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
                background-color: {c["bg"]};
            }}
        """)


# ================================================================== #
#  PreviewWidget — top-level, same external API
# ================================================================== #


class PreviewWidget(QWidget):
    """Preview widget with VS Code-style split editor."""

    selection_changed = pyqtSignal(str, str, int, int)

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

        # Header
        header = QWidget()
        header.setObjectName("previewHeader")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(12, 6, 12, 4)

        self._title_label = QLabel("预览")
        self._title_label.setObjectName("previewTitle")
        hl.addWidget(self._title_label)

        self._file_label = QLabel()
        self._file_label.setObjectName("previewFile")
        self._file_label.setVisible(False)
        hl.addWidget(self._file_label)

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

        c = _theme_colors()
        self._tex_widget = QWidget()
        tex_layout = QVBoxLayout(self._tex_widget)
        tex_layout.setContentsMargins(0, 0, 0, 0)
        tex_layout.setSpacing(0)

        # Tex header with compile controls
        tex_header = QWidget()
        tex_header.setObjectName("texHeader")
        thl = QHBoxLayout(tex_header)
        thl.setContentsMargins(12, 4, 12, 4)

        thl.addWidget(QLabel("TeX 编辑器"))

        thl.addStretch()

        self._engine_combo = QComboBox()
        self._engine_combo.setObjectName("engineCombo")
        self._engine_combo.addItems(["xelatex", "lualatex"])
        self._engine_combo.setFixedWidth(scaled(100))
        thl.addWidget(self._engine_combo)

        w, h = scaled_size(80, 26)
        self._compile_btn = QPushButton("编译")
        self._compile_btn.setObjectName("compileBtn")
        self._compile_btn.setFixedSize(w, h)
        self._compile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._compile_btn.clicked.connect(self._compile_tex)
        thl.addWidget(self._compile_btn)

        tex_layout.addWidget(tex_header)

        # Horizontal splitter: TeX editor (left) + PDF viewer (right)
        tex_split = QSplitter(Qt.Orientation.Horizontal)
        tex_split.setObjectName("texSplitter")

        # TeX section
        tex_section = QWidget()
        tsl = QVBoxLayout(tex_section)
        tsl.setContentsMargins(0, 0, 0, 0)
        tsl.setSpacing(0)

        self._tex_scintilla = QsciScintilla()
        self._tex_scintilla.setObjectName("texEditor")
        self._tex_scintilla.setUtf8(True)
        self._tex_scintilla.setMarginLineNumbers(1, True)
        self._tex_scintilla.setMarginWidth(1, "0000")
        self._tex_scintilla.setReadOnly(False)

        # Configure lexer with theme colors
        lexer = QsciLexerTeX(self._tex_scintilla)
        self._tex_scintilla.setLexer(lexer)
        self._tex_scintilla.marginClicked.connect(self._on_tex_margin_clicked)

        # Set basic colors for lexer
        lexer.setColor(QColor(c["fg"]))
        lexer.setPaper(QColor(c["bg"]))

        self._tex_scintilla.setStyleSheet(f"""
            QsciScintilla#texEditor {{
                background-color: {c["bg"]};
                color: {c["fg"]};
                border: none;
                font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
                font-size: 13px;
            }}
            QsciScintilla#texEditor::margin {{
                background-color: {c["surface"]};
                color: {c["muted"]};
            }}
        """)
        tsl.addWidget(self._tex_scintilla)

        # PDF section
        pdf_section = QWidget()
        psl = QVBoxLayout(pdf_section)
        psl.setContentsMargins(0, 0, 0, 0)
        psl.setSpacing(0)

        self._tex_pdf_document = QPdfDocument(None)
        self._tex_pdf_view = QPdfView(None)
        self._tex_pdf_view.setObjectName("texPdfView")
        self._tex_pdf_view.setDocument(self._tex_pdf_document)
        self._tex_pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self._tex_pdf_view.setStyleSheet(f"""
            QPdfView#texPdfView {{
                background-color: {c["bg"]};
                border: none;
            }}
        """)
        psl.addWidget(self._tex_pdf_view, 1)

        tex_split.addWidget(tex_section)
        tex_split.addWidget(pdf_section)
        tex_split.setSizes([scaled(450), scaled(400)])

        tex_layout.addWidget(tex_split, 1)

        # Tex header styling
        tex_header.setStyleSheet(f"""
            QWidget#texHeader {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
            }}
            QLabel {{
                color: {c["fg"]};
                font-size: 13px;
                font-weight: 500;
            }}
            QComboBox#engineCombo {{
                background-color: {c["bg"]};
                color: {c["fg"]};
                border: 1px solid {c["border"]};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 12px;
            }}
            QComboBox#engineCombo:hover {{
                border: 1px solid {c["accent"]};
            }}
            QComboBox#engineCombo::drop-down {{
                border: none;
                width: 20px;
            }}
            QPushButton#compileBtn {{
                background-color: {c["accent"]};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                font-weight: 500;
                font-size: 12px;
                padding: 4px 12px;
            }}
            QPushButton#compileBtn:hover {{
                background-color: {"#1085d8" if _dark_mode() else "#0078d4"};
            }}
            QPushButton#compileBtn:disabled {{
                background-color: {c["muted"]};
                color: {c["bg"]};
            }}
        """)

        self._mode_stack.addWidget(self._tex_widget)  # page 1

    # ------------------------------------------------------------------ #
    #  Style
    # ------------------------------------------------------------------ #

    def _apply_style(self) -> None:
        c = _theme_colors()
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {c["bg"]};
            }}
            #previewHeader {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
            }}
            #previewTitle {{
                font-size: 13px;
                font-weight: 600;
                color: {c["fg"]};
            }}
            #previewFile {{
                font-size: 11px;
                color: {c["muted"]};
                font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            }}
            QSplitter#editorSplitter::handle {{
                background-color: {c["border"]};
                width: 2px;
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
        self._file_label.setVisible(False)

        if directory == "tex":
            self._ensure_tex_mode()
            self._mode_stack.setCurrentIndex(1)
            self._title_label.setText("LaTeX 编辑器")
        else:
            self._mode_stack.setCurrentIndex(0)
            self._title_label.setText("预览")
            if not self._panels[0].tab_count():
                pass  # Placeholder already visible

        logger.debug("Preview directory: {}", directory)

    def load_file(self, file_path: Path) -> None:
        file_path = Path(file_path).resolve()
        self._current_file = file_path

        rel = file_path.relative_to(self.workspace)
        self._file_label.setText(f"文件: {rel}")
        self._file_label.setVisible(True)

        if self._current_directory == "tex":
            self._load_tex_file(file_path)
        else:
            self._panels[-1].open_file(file_path, preview=True)

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

        engine = self._engine_combo.currentText()
        tex_path = self._current_file
        work_dir = str(tex_path.parent)

        from PyQt6.QtCore import QProcess

        self._tex_process = QProcess(self)
        self._tex_process.setWorkingDirectory(work_dir)
        self._tex_process.finished.connect(self._on_compile_finished)
        self._compile_btn.setEnabled(False)
        self._compile_btn.setText("编译中...")

        args = [
            "-synctex=1",
            "-interaction=nonstopmode",
            tex_path.name,
        ]
        self._tex_process.start(engine, args)
        logger.info("Compiling: {} {}", engine, " ".join(args))

    def _on_compile_finished(self, exit_code, exit_status) -> None:
        self._compile_btn.setEnabled(True)
        self._compile_btn.setText("编译")

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
            return

        # Create right panel
        path = Path(file_key)
        left = self._panels[0]
        right = EditorPanel()
        right.split_requested.connect(self._on_split_requested)
        right.panel_emptied.connect(self._on_right_panel_emptied)
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
