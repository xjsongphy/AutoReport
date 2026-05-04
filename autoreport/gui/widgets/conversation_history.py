"""Inline conversation history dropdown — Cline-style session switcher."""

from datetime import datetime
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..scale import dpi_scale


class ConversationHistoryDropdown(QWidget):
    """Inline dropdown list showing conversation sessions.

    Slides down below the agent header. Not a popup — remains in the widget tree.
    """

    session_selected = pyqtSignal(str)
    new_conversation_requested = pyqtSignal()
    delete_session_requested = pyqtSignal(str)
    rename_session_requested = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("historyDropdown")
        self.setVisible(False)
        self._setup_ui()

    def _setup_ui(self) -> None:
        s = dpi_scale()
        self.setFixedHeight(round(260 * s))
        self.setMaximumWidth(round(300 * s))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Session list — compact Copilot-style
        self._session_list = QListWidget()
        self._session_list.setObjectName("sessionList")
        self._session_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._session_list.itemClicked.connect(self._on_item_clicked)
        self._session_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._session_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._session_list, 1)

        # Bottom bar: new button
        new_btn = QPushButton("+ 新建对话")
        new_btn.setObjectName("newSessionBtn")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self._on_new_conversation)
        new_btn.setFixedHeight(round(32 * s))
        layout.addWidget(new_btn)

        self._apply_style()

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark
        s = dpi_scale()

        def px(v: int) -> str:
            return f"{round(v * s)}px"

        bg = "#1f1f1f" if dark else "#ffffff"
        border = "#2b2b2b" if dark else "#e0e0e0"
        fg = "#cccccc" if dark else "#333333"
        muted = "#8b949e"
        hover = "#2a2d2e" if dark else "#f5f5f5"
        new_bg = "#1e3a5f" if dark else "#e8f0fe"
        new_fg = "#4fc3f7"
        selected_bg = "#094771" if dark else "#e8f0fe"

        self.setStyleSheet(f"""
            QWidget#historyDropdown {{
                background-color: {bg};
                border: 1px solid {border};
                border-top: none;
            }}
            QListWidget#sessionList {{
                background-color: transparent;
                border: none;
                outline: none;
                font-size: {px(13)};
                color: {fg};
            }}
            QListWidget#sessionList::item {{
                padding: {px(5)} {px(12)};
                border-radius: {px(2)};
                margin: {px(1)} {px(4)};
            }}
            QListWidget#sessionList::item:hover {{
                background-color: {hover};
            }}
            QListWidget#sessionList::item:selected {{
                background-color: {selected_bg};
            }}
            QPushButton#newSessionBtn {{
                background-color: {new_bg};
                border: none;
                border-top: 1px solid {border};
                color: {new_fg};
                font-size: {px(12)};
                font-weight: 600;
                border-radius: 0;
            }}
            QPushButton#newSessionBtn:hover {{
                background-color: {hover};
            }}
        """)

    def populate(self, sessions: list[dict], current_session_id: str | None = None) -> None:
        self._session_list.clear()

        for session in sessions:
            session_id = session.get("id", "")
            name = session.get("name", "未命名对话")
            timestamp = session.get("timestamp", "")
            preview = session.get("preview", "")

            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%m/%d %H:%M")
            except Exception:
                time_str = timestamp

            # Copilot-style: name (bold) — preview below
            if preview:
                preview_short = preview[:40] + "…" if len(preview) > 40 else preview
                item_text = f"{name}  {time_str}\n{preview_short}"
            else:
                item_text = f"{name}  {time_str}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, session_id)

            if session_id == current_session_id:
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self._session_list.addItem(item)

        self.setVisible(True)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self.session_selected.emit(session_id)
            self.setVisible(False)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        pass  # single-click handles selection

    def _on_new_conversation(self) -> None:
        self.new_conversation_requested.emit()
        self.setVisible(False)

    def _show_context_menu(self, pos) -> None:
        item = self._session_list.itemAt(pos)
        if not item:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id:
            return

        from PyQt6.QtWidgets import QInputDialog, QMenu

        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
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
                border-radius: 2px;
                padding: 2px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: {fg};
                padding: 6px 12px;
                font-size: 12px;
            }}
            QMenu::item:hover {{
                background-color: {hover};
            }}
        """)

        rename_action = menu.addAction("重命名")
        delete_action = menu.addAction("删除")
        action = menu.exec(self._session_list.mapToGlobal(pos))

        if action == rename_action:
            new_name, ok = QInputDialog.getText(
                self, "重命名对话", "新名称:", text=item.text().split("\n")[0]
            )
            if ok and new_name:
                self.rename_session_requested.emit(session_id, new_name)
        elif action == delete_action:
            self.delete_session_requested.emit(session_id)
