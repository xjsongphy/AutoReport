"""Agent panel — Codex CLI style with flat timeline, status indicator, and clean input."""

from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from autoreport.core.file_search import FileSearchManager
from autoreport.gui.widgets.chat_input import ChatInput
from autoreport.gui.widgets.conversation_history import ConversationHistoryDropdown
from autoreport.gui.widgets.debug_panel import DebugPanel
from autoreport.gui.widgets.file_search_popup import FileSearchPopup
from autoreport.gui.widgets.messages_area import MessagesArea
from autoreport.gui.widgets.status_indicator import StatusIndicator
from autoreport.gui.widgets.working_border import WorkingBorder
from autoreport.interfaces.types import ApiDebugMessage


class AgentPanel(QWidget):
    """Codex CLI-style agent panel with flat timeline, status bar, and composer."""

    message_sent = pyqtSignal(str)
    debug_mode_toggled = pyqtSignal(bool)
    _debug_msg_signal = pyqtSignal(object)
    history_requested = pyqtSignal()
    new_conversation_requested = pyqtSignal()
    session_selected_from_dropdown = pyqtSignal(str)
    delete_session_requested = pyqtSignal(str)
    rename_session_requested = pyqtSignal(str, str)
    conversation_cleared = pyqtSignal()

    def __init__(self, panel_id: str, title: str, workspace: Path | None = None):
        super().__init__()
        self.panel_id = panel_id
        self._agent_type = "sub"
        self._workspace = Path(workspace).resolve() if workspace else Path.cwd()
        self._preview_context: tuple[str, str, int, int] | None = None
        self._opened_file: str | None = None
        self._context_enabled: bool = True
        self._current_tool_group = None

        self._file_search_manager = FileSearchManager(self._workspace)
        self._file_search_popup: FileSearchPopup | None = None

        self._setup_ui(title)
        self._setup_file_search()

        self._debug_msg_signal.connect(self._handle_debug_msg)

    def _setup_ui(self, title: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- Header (minimal, Codex-style) ----
        header = QWidget()
        header.setObjectName("panelHeader")
        header.setFixedHeight(36)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(8)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("panelTitle")
        hl.addWidget(self._title_label)

        self._status_label = QLabel("idle")
        self._status_label.setObjectName("panelStatus")
        hl.addWidget(self._status_label)

        hl.addStretch()

        self._new_conv_btn = QPushButton("+")
        self._new_conv_btn.setObjectName("headerAction")
        self._new_conv_btn.setToolTip("New conversation")
        self._new_conv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_conv_btn.clicked.connect(self._on_new_conversation)
        self._new_conv_btn.setFixedSize(28, 28)
        hl.addWidget(self._new_conv_btn)

        self._history_btn = QPushButton("☰")
        self._history_btn.setObjectName("headerAction")
        self._history_btn.setToolTip("History")
        self._history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_btn.clicked.connect(self._on_history)
        self._history_btn.setFixedSize(28, 28)
        hl.addWidget(self._history_btn)

        self._debug_button = QPushButton("Debug")
        self._debug_button.setObjectName("debugBtn")
        self._debug_button.setCheckable(True)
        self._debug_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._debug_button.clicked.connect(self._on_debug_toggled)
        hl.addWidget(self._debug_button)

        layout.addWidget(header)

        # ---- Inline history dropdown ----
        self._history_dropdown = ConversationHistoryDropdown()
        self._history_dropdown.setVisible(False)
        self._history_dropdown.session_selected.connect(self._on_history_session_selected)
        self._history_dropdown.new_conversation_requested.connect(self._on_history_new_conversation)
        self._history_dropdown.delete_session_requested.connect(self._on_history_delete)
        self._history_dropdown.rename_session_requested.connect(self._on_history_rename)
        layout.addWidget(self._history_dropdown)

        # ---- Messages area ----
        self._messages_area = MessagesArea()
        layout.addWidget(self._messages_area, 1)

        # ---- Debug panel (hidden) ----
        self._debug_panel = DebugPanel()
        self._debug_panel.setVisible(False)
        layout.addWidget(self._debug_panel)

        # ---- Status indicator (Codex-style, animated) ----
        self._status_indicator = StatusIndicator()
        layout.addWidget(self._status_indicator)

        # ---- Context chip bar ----
        self._context_bar = QWidget()
        self._context_bar.setObjectName("contextBar")
        self._context_bar.setVisible(False)
        cl = QHBoxLayout(self._context_bar)
        cl.setContentsMargins(16, 4, 12, 4)
        cl.setSpacing(6)

        self._context_label = QLabel()
        self._context_label.setObjectName("contextLabel")
        self._context_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cl.addWidget(self._context_label, 1)

        self._context_eye = QPushButton("👁")
        self._context_eye.setObjectName("contextEye")
        self._context_eye.setCheckable(True)
        self._context_eye.setChecked(True)
        self._context_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self._context_eye.setToolTip("Include context (toggle)")
        self._context_eye.clicked.connect(self._on_eye_toggled)
        self._context_eye.setFixedSize(24, 24)
        cl.addWidget(self._context_eye)

        layout.addWidget(self._context_bar)

        # ---- Input bar (VS Code Copilot-style composer) ----
        # Single container with input + send button, wrapped by working border
        self._input_container = QWidget()
        self._input_container.setObjectName("inputContainer")
        icl = QHBoxLayout(self._input_container)
        icl.setContentsMargins(4, 2, 4, 2)
        icl.setSpacing(4)

        self._input_field = ChatInput()
        self._input_field.setPlaceholderText("Message…  (@ file, Enter send)")
        self._input_field.send_message.connect(self._on_send)
        self._input_field.file_reference_requested.connect(self._on_file_reference_requested)
        icl.addWidget(self._input_field, 1)

        send_btn = QPushButton("↑")
        send_btn.setObjectName("sendBtn")
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.clicked.connect(self._on_send)
        send_btn.setFixedSize(26, 26)

        icl.addWidget(send_btn)

        # Working border overlays the container
        self._working_border = WorkingBorder(self._input_container)
        self._working_border.show()

        layout.addWidget(self._input_container)

        # ---- Secondary toolbar (VS Code: .chat-secondary-toolbar) ----
        secondary_bar = QWidget()
        secondary_bar.setObjectName("secondaryToolbar")
        sl = QHBoxLayout(secondary_bar)
        sl.setContentsMargins(10, 0, 6, 2)
        sl.setSpacing(2)

        add_btn = QPushButton("+")
        add_btn.setObjectName("secondaryBtn")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("添加上下文")
        add_btn.setFixedSize(22, 18)
        sl.addWidget(add_btn)

        at_btn = QPushButton("@")
        at_btn.setObjectName("secondaryBtn")
        at_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        at_btn.setToolTip("引用文件")
        at_btn.setFixedSize(22, 18)
        sl.addWidget(at_btn)

        sl.addStretch()

        self._secondary_status = QLabel("")
        self._secondary_status.setObjectName("secondaryStatus")
        sl.addWidget(self._secondary_status)

        layout.addWidget(secondary_bar)

    def _setup_file_search(self) -> None:
        self._file_search_popup = FileSearchPopup(self)
        self._file_search_popup.file_selected.connect(self._on_file_selected)
        self._file_search_popup.agent_selected.connect(self._on_agent_selected)
        self._file_search_popup.cancelled.connect(self._on_file_search_cancelled)

    # ---- File reference handling ----

    def _on_file_reference_requested(self, query: str, position: QPoint) -> None:
        if not self._file_search_popup:
            return
        self._file_search_popup.move(position)
        self._file_search_popup.set_query(query, waiting=True)
        self._file_search_popup.show()
        self._file_search_popup.raise_()
        self._file_search_popup.setFocus()
        self._input_field.set_popup_active(True)

        async def on_results(matches):
            if self._file_search_popup and self._file_search_popup.isVisible():
                self._file_search_popup.set_matches(matches)

        import asyncio
        asyncio.create_task(self._file_search_manager.search(query, on_results))

    def _on_file_selected(self, file_path: Path) -> None:
        self._file_search_popup.hide()
        self._input_field.set_popup_active(False)
        self._input_field.setFocus()
        self._input_field.insert_file_reference(file_path)

    def _on_file_search_cancelled(self) -> None:
        self._file_search_popup.hide()
        self._input_field.set_popup_active(False)
        self._input_field.setFocus()

    def _on_agent_selected(self, agent_type: str) -> None:
        self._file_search_popup.hide()
        self._input_field.set_popup_active(False)
        self._input_field.setFocus()
        name = FileSearchPopup.AGENT_INFO.get(agent_type, (agent_type, ""))[0]
        self._input_field.insert_agent_reference(name)

    # ---- Public API ----

    def set_opened_file(self, file_path: str) -> None:
        self._opened_file = file_path
        self._preview_context = None
        self._context_enabled = True
        self._context_eye.setChecked(True)
        self._context_eye.setText("👁")
        self._context_label.setText(Path(file_path).name)
        self._context_bar.setVisible(True)

    def set_preview_context(self, file_path: str, selected_text: str, start_line: int, end_line: int) -> None:
        self._preview_context = (file_path, selected_text, start_line, end_line)
        self._opened_file = None
        self._context_enabled = True
        self._context_eye.setChecked(True)
        self._context_eye.setText("👁")
        lines = end_line - start_line + 1
        self._context_label.setText(f"{lines} line{'s' if lines > 1 else ''} — {Path(file_path).name}")
        self._context_bar.setVisible(True)

    def _on_eye_toggled(self) -> None:
        self._context_enabled = self._context_eye.isChecked()
        self._context_eye.setText("👁" if self._context_enabled else "🚫")

    def set_workspace(self, workspace: Path) -> None:
        self._workspace = Path(workspace).resolve()
        self._file_search_manager = FileSearchManager(self._workspace)

    def set_agent_type(self, agent_type: str) -> None:
        self._agent_type = agent_type
        titles = {
            "data_analysis": "Data Analysis",
            "plotting": "Plotting",
            "theory": "Theory",
            "report": "Report",
            "main": "Main Agent",
            "sub": "Select Agent",
        }
        self._title_label.setText(titles.get(agent_type, "Agent"))
        if self._file_search_popup:
            self._file_search_popup.set_current_agent(agent_type)

    @property
    def agent_type(self) -> str:
        return self._agent_type

    # ---- Messages ----

    def add_message(
        self,
        role: str,
        content: str,
        source: str = "user",
        coordination: bool = False,
        streaming: bool = False,
    ) -> None:
        if streaming and role == "agent" and not content:
            return

        if streaming and role == "agent":
            rows = self._messages_area.get_message_rows()
            if rows and rows[-1]._role == "agent":
                rows[-1].append_content(content)
                return

        ts = datetime.now().strftime("%H:%M")
        agent_name = self._title_label.text() or "Agent"
        self._messages_area.add_message_row(
            role=role,
            content=content,
            timestamp=ts,
            is_coordination=coordination or source == "main_agent",
            agent_name=agent_name,
        )

    def add_tool_call(self, tool_name: str, arguments: dict) -> None:
        groups = self._messages_area.get_tool_groups()
        if not groups:
            group = self._messages_area.add_tool_group()
            self._current_tool_group = group
        else:
            self._current_tool_group = groups[-1]

    def add_tool_result(self, tool_name: str, result: Any, error: str | None = None) -> None:
        if hasattr(self, "_current_tool_group") and self._current_tool_group:
            self._current_tool_group.add_tool_call(
                name=tool_name,
                arguments={},
                success=error is None,
                duration_ms=100,
                result=result if error is None else None,
                error=error,
            )

    def add_error(self, source: str, message: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role="agent",
            content=f"✗ {source}: {message}",
            timestamp=ts,
        )

    def add_checkpoint(self, checkpoint_id: str, description: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role="agent",
            content=f"⚑ {description}",
            timestamp=ts,
        )

    def handle_task_update(self, source: str, target: str, text: str) -> None:
        """Handle task update for GUI display.

        Uses coordination message style (muted, italic) to blend with timeline.
        """
        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role="agent",
            content=text,
            timestamp=ts,
            is_coordination=True,
        )

    # ---- Status ----

    def set_status(self, status: str, extra: dict | None = None) -> None:
        status_map = {
            "idle": ("idle", False),
            "thinking": ("thinking", True),
            "running_tool": ("tool", True),
            "error": ("error", False),
            "debug_mode": ("debug", False),
        }
        label, active = status_map.get(status, (status, False))
        self._status_label.setText(label)

        if active:
            header = "Thinking" if status == "thinking" else "Running tool"
            self._status_indicator.start(header)
            self._working_border.start()
        else:
            self._status_indicator.stop()
            self._working_border.stop()

    # ---- Actions ----

    def _on_send(self) -> None:
        content = self._input_field.get_plain_text().strip()
        if not content:
            return

        # Handle slash commands
        if content.startswith("/"):
            cmd = content.split()[0].lower()
            self._input_field.clear_text()
            if cmd in ("/clear", "/new"):
                self.clear_conversation()
            elif cmd == "/help":
                self.add_message("agent", "Available commands:\n/clear — Clear conversation\n/new — New conversation\n/help — Show this help")
            return

        final_message = content
        if self._context_enabled:
            if self._preview_context:
                fp, text, s, e = self._preview_context
                ctx = f"\n\n<!-- context -->\n**File**: {fp} (lines {s}-{e})\n```\n{text}\n```\n"
                final_message = content + ctx
            elif self._opened_file:
                ctx = f"\n\n<!-- context -->\n**File**: {self._opened_file}\n"
                final_message = content + ctx

        self._input_field.clear_text()
        self.message_sent.emit(final_message)

        self._preview_context = None
        self._opened_file = None
        self._context_bar.setVisible(False)

    def _on_history(self) -> None:
        if self._history_dropdown.isVisible():
            self._history_dropdown.setVisible(False)
        else:
            self.history_requested.emit()

    def _on_new_conversation(self) -> None:
        self.new_conversation_requested.emit()

    def show_history_dropdown(self, sessions: list[dict], current_id: str | None = None) -> None:
        self._history_dropdown.populate(sessions, current_id)

    def _on_history_session_selected(self, session_id: str) -> None:
        self.session_selected_from_dropdown.emit(session_id)

    def _on_history_new_conversation(self) -> None:
        self.new_conversation_requested.emit()

    def _on_history_delete(self, session_id: str) -> None:
        self.delete_session_requested.emit(session_id)

    def _on_history_rename(self, session_id: str, new_name: str) -> None:
        self.rename_session_requested.emit(session_id, new_name)

    def _on_debug_toggled(self) -> None:
        enabled = self._debug_button.isChecked()
        self._debug_panel.setVisible(enabled)
        self.debug_mode_toggled.emit(enabled)

    def subscribe_to_debug_messages(self, bus) -> None:
        async def on_debug_message(msg):
            if isinstance(msg, ApiDebugMessage):
                self._debug_msg_signal.emit(msg)

        bus.subscribe(ApiDebugMessage, on_debug_message)

    def _handle_debug_msg(self, msg) -> None:
        self._debug_panel.add_entry(
            timestamp=msg.timestamp,
            model=msg.model,
            tokens_in=msg.tokens_in,
            tokens_out=msg.tokens_out,
            duration_ms=msg.duration_ms,
            status=msg.status,
            error=msg.error,
        )

    def set_debug_mode(self, enabled: bool) -> None:
        self._debug_button.setChecked(enabled)

    def hide_debug_button(self, hide: bool = True) -> None:
        self._debug_button.setHidden(hide)

    def hide_conv_buttons(self, hide: bool = True) -> None:
        self._history_btn.setHidden(hide)
        self._new_conv_btn.setHidden(hide)

    def clear_conversation(self) -> None:
        """Clear messages and notify backend."""
        self._messages_area.clear()
        self.conversation_cleared.emit()
