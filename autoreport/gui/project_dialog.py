"""Project selection dialog — VSCode welcome page style."""

from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
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
from ..core.recent_projects import RecentProjects

PROJECT_DIRECTORIES = ["data", "data/processed", "references", "theory", "code", "tex"]


class _RecentItem(QWidget):
    """Single recent project row — VSCode button-link style."""

    clicked = pyqtSignal(Path)
    delete_requested = pyqtSignal(Path)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self._path = path
        self.setObjectName("recentItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Blue link-like name
        name = QPushButton(self._path.name)
        name.setObjectName("recentName")
        name.setCursor(Qt.CursorShape.PointingHandCursor)
        name.clicked.connect(lambda: self.clicked.emit(self._path))
        layout.addWidget(name)

        # Gray parent path
        full = str(self._path)
        parent_path = str(self._path.parent) if self._path.parent != self._path.anchor else ""
        if parent_path and parent_path != "/":
            path_label = QLabel(parent_path)
            path_label.setObjectName("recentPath")
            path_label.setWordWrap(False)
            layout.addWidget(path_label)

        layout.addStretch()

        # Delete button (visible on hover)
        del_btn = QPushButton("✕")
        del_btn.setObjectName("recentDeleteBtn")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFixedSize(20, 20)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._path))
        layout.addWidget(del_btn)


class ProjectDialog(QDialog):
    """Project selection dialog — VSCode welcome page style."""

    project_selected = pyqtSignal(Path)

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._selected_project: Path | None = None
        self._recent = RecentProjects()

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
        header = QWidget(self)
        header.setObjectName("header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(40, 36, 40, 28)
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
        actions = QWidget(self)
        actions.setObjectName("actionBar")
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(40, 12, 40, 16)
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

        config_btn = QPushButton("API 配置")
        config_btn.setObjectName("configBtn")
        config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        config_btn.clicked.connect(self._on_config)
        actions_layout.addWidget(config_btn)

        actions_layout.addStretch()

        root.addWidget(actions)

        # ---- Recent projects ----
        recent_header = QWidget(self)
        recent_header.setObjectName("sectionHeader")
        recent_header_layout = QHBoxLayout(recent_header)
        recent_header_layout.setContentsMargins(40, 24, 40, 10)
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

        self._list_container = QWidget(self)
        self._list_container.setObjectName("listContainer")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(40, 0, 40, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_container)
        root.addWidget(scroll, 1)

        # ---- Footer ----
        footer = QWidget(self)
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

        link_color = "#3794ff" if dark else "#005fb8"
        link_hover = "#5cb3ff" if dark else "#007acc"

        c = {
            "bg": "#1f1f1f" if dark else "#f3f3f3",
            "headerBg": "#181818" if dark else "#f3f3f3",
            "titleFg": "#e0e0e0" if dark else "#1a1a1a",
            "subtitleFg": "#999" if dark else "#666",
            "border": "#2b2b2b" if dark else "#e0e0e0",
            "sectionFg": "#ccc" if dark else "#555",
            "primaryBg": "#0078d4" if dark else "#0078d4",
            "primaryFg": "#ffffff",
            "primaryHover": "#026ec1" if dark else "#106ebe",
            "secondaryBorder": "#555" if dark else "#ccc",
            "secondaryFg": "#ddd" if dark else "#333333",
            "secondaryHoverBg": "#2a2d2e" if dark else "#e9e9e9",
            "link": link_color,
            "linkHover": link_hover,
            "pathFg": "#858585" if dark else "#888888",
            "deleteFg": "#858585" if dark else "#999",
            "deleteHoverFg": "#f44747" if dark else "#d32f2f",
            "deleteHoverBg": "#3a1a1a" if dark else "#fef2f2",
            "cancelFg": "#858585" if dark else "#888888",
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
            #actionBar {{
                background-color: {c["bg"]};
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
            #configBtn {{
                background-color: transparent;
                color: {c["secondaryFg"]};
                border: 1px solid {c["secondaryBorder"]};
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
            }}
            #configBtn:hover {{
                background-color: {c["secondaryHoverBg"]};
            }}
            #sectionHeader {{
                background-color: {c["bg"]};
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
            #recentScroll > QWidget {{
                background-color: {c["bg"]};
            }}
            #listContainer {{
                background-color: {c["bg"]};
            }}

            /* Recent item row — VSCode button-link style, no card */
            #recentItem {{
                background-color: transparent;
                padding: 4px 0;
            }}
            #recentName {{
                background-color: transparent;
                border: none;
                color: {c["link"]};
                font-size: 13px;
                text-align: left;
                padding: 2px 0;
            }}
            #recentName:hover {{
                color: {c["linkHover"]};
                text-decoration: underline;
            }}
            #recentPath {{
                font-size: 13px;
                color: {c["pathFg"]};
                padding-left: 8px;
            }}
            #recentDeleteBtn {{
                background-color: transparent;
                color: transparent;
                border: none;
                border-radius: 3px;
                font-size: 11px;
                padding: 0;
            }}
            #recentItem:hover #recentDeleteBtn {{
                color: {c["deleteFg"]};
            }}
            #recentDeleteBtn:hover {{
                background-color: {c["deleteHoverBg"]};
                color: {c["deleteHoverFg"]};
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
        for path in self._recent.get_all():
            self._add_project(path)

    def _is_valid_project(self, path: Path) -> bool:
        for dir_name in ["data", "references", "theory", "code", "tex"]:
            if (path / dir_name).exists():
                return True
        return False

    def _add_project(self, path: Path) -> None:
        for i in range(self._list_layout.count()):
            w = self._list_layout.itemAt(i).widget()
            if isinstance(w, _RecentItem) and w._path == path:
                return

        item = _RecentItem(path)
        item.clicked.connect(self._select_project)
        item.delete_requested.connect(self._on_delete_project)
        self._list_layout.insertWidget(self._list_layout.count() - 1, item)

    def _on_delete_project(self, path: Path) -> None:
        self._recent.remove(path)
        for i in range(self._list_layout.count()):
            w = self._list_layout.itemAt(i).widget()
            if isinstance(w, _RecentItem) and w._path == path:
                self._list_layout.removeWidget(w)
                w.deleteLater()
                break

    # ---- Actions ----

    def _select_project(self, path: Path) -> None:
        self._selected_project = path
        self._recent.add(path)
        logger.info("Selected project: {}", path)
        self.project_selected.emit(path)
        self.accept()

    def _on_config(self) -> None:
        from .config_dialog import ConfigDialog

        dialog = ConfigDialog(self.config_manager, parent=self)
        dialog.exec()

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

            self._recent.add(path)
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
                    self._recent.add(path)
                    self._add_project(path)
                else:
                    return
            else:
                self._recent.add(path)

            self._select_project(path)

    def _create_project_structure(self, path: Path) -> None:
        for dir_name in PROJECT_DIRECTORIES:
            (path / dir_name).mkdir(parents=True, exist_ok=True)
        logger.debug("Created project structure in: {}", path)

    def get_selected_project(self) -> Path | None:
        return self._selected_project
