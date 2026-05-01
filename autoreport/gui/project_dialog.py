"""Project selection dialog inspired by VSCode's welcome screen."""

from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config import ConfigManager

PROJECT_DIRECTORIES = ["data", "data/processed", "references", "theory", "code", "tex"]


def _draw_folder_icon(color: str, size: int = 48) -> QPixmap:
    """Draw a small folder icon for the project list."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.5)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(c.lighter(160))
    # Tab
    tab = QPainterPath()
    tab.moveTo(4, 11)
    tab.lineTo(4, 7)
    tab.quadTo(4, 4, 7, 4)
    tab.lineTo(18, 4)
    tab.lineTo(21, 7)
    tab.lineTo(21, 11)
    p.drawPath(tab)
    # Body
    body = QPainterPath()
    body.moveTo(3, 11)
    body.lineTo(3, size - 4)
    body.quadTo(3, size - 3, 4, size - 3)
    body.lineTo(size - 4, size - 3)
    body.quadTo(size - 3, size - 3, size - 3, size - 4)
    body.lineTo(size - 3, 11)
    body.closeSubpath()
    p.drawPath(body)
    p.end()
    return pixmap


class _ProjectItem(QFrame):
    """Clickable project card in the recent list."""

    clicked = pyqtSignal(Path)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self._path = path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("projectItem")
        self.setFixedHeight(52)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(_draw_folder_icon("#e8a84c", 32))
        layout.addWidget(icon_label)

        info = QVBoxLayout()
        info.setSpacing(2)

        name = QLabel(self._path.name)
        name.setObjectName("projectName")
        info.addWidget(name)

        path_label = QLabel(str(self._path))
        path_label.setObjectName("projectPath")
        info.addWidget(path_label)

        layout.addLayout(info, 1)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit(self._path)
        super().mousePressEvent(event)


class ProjectDialog(QDialog):
    """Project selection dialog — VSCode-inspired layout."""

    project_selected = pyqtSignal(Path)

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._selected_project: Path | None = None

        self._setup_ui()
        self._apply_style()
        self._load_recent_projects()

    def _setup_ui(self) -> None:
        self.setWindowTitle("AutoReport")
        self.setMinimumSize(680, 520)
        self.resize(720, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Header ----
        header = QWidget()
        header.setObjectName("header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(40, 36, 40, 20)
        header_layout.setSpacing(6)

        title = QLabel("AutoReport")
        title.setObjectName("title")
        header_layout.addWidget(title)

        subtitle = QLabel(
            "多 Agent 协作的物理实验报告自动撰写系统。\n"
            "选择一个已有项目，或新建项目开始。"
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)

        root.addWidget(header)

        # ---- Action buttons ----
        actions = QWidget()
        actions.setObjectName("actions")
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(40, 0, 40, 16)
        actions_layout.setSpacing(12)

        open_btn = QPushButton("打开文件夹…")
        open_btn.setObjectName("primaryBtn")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._on_open_folder)
        actions_layout.addWidget(open_btn)

        new_btn = QPushButton("新建项目…")
        new_btn.setObjectName("secondaryBtn")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self._on_new_project)
        actions_layout.addWidget(new_btn)

        actions_layout.addStretch()

        root.addWidget(actions)

        # ---- Separator ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        root.addWidget(sep)

        # ---- Recent projects ----
        recent_header = QWidget()
        recent_header_layout = QHBoxLayout(recent_header)
        recent_header_layout.setContentsMargins(40, 16, 40, 8)
        recent_label = QLabel("最近的项目")
        recent_label.setObjectName("sectionLabel")
        recent_header_layout.addWidget(recent_label)
        recent_header_layout.addStretch()
        root.addWidget(recent_header)

        scroll = QScrollArea()
        scroll.setObjectName("recentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(32, 0, 32, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_container)
        root.addWidget(scroll, 1)

        # ---- Footer ----
        footer = QWidget()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(40, 12, 40, 16)
        cancel_btn = QPushButton("退出")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        footer_layout.addStretch()
        footer_layout.addWidget(cancel_btn)
        root.addWidget(footer)

    def _apply_style(self) -> None:
        dark = self._get_dark_mode()

        c = {
            "bg": "#1e1e1e" if dark else "#f3f3f3",
            "headerBg": "#252526" if dark else "#f3f3f3",
            "titleFg": "#e0e0e0" if dark else "#1a1a1a",
            "subtitleFg": "#999" if dark else "#666",
            "sectionFg": "#ccc" if dark else "#555",
            "primaryBg": "#0e639c" if dark else "#0078d4",
            "primaryFg": "#ffffff",
            "primaryHover": "#1177bb" if dark else "#106ebe",
            "secondaryBorder": "#555" if dark else "#ccc",
            "secondaryFg": "#ddd" if dark else "#333333",
            "secondaryHoverBg": "#333" if dark else "#e9e9e9",
            "itemBg": "#2d2d2d" if dark else "#eaeaea",
            "itemHoverBg": "#3d3d3d" if dark else "#e0e0e0",
            "itemName": "#e0e0e0" if dark else "#1a1a1a",
            "itemPath": "#888" if dark else "#888888",
            "sepColor": "#333" if dark else "#ddd",
            "cancelFg": "#999" if dark else "#888888",
            "cancelHoverFg": "#ccc" if dark else "#333333",
        }

        self.setStyleSheet(f"""
            ProjectDialog {{
                background-color: {c["bg"]};
            }}
            #header {{
                background-color: {c["headerBg"]};
            }}
            #title {{
                font-size: 28px;
                font-weight: 700;
                color: {c["titleFg"]};
            }}
            #subtitle {{
                font-size: 13px;
                color: {c["subtitleFg"]};
                line-height: 1.5;
            }}
            #primaryBtn {{
                background-color: {c["primaryBg"]};
                color: {c["primaryFg"]};
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            #primaryBtn:hover {{ background-color: {c["primaryHover"]}; }}
            #secondaryBtn {{
                background-color: transparent;
                color: {c["secondaryFg"]};
                border: 1px solid {c["secondaryBorder"]};
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
            }}
            #secondaryBtn:hover {{
                background-color: {c["secondaryHoverBg"]};
            }}
            #separator {{
                color: {c["sepColor"]};
                max-height: 1px;
            }}
            #sectionLabel {{
                font-size: 12px;
                font-weight: 600;
                color: {c["sectionFg"]};
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            #recentScroll {{
                background-color: {c["bg"]};
                border: none;
            }}
            #projectItem {{
                background-color: {c["itemBg"]};
                border: 1px solid transparent;
                border-radius: 6px;
            }}
            #projectItem:hover {{
                background-color: {c["itemHoverBg"]};
                border-color: {c["sepColor"]};
            }}
            #projectName {{
                font-size: 13px;
                font-weight: 600;
                color: {c["itemName"]};
            }}
            #projectPath {{
                font-size: 11px;
                color: {c["itemPath"]};
            }}
            #footer {{
                background-color: {c["headerBg"]};
            }}
            #cancelBtn {{
                background-color: transparent;
                color: {c["cancelFg"]};
                border: none;
                padding: 6px 16px;
                font-size: 12px;
            }}
            #cancelBtn:hover {{
                color: {c["cancelHoverFg"]};
            }}
            QScrollArea {{
                border: none;
            }}
        """)

    def _get_dark_mode(self) -> bool:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        return hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

    # ---- Data loading ----

    def _load_recent_projects(self) -> None:
        current_dir = Path.cwd()
        for item in current_dir.iterdir():
            if item.is_dir() and self._is_valid_project(item):
                self._add_project(item)

    def _is_valid_project(self, path: Path) -> bool:
        for dir_name in ["data", "references", "theory", "code", "tex"]:
            if (path / dir_name).exists():
                return True
        return False

    def _add_project(self, path: Path) -> None:
        # Avoid duplicates
        for i in range(self._list_layout.count()):
            w = self._list_layout.itemAt(i).widget()
            if isinstance(w, _ProjectItem) and w._path == path:
                return

        item = _ProjectItem(path)
        item.clicked.connect(self._select_project)
        # Insert before the stretch at the end
        self._list_layout.insertWidget(self._list_layout.count() - 1, item)

    # ---- Actions ----

    def _select_project(self, path: Path) -> None:
        self._selected_project = path
        logger.info("Selected project: {}", path)
        self.project_selected.emit(path)
        self.accept()

    def _on_new_project(self) -> None:
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)

        if dialog.exec():
            path = Path(dialog.selectedFiles()[0])
            if any(path.iterdir()):
                reply = QMessageBox.question(
                    self, "目录不为空",
                    f"'{path.name}' 不为空。是否在此目录中创建项目结构？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            try:
                self._create_project_structure(path)
            except OSError as e:
                logger.error("Failed to create project: {}", e)
                QMessageBox.critical(self, "创建失败", f"无法创建项目结构：\n{e}")
                return

            self._add_project(path)
            self._select_project(path)

    def _on_open_folder(self) -> None:
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)

        if dialog.exec():
            path = Path(dialog.selectedFiles()[0])

            if not self._is_valid_project(path):
                reply = QMessageBox.question(
                    self, "不是有效的项目",
                    f"'{path.name}' 不是 AutoReport 项目。是否创建项目结构？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    try:
                        self._create_project_structure(path)
                    except OSError as e:
                        logger.error("Failed to create project: {}", e)
                        QMessageBox.critical(self, "创建失败", f"无法创建项目结构：\n{e}")
                        return
                    self._add_project(path)
                else:
                    return

            self._select_project(path)

    def _create_project_structure(self, path: Path) -> None:
        for dir_name in PROJECT_DIRECTORIES:
            (path / dir_name).mkdir(parents=True, exist_ok=True)
        logger.debug("Created project structure in: {}", path)

    def get_selected_project(self) -> Path | None:
        return self._selected_project
