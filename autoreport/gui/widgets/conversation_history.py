"""Conversation history popup dialog."""

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ConversationHistoryDialog(QDialog):
    """Dialog showing conversation history with Cline-style UI."""

    session_selected = pyqtSignal(str)  # session_id
    new_conversation_requested = pyqtSignal()
    delete_session_requested = pyqtSignal(str)  # session_id
    rename_session_requested = pyqtSignal(str, str)  # session_id, new_name

    def __init__(self, sessions: list[dict], current_session_id: str | None = None, parent: QWidget | None = None):
        """Initialize conversation history dialog.

        Args:
            sessions: List of session dicts with keys: id, name, timestamp, preview
            current_session_id: Current active session ID
            parent: Parent widget
        """
        super().__init__(parent)
        self._sessions = sessions
        self._current_session_id = current_session_id
        self._setup_ui()
        self._populate_sessions()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        self.setWindowTitle("对话历史")
        self.setFixedSize(360, 480)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)

        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        # Cline-style colors
        c = {
            "bg": "#252526" if dark else "#ffffff",
            "border": "#3c3c3c" if dark else "#e0e0e0",
            "fg": "#cccccc" if dark else "#333333",
            "fg_dim": "#858585" if dark else "#888888",
            "hover": "#2a2d2e" if dark else "#f5f5f5",
            "selected": "#094771" if dark else "#e8f0fe",
            "selectedFg": "#ffffff" if dark else "#094771",
            "borderNew": "#4fc3f7",
            "bgNew": "#1e3a5f" if dark else "#e8f0fe",
            "fgNew": "#4fc3f7",
        }

        self._colors = c
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c["bg"]};
                border: 1px solid {c["border"]};
                border-radius: 8px;
            }}
            QLabel {{
                color: {c["fg"]};
                font-size: 12px;
            }}
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-radius: 4px;
                margin: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {c["hover"]};
            }}
            QListWidget::item:selected {{
                background-color: {c["selected"]};
                color: {c["selectedFg"]};
            }}
            QPushButton {{
                background-color: transparent;
                border: 1px solid {c["border"]};
                border-radius: 4px;
                padding: 6px 12px;
                color: {c["fg"]};
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {c["hover"]};
            }}
            QLineEdit {{
                background-color: {c["hover"]};
                border: 1px solid {c["border"]};
                border-radius: 4px;
                padding: 6px;
                color: {c["fg"]};
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {c["fgNew"]};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header with title
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel("对话历史")
        title_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        layout.addWidget(header)

        # Session list
        self._session_list = QListWidget()
        self._session_list.setStyleSheet("QListWidget { font-size: 13px; }")
        self._session_list.itemClicked.connect(self._on_item_clicked)
        self._session_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._session_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._session_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._session_list)

        # New conversation button
        new_btn = QPushButton("+ 新建对话")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c["bgNew"]};
                border: 1px solid {c["borderNew"]};
                color: {c["fgNew"]};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {c["hover"]};
            }}
        """)
        new_btn.clicked.connect(self._on_new_conversation)
        layout.addWidget(new_btn)

    def _populate_sessions(self) -> None:
        """Populate the session list with conversations."""
        self._session_list.clear()

        for session in self._sessions:
            session_id = session.get("id", "")
            name = session.get("name", "未命名对话")
            timestamp = session.get("timestamp", "")
            preview = session.get("preview", "")

            # Format timestamp
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%m/%d %H:%M")
            except Exception:
                time_str = timestamp

            # Create item with session info
            item_text = f"{name}\n{time_str}"
            if preview:
                preview_short = preview[:50] + "..." if len(preview) > 50 else preview
                item_text += f" · {preview_short}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, session_id)

            # Highlight current session
            if session_id == self._current_session_id:
                item.setSelected(True)

            self._session_list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle single click - just select."""
        pass

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double click - load session."""
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self.session_selected.emit(session_id)
            self.accept()

    def _on_new_conversation(self) -> None:
        """Handle new conversation button click."""
        self.new_conversation_requested.emit()
        self.accept()

    def _show_context_menu(self, pos) -> None:
        """Show context menu for session items."""
        item = self._session_list.itemAt(pos)
        if not item:
            return

        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self._colors["bg"]};
                border: 1px solid {self._colors["border"]};
                border-radius: 4px;
                padding: 4px;
            }}
            QAction {{
                background-color: transparent;
                color: {self._colors["fg"]};
                padding: 6px 12px;
                font-size: 12px;
            }}
            QAction:hover {{
                background-color: {self._colors["hover"]};
            }}
        """)

        rename_action = menu.addAction("重命名")
        delete_action = menu.addAction("删除")

        action = menu.exec(self._session_list.mapToGlobal(pos))

        if action == rename_action:
            # Show rename dialog
            from PyQt6.QtWidgets import QInputDialog
            new_name, ok = QInputDialog.getText(
                self, "重命名对话", "新名称:", text=item.text().split("\n")[0]
            )
            if ok and new_name:
                self.rename_session_requested.emit(session_id, new_name)
        elif action == delete_action:
            self.delete_session_requested.emit(session_id)

    def update_sessions(self, sessions: list[dict], current_session_id: str | None = None) -> None:
        """Update the session list.

        Args:
            sessions: Updated list of session dicts
            current_session_id: Current active session ID
        """
        self._sessions = sessions
        self._current_session_id = current_session_id
        self._populate_sessions()
