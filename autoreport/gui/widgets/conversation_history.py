"""Floating conversation history dropdown with hover delete button."""

from datetime import datetime

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from .base_popup_dropdown import BasePopupDropdown


class SessionListItem(QWidget):
    """Custom widget for session list item with hover delete button."""

    delete_requested = pyqtSignal(str)

    def __init__(self, session_id: str, name: str, timestamp: str, preview: str = "", is_current: bool = False, parent=None):
        super().__init__(parent)
        self._session_id = session_id
        self._is_current = is_current
        self._setup_ui(name, timestamp, preview)

    def _setup_ui(self, name: str, timestamp: str, preview: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 8, 6)
        layout.setSpacing(8)

        # Left: name + preview
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(1)

        name_label = QLabel(name)
        name_label.setObjectName("sessionName")
        if self._is_current:
            name_label.setStyleSheet("font-weight: 600; color: #0078d4;")
        left_layout.addWidget(name_label)

        if preview:
            preview_short = preview[:35] + "…" if len(preview) > 35 else preview
            preview_label = QLabel(preview_short)
            preview_label.setObjectName("sessionPreview")
            preview_label.setStyleSheet("color: #8b949e; font-size: 11px;")
            left_layout.addWidget(preview_label)

        layout.addLayout(left_layout, 1)

        # Right: time label and delete button (stacked, delete on hover)
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        # Time label (shown by default, hidden on hover)
        self._time_label = QLabel()
        self._time_label.setObjectName("sessionTime")
        self._time_label.setStyleSheet("color: #8b949e; font-size: 11px;")
        right_layout.addWidget(self._time_label)

        try:
            dt = datetime.fromisoformat(timestamp)
            self._time_label.setText(dt.strftime("%m/%d %H:%M"))
        except Exception:
            self._time_label.setText("")

        # Delete button (hidden by default, shown on hover)
        self._delete_btn = QPushButton("删除")
        self._delete_btn.setObjectName("sessionDeleteBtn")
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setFixedHeight(18)
        self._delete_btn.setVisible(False)
        self._delete_btn.clicked.connect(self._on_delete)
        right_layout.addWidget(self._delete_btn)

        layout.addWidget(right_widget)

        # Install event filter for hover
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def _on_delete(self) -> None:
        self.delete_requested.emit(self._session_id)

    def enterEvent(self, event) -> None:
        self._time_label.setVisible(False)
        self._delete_btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._time_label.setVisible(True)
        self._delete_btn.setVisible(False)
        super().leaveEvent(event)


class ConversationHistoryDropdown(BasePopupDropdown):
    """Floating dropdown list showing conversation sessions.

    Inherits unified styling and animations from BasePopupDropdown.
    """

    session_selected = pyqtSignal(str)
    delete_session_requested = pyqtSignal(str)
    rename_session_requested = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None):
        """Initialize the conversation history dropdown."""
        super().__init__(parent)
        self.setObjectName("historyDropdown")

        # Setup context menu for delete/rename
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Override base styling with delete button style
        self._apply_extended_style()

    def _apply_extended_style(self) -> None:
        """Add delete button styling to base theme."""
        from PyQt6.QtWidgets import QApplication

        delete_btn_style = """
            QPushButton#sessionDeleteBtn {
                background-color: #f44747;
                border: none;
                color: #ffffff;
                font-size: 11px;
                font-weight: 500;
                border-radius: 3px;
                padding: 0 6px;
            }
            QPushButton#sessionDeleteBtn:hover {
                background-color: #d32f2f;
            }
        """
        # Append to existing stylesheet
        current_style = self.styleSheet() or ""
        self.setStyleSheet(current_style + delete_btn_style)

    def show_dropdown(self, parent_widget: QWidget) -> None:
        """Position and show the dropdown below parent widget."""
        if not parent_widget:
            return

        self.clear()
        self.populate_from_store()

        if self.count() == 0:
            return

        # Use base class show_dropdown for positioning and fade-in
        super().show_dropdown(parent_widget)

    def _on_item_clicked(self, item) -> None:
        """Handle item click - emit session_selected signal."""
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self.session_selected.emit(session_id)

    def populate_from_store(self) -> None:
        """Populate from conversation store via signal callback."""
        # This will be called by parent with actual session data
        pass

    def populate(self, sessions: list[dict], current_session_id: str | None = None) -> None:
        self.clear()

        for session in sessions:
            session_id = session.get("id", "")
            name = session.get("name", "未命名对话")
            timestamp = session.get("timestamp", "")
            preview = session.get("preview", "")

            # Create custom widget item
            item_widget = SessionListItem(
                session_id, name, timestamp, preview,
                is_current=(session_id == current_session_id)
            )
            item_widget.delete_requested.connect(self.delete_session_requested.emit)

            # Wrap in QListWidgetItem
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, session_id)
            size_hint = item_widget.sizeHint()
            item.setSizeHint(size_hint)

            self.addItem(item)
            self.setItemWidget(item, item_widget)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self.session_selected.emit(session_id)
            self.hide()

    def _show_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if not item:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id:
            return

        from PyQt6.QtWidgets import QInputDialog, QMenu

        hints = self.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark
        bg = "#252526" if dark else "#ffffff"
        border = "#3c3c3c" if dark else "#e0e0e0"
        fg = "#cccccc" if dark else "#333333"
        hover = "#2a2d2e" if dark else "#f5f5f5"

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: {fg};
                padding: 6px 12px;
                font-size: 12px;
                border-radius: 3px;
            }}
            QMenu::item:hover {{
                background-color: {hover};
            }}
        """)

        rename_action = menu.addAction("重命名")
        delete_action = menu.addAction("删除")
        action = menu.exec(self.mapToGlobal(pos))

        if action == rename_action:
            widget = self.itemWidget(item)
            if widget:
                name_label = widget.findChild(QLabel, "sessionName")
                current_name = name_label.text() if name_label else ""
            else:
                current_name = ""
            new_name, ok = QInputDialog.getText(
                self, "重命名对话", "新名称:", text=current_name
            )
            if ok and new_name:
                self.rename_session_requested.emit(session_id, new_name)
        elif action == delete_action:
            self.delete_session_requested.emit(session_id)

