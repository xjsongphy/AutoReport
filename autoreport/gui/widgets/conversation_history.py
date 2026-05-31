"""Floating conversation history dropdown with hover delete button."""

from datetime import datetime

from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ..theme import get_theme_colors
from ...utils.editor_context import user_visible_content
from .ui_utils import create_isolated_context_menu, danger_filled_button_qss


def _bubble_visible_text(text: str) -> str:
    """Use the same editor-context stripping logic as user bubbles."""
    raw = str(text or "")
    body = user_visible_content(raw).strip()
    if raw.startswith("Editor context: ") and body == raw.strip():
        return ""
    return body


class SessionListItem(QWidget):
    """Custom widget for session list item with hover delete button."""

    clicked = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    context_menu_requested = pyqtSignal(str, str, QPoint)

    def __init__(self, session_id: str, name: str, timestamp: str, preview: str = "", is_current: bool = False, parent=None):
        super().__init__(parent)
        self._session_id = session_id
        self._is_current = is_current
        self._name_text = name
        self._preview_text = preview
        self.setObjectName("sessionListItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui(name, timestamp, preview)
        self._set_hovered(False)

    def _setup_ui(self, name: str, timestamp: str, preview: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Left: name + preview
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(1)

        self._name_label = QLabel(name)
        self._name_label.setObjectName("sessionName")
        self._name_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._name_label.setAutoFillBackground(False)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._name_label.setWordWrap(False)
        left_layout.addWidget(self._name_label)

        self._preview_label: QLabel | None = None
        if preview:
            self._preview_label = QLabel(preview)
            self._preview_label.setObjectName("sessionPreview")
            self._preview_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self._preview_label.setAutoFillBackground(False)
            self._preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self._preview_label.setWordWrap(False)
            left_layout.addWidget(self._preview_label)

        layout.addLayout(left_layout, 1)

        # Right: fixed action slot. Hover swaps content without changing row width.
        right_widget = QWidget(self)
        right_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        right_widget.setAutoFillBackground(False)

        # Time label (shown by default, hidden on hover)
        self._time_label = QLabel()
        self._time_label.setObjectName("sessionTime")
        self._time_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._time_label.setAutoFillBackground(False)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        try:
            dt = datetime.fromisoformat(timestamp)
            self._time_label.setText(dt.strftime("%m/%d %H:%M"))
        except Exception:
            self._time_label.setText("")

        # Delete button (hidden by default, shown on hover)
        self._delete_btn = QPushButton("删除")
        self._delete_btn.setObjectName("sessionDeleteBtn")
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setFixedSize(42, 22)
        self._delete_btn.clicked.connect(self._on_delete)

        right_width = max(
            74,
            self._time_label.sizeHint().width(),
            self._delete_btn.sizeHint().width(),
        )
        right_widget.setFixedWidth(right_width)

        delete_page = QWidget(right_widget)
        delete_page.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        delete_page.setAutoFillBackground(False)
        delete_layout = QHBoxLayout(delete_page)
        delete_layout.setContentsMargins(0, 0, 0, 0)
        delete_layout.addStretch(1)
        delete_layout.addWidget(self._delete_btn)

        self._right_stack = QStackedLayout(right_widget)
        self._right_stack.setContentsMargins(0, 0, 0, 0)
        self._right_stack.setSpacing(0)
        self._right_stack.addWidget(self._time_label)
        self._right_stack.addWidget(delete_page)
        self._right_stack.setCurrentWidget(self._time_label)

        layout.addWidget(right_widget)

        # Install event filter for hover
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._update_elided_labels()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_elided_labels()

    def _update_elided_labels(self) -> None:
        width = max(20, self._name_label.width())
        self._name_label.setText(self._name_label.fontMetrics().elidedText(
            self._name_text,
            Qt.TextElideMode.ElideRight,
            width,
        ))
        if self._preview_label is not None:
            preview_width = max(20, self._preview_label.width())
            self._preview_label.setText(self._preview_label.fontMetrics().elidedText(
                self._preview_text,
                Qt.TextElideMode.ElideRight,
                preview_width,
            ))

    def _set_hovered(self, hovered: bool) -> None:
        # Only update if hover state actually changed
        if hasattr(self, '_last_hovered') and self._last_hovered == hovered:
            return
        self._last_hovered = hovered

        c = get_theme_colors()
        if self._is_current:
            bg = c["selection"]
        elif hovered:
            bg = c["hover"]
        else:
            bg = "transparent"
        self.setStyleSheet(f"""
            QWidget#sessionListItem {{
                background-color: {bg};
                border-radius: {c["radius_sm"]};
            }}
            QWidget#sessionListItem QLabel {{
                background: transparent;
                border: none;
            }}
        """)

    def _on_delete(self) -> None:
        self.delete_requested.emit(self._session_id)

    def _on_context_menu(self, pos: QPoint) -> None:
        self.context_menu_requested.emit(
            self._session_id,
            self._name_text,
            self.mapToGlobal(pos),
        )

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit(self._session_id)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self._set_hovered(True)
        self._right_stack.setCurrentIndex(1)
        self._update_elided_labels()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_hovered(False)
        self._right_stack.setCurrentIndex(0)
        self._update_elided_labels()
        super().leaveEvent(event)


class ConversationHistoryDropdown(QFrame):
    """Floating conversation history popup built without QListWidget."""

    DEFAULT_WIDTH = 420
    MIN_WIDTH = 280
    PANEL_MARGIN = 8
    PANEL_WIDTH_RATIO = 0.82
    VERTICAL_GAP = 6

    session_selected = pyqtSignal(str)
    delete_session_requested = pyqtSignal(str)
    rename_session_requested = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None, *, max_visible_items: int = 6):
        """Initialize the conversation history dropdown."""
        super().__init__(parent)
        self.setObjectName("historyDropdown")
        self._max_visible_items = max(1, int(max_visible_items))
        self._rows: list[SessionListItem] = []
        self._current_session_id: str | None = None
        self._anchor_widget: QWidget | None = None
        self._event_filter_installed = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._panel = QFrame(self)
        self._panel.setObjectName("historyDropdownPanel")
        self._panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(6, 6, 6, 6)
        panel_layout.setSpacing(0)
        root.addWidget(self._panel)

        self._scroll = QScrollArea(self._panel)
        self._scroll.setObjectName("historyScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.viewport().setObjectName("historyScrollViewport")
        panel_layout.addWidget(self._scroll)

        self._content = QWidget(self._scroll)
        self._content.setObjectName("historyContent")
        self._list_layout = QVBoxLayout(self._content)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._scroll.setWidget(self._content)

        self.setFixedWidth(self.DEFAULT_WIDTH)

    def _apply_theme(self) -> None:
        """Apply all popup styling without using item delegates."""
        c = get_theme_colors()

        self.setStyleSheet(f"""
            QFrame#historyDropdownPanel {{
                background-color: {c["bg"]};
                border: 1px solid {c["input_border"]};
                border-radius: {c["radius_md"]};
            }}
            QScrollArea#historyScrollArea {{
                background: transparent;
                border: none;
            }}
            QWidget#historyScrollViewport {{
                background: transparent;
                border: none;
            }}
            QWidget#historyContent {{
                background: transparent;
                border: none;
            }}
            QLabel#sessionName {{
                color: {c["fg"]};
                font-size: 13px;
                background: transparent;
            }}
            QLabel#sessionPreview {{
                color: {c["muted"]};
                font-size: 11px;
                background: transparent;
            }}
            QLabel#sessionTime {{
                color: {c["muted"]};
                font-size: 11px;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 4px 0 4px 2px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {c["scrollbar"]};
                min-height: 28px;
                border-radius: {c["radius_sm"]};
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {c["scrollbar_hover"]};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
                height: 0px;
            }}
            {danger_filled_button_qss(
                "#sessionDeleteBtn",
                radius=c["radius_sm"],
                padding="0 6px",
                font_size=11,
                font_weight=c["fw_medium"],
            )}
        """)

    def show_dropdown(self, parent_widget: QWidget) -> None:
        """Position and show the dropdown below parent widget.

        Align the dropdown's right edge to the trigger button's right edge so
        it expands leftward instead of overflowing to the right.
        """
        if not parent_widget:
            return

        if not self._rows:
            return

        self._anchor_widget = parent_widget
        geometry = self._current_anchor_geometry(parent_widget)
        self._fit_to_anchor_panel(geometry)
        self.ensurePolished()

        y = geometry["button_rect"].bottom() + 1 + self.VERTICAL_GAP
        max_height = self._available_height_below(geometry, y)
        self._apply_popup_height(max_height=max_height)

        x = geometry["button_rect"].right() + 1 - self.width()
        bounds = geometry.get("panel_bounds")
        if bounds is not None:
            panel_left, panel_right = bounds
            x = max(panel_left, min(x, panel_right - self.width()))

        self.move(x, y)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        self._install_app_event_filter()
        self._refresh_row_elision()

    def populate_from_store(self) -> None:
        """Populate from conversation store via signal callback."""
        # This will be called by parent with actual session data
        pass

    def populate(self, sessions: list[dict], current_session_id: str | None = None) -> None:
        self._clear_rows()
        self._current_session_id = current_session_id

        for session in sessions:
            session_id = session.get("id", "")
            raw_name = str(session.get("name", "未命名对话") or "")
            timestamp = session.get("timestamp", "")
            raw_preview = str(session.get("preview", "") or "")
            visible_name = _bubble_visible_text(raw_name)
            visible_preview = _bubble_visible_text(raw_preview)
            name = visible_name or visible_preview or "新对话"
            preview = visible_preview
            if preview == name:
                preview = ""

            row = SessionListItem(
                session_id, name, timestamp, preview,
                is_current=(session_id == current_session_id),
                parent=self._content,
            )
            row.clicked.connect(self._on_session_clicked)
            row.delete_requested.connect(self.delete_session_requested.emit)
            row.context_menu_requested.connect(self._show_context_menu)
            self._list_layout.addWidget(row)
            self._rows.append(row)

        self._apply_popup_height()

    def count(self) -> int:
        return len(self._rows)

    def _clear_rows(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()

    def _apply_popup_height(self, max_height: int | None = None) -> None:
        if not self._rows:
            self.setFixedHeight(0)
            return

        row_height = max(row.sizeHint().height() for row in self._rows)
        visible_rows = min(len(self._rows), self._max_visible_items)
        margins = self._panel.layout().contentsMargins()
        height = row_height * visible_rows + margins.top() + margins.bottom()
        if max_height is not None and max_height > 0:
            min_height = row_height + margins.top() + margins.bottom()
            height = max(min_height, min(height, max_height))
        self.setFixedHeight(height)

    def _fit_to_anchor_panel(self, geometry: dict) -> None:
        width = self.DEFAULT_WIDTH
        bounds = geometry.get("panel_bounds")
        if bounds is not None:
            panel_left, panel_right = bounds
            available_width = max(0, panel_right - panel_left)
            proportional_width = int(available_width * self.PANEL_WIDTH_RATIO)
            width = min(width, max(self.MIN_WIDTH, proportional_width), available_width)
        self.setFixedWidth(width)

    def _current_anchor_geometry(self, parent_widget: QWidget) -> dict:
        panel = self._anchor_panel(parent_widget)
        if panel is not None and self.parentWidget() is not panel:
            self.setParent(panel)
        self._flush_anchor_layout(parent_widget, panel)

        coordinate_parent = panel or self.parentWidget()
        if coordinate_parent is not None:
            button_top_left = parent_widget.mapTo(coordinate_parent, QPoint(0, 0))
        else:
            button_top_left = parent_widget.mapToGlobal(QPoint(0, 0))
        button_rect = QRect(button_top_left, parent_widget.size())
        panel_bounds = None
        panel_bottom = None

        if panel is not None:
            panel_left = self.PANEL_MARGIN
            panel_right = panel.width() - self.PANEL_MARGIN
            panel_bounds = (panel_left, panel_right)
            panel_bottom = panel.height() - self.PANEL_MARGIN

        return {
            "button_rect": button_rect,
            "panel_bounds": panel_bounds,
            "panel_bottom": panel_bottom,
        }

    def _flush_anchor_layout(self, parent_widget: QWidget, panel: QWidget | None) -> None:
        widgets: list[QWidget] = []
        cursor: QWidget | None = parent_widget
        while cursor is not None:
            widgets.append(cursor)
            if cursor is panel:
                break
            cursor = cursor.parentWidget()
        if panel is not None and panel not in widgets:
            widgets.append(panel)

        for widget in reversed(widgets):
            widget.ensurePolished()
            widget.updateGeometry()
            layout = widget.layout()
            if layout is not None:
                layout.activate()
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def _anchor_panel(self, parent_widget: QWidget) -> QWidget | None:
        panel = parent_widget
        while panel is not None and panel.__class__.__name__ != "AgentPanel":
            panel = panel.parentWidget()
        return panel

    def _available_height_below(self, geometry: dict, y: int) -> int | None:
        bottoms: list[int] = []
        panel_bottom = geometry.get("panel_bottom")
        if panel_bottom is not None:
            bottoms.append(panel_bottom)

        if not bottoms:
            return None
        return max(0, min(bottoms) - y)

    def _refresh_row_elision(self) -> None:
        for row in self._rows:
            row._update_elided_labels()

    def _on_session_clicked(self, session_id: str) -> None:
        if session_id:
            self.session_selected.emit(session_id)
            self.hide()

    def hide(self) -> None:
        super().hide()
        self._remove_app_event_filter()
        self._release_anchor_button()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._remove_app_event_filter()
        self._release_anchor_button()

    def _install_app_event_filter(self) -> None:
        if self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._event_filter_installed = True

    def _remove_app_event_filter(self) -> None:
        if not self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._event_filter_installed = False

    def eventFilter(self, obj, event):  # noqa: N802
        if self.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                global_pos = event.globalPos()
            if not self._contains_global_pos(self, global_pos) and not self._contains_global_pos(self._anchor_widget, global_pos):
                self.hide()
        return super().eventFilter(obj, event)

    @staticmethod
    def _contains_global_pos(widget: QWidget | None, global_pos: QPoint) -> bool:
        if widget is None:
            return False
        local_pos = widget.mapFromGlobal(global_pos)
        return widget.rect().contains(local_pos)

    def _release_anchor_button(self) -> None:
        anchor = self._anchor_widget
        if anchor is None:
            return
        self._anchor_widget = None
        if hasattr(anchor, "setDown"):
            anchor.setDown(False)
        anchor.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
        # Use deferred calls to ensure clean state after all event processing
        QTimer.singleShot(0, anchor.clearFocus)
        QTimer.singleShot(0, lambda: QApplication.sendEvent(anchor, QEvent(QEvent.Type.Leave)))
        QTimer.singleShot(0, anchor.update)

    def _show_context_menu(self, session_id: str, current_name: str, global_pos: QPoint) -> None:
        if not session_id:
            return

        menu = create_isolated_context_menu(self)

        rename_action = menu.addAction("重命名")
        delete_action = menu.addAction("删除")
        action = menu.exec(global_pos)

        if action == rename_action:
            new_name, ok = QInputDialog.getText(
                self, "重命名对话", "新名称:", text=current_name
            )
            if ok and new_name:
                self.rename_session_requested.emit(session_id, new_name)
        elif action == delete_action:
            self.delete_session_requested.emit(session_id)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
