"""File search popup widget for @ file references with agent quick-select."""

from dataclasses import dataclass
from pathlib import Path
from typing import override

from PyQt6.QtCore import QEvent, QRect, QRectF, QSize, Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QKeyEvent, QIcon, QPainterPath, QRegion
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QApplication
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from autoreport.utils.agent_labels import get_agent_title, get_agent_badge_with_icon
from autoreport.gui.icons import get_agent_icon as get_agent_qicon
from ..theme import get_theme_colors


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
    unhandled_key_pressed = pyqtSignal(object)

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
        self._workspace: Path | None = None

        self._setup_ui()
        self._setup_window_flags()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._frame = QFrame(self)
        self._frame.setObjectName("fileSearchPopupFrame")
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(4)
        layout.addWidget(self._frame)

        self._status_label = QLabel()
        self._status_label.setVisible(False)
        frame_layout.addWidget(self._status_label)

        self._list_widget = QListWidget()
        self._list_widget.setItemDelegate(HTMLDelegate())
        self._list_widget.setSpacing(2)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_widget.currentRowChanged.connect(self._on_current_row_changed)
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list_widget.installEventFilter(self)
        self._list_widget.viewport().installEventFilter(self)
        frame_layout.addWidget(self._list_widget)

        self.setFixedWidth(400)

        c = get_theme_colors()

        self._frame.setStyleSheet(f"""
            QFrame#fileSearchPopupFrame {{
                background-color: {c["bg"]};
                border: 1px solid {c["border"]};
                border-radius: {c["radius_md"]};
            }}
            QListWidget {{
                background-color: {c["bg"]};
                border: none;
                outline: none;
                padding: 2px;
            }}
            QListWidget::item {{
                padding: 0 8px;
                border-radius: {c["radius_sm"]};
                color: {c["popup_fg"]};
            }}
            QListWidget::item:hover {{
                background-color: {c["popup_hover"]};
            }}
            QListWidget::item:selected {{
                background-color: {c["tree_sel_bg"]};
                color: {c["tree_sel_fg"]};
            }}
        """)

    def _setup_window_flags(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

    def set_workspace(self, workspace: Path | str | None) -> None:
        self._workspace = Path(workspace).resolve() if workspace else None

    def _radius_px(self) -> float:
        try:
            return float(str(get_theme_colors().get("radius_md", "6px")).removesuffix("px"))
        except ValueError:
            return 6.0

    def _update_rounded_mask(self) -> None:
        rect = QRectF(QRect(self.rect()).adjusted(0, 0, -1, -1))
        if rect.isEmpty():
            return
        path = QPainterPath()
        radius = self._radius_px()
        path.addRoundedRect(rect, radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_rounded_mask()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._update_rounded_mask()

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
                "no matching files" if not self._matches else None
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
            self._populate_list(file_status=None if matches else "no matching files")
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
            item.setSizeHint(QSize(0, 38))
            self._list_widget.addItem(item)

        has_files = file_status is None and self._matches
        if self._agents and file_status:
            text = file_status
            sep = QListWidgetItem(f"  {text}")
            sep.setData(Qt.ItemDataRole.UserRole, ("separator", None))
            sep.setFlags(Qt.ItemFlag.NoItemFlags)
            sep.setSizeHint(QSize(0, 32))
            self._list_widget.addItem(sep)

        if has_files:
            for match in self._matches[:self.MAX_VISIBLE_ROWS]:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, ("file", match))
                item.setText(self._format_match_text(match))
                item.setToolTip(str(match.path))
                item.setSizeHint(QSize(0, 34))
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
        path = Path(match.path)
        if self._workspace and path.is_absolute():
            try:
                return path.relative_to(self._workspace).as_posix()
            except ValueError:
                pass
        return path.as_posix()

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

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self.select_current()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self.select_current()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj in {self._list_widget, self._list_widget.viewport()} and event.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True
        return super().eventFilter(obj, event)

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        match event.key():
            case Qt.Key.Key_Up:
                self.move_up()
                return
            case Qt.Key.Key_Down:
                self.move_down()
                return
            case Qt.Key.Key_Enter | Qt.Key.Key_Return:
                self.select_current()
                return
            case Qt.Key.Key_Escape:
                self.cancel()
                return
            case _:
                self.unhandled_key_pressed.emit(event)
                event.accept()

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
            text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
            if text:
                opt = QStyleOptionViewItem(option)
                self.initStyleOption(opt, index)
                opt.text = ""
                style = opt.widget.style() if opt.widget else QApplication.style()
                style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

                text_rect = option.rect.adjusted(8, 0, -8, 0)
                elided = option.fontMetrics.elidedText(
                    text,
                    Qt.TextElideMode.ElideMiddle,
                    text_rect.width(),
                )
                painter.save()
                painter.setPen(opt.palette.color(opt.palette.ColorRole.Text))
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    elided,
                )
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
                return QSize(400, 34)
        return super().sizeHint(option, index)
