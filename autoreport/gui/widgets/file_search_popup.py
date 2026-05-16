"""File search popup widget for @ file references with agent quick-select."""

from dataclasses import dataclass
from pathlib import Path
from typing import override

from PyQt6.QtCore import QSize, Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QKeyEvent, QTextDocument, QIcon
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from autoreport.utils.agent_labels import get_agent_title, get_agent_badge_with_icon
from autoreport.gui.icons import get_agent_icon as get_agent_qicon


@dataclass
class FileMatch:
    """File search result match."""

    path: Path
    score: int
    indices: list[int] | None = None


class FileSearchPopup(QWidget):
    """Popup widget for displaying agent quick-select and file search results."""

    file_selected = pyqtSignal(Path)
    agent_selected = pyqtSignal(str)
    cancelled = pyqtSignal()

    MAX_VISIBLE_ROWS = 10

    # Lazy initialization to avoid QPixmap before QApplication
    _AGENT_INFO_CACHE: dict[str, tuple[str, QIcon]] | None = None

    @classmethod
    def _get_agent_info(cls) -> dict[str, tuple[str, QIcon]]:
        """Get agent info dict (lazy loaded to avoid QPixmap before QApplication)."""
        if cls._AGENT_INFO_CACHE is None:
            cls._AGENT_INFO_CACHE = {
                key: (get_agent_title(key), get_agent_qicon(key, size=24))
                for key in ("main", "data_analysis", "plotting", "theory", "report")
            }
        return cls._AGENT_INFO_CACHE

    # For backward compatibility
    @property
    def AGENT_INFO(self) -> dict[str, tuple[str, QIcon]]:
        return self._get_agent_info()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._query = ""
        self._matches: list[FileMatch] = []
        self._selected_idx = 0
        self._agents: list[tuple[str, str, QIcon]] = []
        self._current_agent: str = ""

        self._setup_ui()
        self._setup_window_flags()

    def _setup_ui(self) -> None:
        from PyQt6.QtWidgets import QApplication

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._status_label = QLabel()
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        self._list_widget = QListWidget()
        self._list_widget.setItemDelegate(HTMLDelegate())
        self._list_widget.setSpacing(1)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_widget.currentRowChanged.connect(self._on_current_row_changed)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list_widget)

        self.setFixedWidth(400)

        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        bg = "#1f1f1f" if dark else "#ffffff"
        border = "#2b2b2b" if dark else "#e0e0e0"
        fg = "#cccccc" if dark else "#333333"
        muted = "#737373" if dark else "#999999"
        sel_bg = "#094771" if dark else "#cce4f7"
        hover = "#2a2d2e" if dark else "#e8e8e8"

        self.setStyleSheet(f"""
            FileSearchPopup {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QListWidget {{
                background-color: {bg};
                border: none;
                outline: none;
                padding: 2px;
            }}
            QListWidget::item {{
                padding: 5px 8px;
                border-radius: 3px;
                color: {fg};
            }}
            QListWidget::item:hover {{
                background-color: {hover};
            }}
            QListWidget::item:selected {{
                background-color: {sel_bg};
                color: #ffffff;
            }}
        """)

    def _setup_window_flags(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Setup fade animation
        self._fade_effect = QGraphicsOpacityEffect(self)
        self._fade_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._fade_effect)

        self._fade_animation = QPropertyAnimation(self._fade_effect, b"opacity")
        self._fade_animation.setDuration(150)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade_animation.finished.connect(self._on_fade_out_finished)

    def _on_fade_out_finished(self) -> None:
        """Called when fade-out animation completes."""
        self.hide()
        self._fade_effect.setOpacity(1.0)

    def hide(self) -> None:
        """Hide with fade-out animation."""
        if self.isVisible() and not self._fade_animation.state() == QPropertyAnimation.State.Running:
            self._fade_animation.start()
        else:
            super().hide()

    def hideEvent(self, event) -> None:
        """Handle hide event (e.g., when clicked outside) - use fade animation."""
        if self._fade_animation.state() != QPropertyAnimation.State.Running:
            self._fade_animation.start()
        event.accept()

    def set_current_agent(self, agent_type: str) -> None:
        self._current_agent = agent_type
        self._agents = [
            (t, n, e) for t, (n, e) in self.AGENT_INFO.items()
            if t != agent_type
        ]

    def set_query(self, query: str, waiting: bool = True) -> None:
        self._query = query
        self._selected_idx = 0

        if self._agents:
            self._status_label.setVisible(False)
            status = "searching files…" if waiting else (
                "no file matches" if not self._matches else None
            )
            self._populate_list(file_status=status)
        elif waiting:
            self._show_status("loading...")
        elif not self._matches:
            self._show_status("no matches")
        else:
            self._status_label.setVisible(False)
            self._populate_list()

    def set_matches(self, matches: list[FileMatch]) -> None:
        self._matches = matches
        self._selected_idx = 0

        if self._agents:
            self._status_label.setVisible(False)
            self._populate_list(file_status=None if matches else "no file matches")
        elif not matches:
            self._show_status("no matches")
        else:
            self._status_label.setVisible(False)
            self._populate_list()

    def _show_status(self, text: str) -> None:
        self._list_widget.setVisible(False)
        self._status_label.setText(text)
        self._status_label.setVisible(True)

    def _populate_list(self, file_status: str | None = None) -> None:
        self._list_widget.clear()
        self._list_widget.setVisible(True)
        self._status_label.setVisible(False)

        for agent_type, name, icon in self._agents:
            item = QListWidgetItem(f"  {name}")
            item.setIcon(icon)
            item.setData(Qt.ItemDataRole.UserRole, ("agent", agent_type))
            self._list_widget.addItem(item)

        has_files = file_status is None and self._matches
        if self._agents and (has_files or file_status):
            text = file_status if file_status else "── files ──"
            sep = QListWidgetItem(f"  {text}")
            sep.setData(Qt.ItemDataRole.UserRole, ("separator", None))
            sep.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list_widget.addItem(sep)

        if file_status is None:
            for match in self._matches[:self.MAX_VISIBLE_ROWS]:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, ("file", match))
                item.setText(self._format_match_text(match))
                self._list_widget.addItem(item)

        for i in range(self._list_widget.count()):
            if self._is_selectable(i):
                self._list_widget.setCurrentRow(i)
                break

    def _is_selectable(self, row: int) -> bool:
        item = self._list_widget.item(row)
        if item is None:
            return False
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and data[0] == "separator":
            return False
        return bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)

    def _format_match_text(self, match: FileMatch) -> str:
        path_str = str(match.path)
        rel_path = path_str

        if match.indices:
            highlighted = []
            for i, char in enumerate(path_str):
                if i in match.indices:
                    highlighted.append(f"<b>{char}</b>")
                else:
                    highlighted.append(char)
            rel_path = "".join(highlighted)

        if len(path_str) > 50:
            parts = Path(path_str).parts
            if len(parts) > 3:
                rel_path = ".../" + "/".join(parts[-3:])

        return rel_path

    def move_up(self) -> None:
        if not self._list_widget.isVisible():
            return
        current = self._list_widget.currentRow()
        row = current - 1
        while row >= 0 and not self._is_selectable(row):
            row -= 1
        if row >= 0:
            self._list_widget.setCurrentRow(row)

    def move_down(self) -> None:
        if not self._list_widget.isVisible():
            return
        current = self._list_widget.currentRow()
        row = current + 1
        while row < self._list_widget.count() and not self._is_selectable(row):
            row += 1
        if row < self._list_widget.count():
            self._list_widget.setCurrentRow(row)

    def select_current(self) -> None:
        if not self._list_widget.isVisible():
            return

        current_item = self._list_widget.currentItem()
        if not current_item:
            return

        data = current_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple):
            kind, value = data
            if kind == "agent":
                self.agent_selected.emit(value)
                return
            elif kind == "file":
                self.file_selected.emit(value.path)
                return

        if isinstance(data, FileMatch):
            self.file_selected.emit(data.path)

    def cancel(self) -> None:
        self.cancelled.emit()

    def _on_current_row_changed(self, row: int) -> None:
        self._selected_idx = row

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self.select_current()

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        match event.key():
            case Qt.Key.Key_Up:
                self.move_up()
            case Qt.Key.Key_Down:
                self.move_down()
            case Qt.Key.Key_Enter | Qt.Key.Key_Return:
                self.select_current()
                return
            case Qt.Key.Key_Escape:
                self.cancel()
                return
            case _:
                super().keyPressEvent(event)

    def calculate_height(self) -> int:
        if self._status_label.isVisible():
            return 40

        total = 0
        for i in range(self._list_widget.count()):
            hint = self._list_widget.sizeHintForRow(i)
            total += hint if hint > 0 else 26
        return total + 20


