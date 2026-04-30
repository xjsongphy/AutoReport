"""Project selection dialog for choosing or creating projects."""

from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QMessageBox,
    QLineEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal
from loguru import logger

from ...interfaces.types import AgentType
from ...config import ConfigManager


# Fixed directory structure for projects
PROJECT_DIRECTORIES = ["data", "data/processed", "references", "theory", "code", "tex"]


class ProjectDialog(QDialog):
    """Project selection dialog."""

    project_selected = pyqtSignal(Path)  # Signal when project is selected

    def __init__(self, config_manager: ConfigManager, parent=None):
        """Initialize project dialog.

        Args:
            config_manager: Configuration manager.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config_manager = config_manager
        self._recent_projects: list[Path] = []
        self._selected_project: Path | None = None

        self._setup_ui()
        self._load_recent_projects()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        self.setWindowTitle("选择项目 - AutoReport")
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("选择一个项目或创建新项目")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Description
        description = QLabel(
            "项目是一个包含实验数据和报告的文件夹。"
            "每个项目都有固定的目录结构用于存储数据、参考资料、理论推导等。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Recent projects section
        recent_label = QLabel("最近的项目:")
        recent_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(recent_label)

        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self._on_recent_selected)
        layout.addWidget(self.recent_list)

        # Quick actions
        actions_layout = QHBoxLayout()
        layout.addLayout(actions_layout)

        new_button = QPushButton("新建项目")
        new_button.clicked.connect(self._on_new_project)
        actions_layout.addWidget(new_button)

        open_button = QPushButton("打开文件夹")
        open_button.clicked.connect(self._on_open_folder)
        actions_layout.addWidget(open_button)

        actions_layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)

        button_layout.addStretch()

        open_selected_button = QPushButton("打开选中项目")
        open_selected_button.clicked.connect(self._on_open_selected)
        button_layout.addWidget(open_selected_button)

        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

    def _load_recent_projects(self) -> None:
        """Load recent projects from settings."""
        # TODO: Load from persistent storage
        # For now, check for projects in current directory
        current_dir = Path.cwd()

        for item in current_dir.iterdir():
            if item.is_dir() and self._is_valid_project(item):
                self._add_project_to_list(item)

    def _is_valid_project(self, path: Path) -> bool:
        """Check if a directory is a valid AutoReport project.

        Args:
            path: Directory path to check.

        Returns:
            True if directory contains AutoReport project structure.
        """
        # Check for at least one of the expected directories
        for dir_name in ["data", "references", "theory", "code", "tex"]:
            if (path / dir_name).exists():
                return True
        return False

    def _add_project_to_list(self, path: Path) -> None:
        """Add a project to the recent list.

        Args:
            path: Project path.
        """
        # Check if already in list
        for i in range(self.recent_list.count()):
            item = self.recent_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == str(path):
                return

        # Add to list
        item = QListWidgetItem(path.name)
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setToolTip(str(path))
        self.recent_list.addItem(item)

    def _on_recent_selected(self, item: QListWidgetItem) -> None:
        """Handle double-click on recent project.

        Args:
            item: Clicked item.
        """
        project_path = Path(item.data(Qt.ItemDataRole.UserRole))
        self._select_project(project_path)

    def _on_new_project(self) -> None:
        """Handle new project button click."""
        # Let user choose location
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnlyOnly)

        if dialog.exec():
            path = Path(dialog.selectedFiles()[0])

            # Check if directory already has content
            if any(path.iterdir()):
                reply = QMessageBox.question(
                    self,
                    "目录不为空",
                    f"所选目录 '{path.name}' 不为空。是否要在此目录中创建项目结构？"
                    "\n\n注意：这不会删除现有文件，但会创建 AutoReport 所需的目录。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )

                if reply != QMessageBox.StandardButton.Yes:
                    return

            # Create project structure
            self._create_project_structure(path)

            # Add to recent list
            self._add_project_to_list(path)

            logger.info("Created new project at: {}", path)

            QMessageBox.information(
                self,
                "项目已创建",
                f"项目结构已在 '{path.name}' 中创建。"
            )

    def _on_open_folder(self) -> None:
        """Handle open folder button click."""
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnlyOnly)

        if dialog.exec():
            path = Path(dialog.selectedFiles()[0])

            # Check if valid project
            if not self._is_valid_project(path):
                reply = QMessageBox.question(
                    self,
                    "不是有效的项目",
                    f"所选目录 '{path.name}' 不是有效的 AutoReport 项目。"
                    f"\n\n是否要在此目录中创建项目结构？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    self._create_project_structure(path)
                    self._add_project_to_list(path)
                else:
                    return
            else:
                # Add to recent if not already there
                self._add_project_to_list(path)

            self._select_project(path)

    def _on_open_selected(self) -> None:
        """Handle open selected button click."""
        current_item = self.recent_list.currentItem()
        if current_item:
            project_path = Path(current_item.data(Qt.ItemDataRole.UserRole))
            self._select_project(project_path)
        else:
            QMessageBox.warning(
                self,
                "未选择项目",
                "请从列表中选择一个项目，或创建/打开新项目。"
            )

    def _create_project_structure(self, path: Path) -> None:
        """Create AutoReport project directory structure.

        Args:
            path: Project root path.
        """
        for dir_name in PROJECT_DIRECTORIES:
            dir_path = path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

        logger.debug("Created project structure in: {}", path)

    def _select_project(self, path: Path) -> None:
        """Select a project and close dialog.

        Args:
            path: Project path.
        """
        self._selected_project = path
        logger.info("Selected project: {}", path)

        # Emit signal and accept
        self.project_selected.emit(path)
        self.accept()

    def get_selected_project(self) -> Path | None:
        """Get the selected project path.

        Returns:
            Selected project path or None.
        """
        return self._selected_project