class HTMLDelegate(QStyledItemDelegate):
    """Delegate for rendering HTML in file match items."""

    @override
    def paint(self, painter, option, index):
        item = index.model().data(index, Qt.ItemDataRole.UserRole)

        match_obj = None
        if isinstance(item, FileMatch):
            match_obj = item
        elif isinstance(item, tuple):
            if item[0] == "file":
                match_obj = item[1]
            else:
                super().paint(painter, option, index)
                return

        if match_obj:
            option.text = ""
            super().paint(painter, option, index)

            text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
            if text:
                document = QTextDocument()
                document.setHtml(text)
                document.setTextWidth(option.rect.width())

                painter.save()
                painter.translate(option.rect.topLeft())
                document.drawContents(painter)
                painter.restore()
        else:
            super().paint(painter, option, index)

    @override
    def sizeHint(self, option, index):
        item = index.model().data(index, Qt.ItemDataRole.UserRole)

        match_obj = None
        if isinstance(item, FileMatch):
            match_obj = item
        elif isinstance(item, tuple) and item[0] == "file":
            match_obj = item[1]

        if match_obj:
            text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
            if text:
                document = QTextDocument()
                document.setHtml(text)
                document.setTextWidth(400)
                return QSize(400, int(document.size().height()) + 4)
        return super().sizeHint(option, index)
