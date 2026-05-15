"""Agent panel — Codex CLI style with flat timeline, status indicator, and clean input."""

from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
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
from autoreport.gui.widgets.ui_utils import IconActionButton
from autoreport.utils.agent_labels import get_agent_badge, get_agent_title, get_agent_icon
from autoreport.gui.widgets.messages_area import MessagesArea
from autoreport.gui.widgets.status_indicator import StatusIndicator
from autoreport.gui.widgets.working_border import WorkingBorder
from autoreport.interfaces.types import ApiDebugMessage
from autoreport.utils.logging_config import ui_logger


class AgentPanel(QWidget):
    """Codex CLI-style agent panel with flat timeline, status bar, and composer."""

    message_sent = pyqtSignal(str)
    interrupt_requested = pyqtSignal()
    _debug_msg_signal = pyqtSignal(object)
    history_requested = pyqtSignal()
    new_conversation_requested = pyqtSignal()
    session_selected_from_dropdown = pyqtSignal(str)
    delete_session_requested = pyqtSignal(str)
    rename_session_requested = pyqtSignal(str, str)
    conversation_cleared = pyqtSignal()
    compact_requested = pyqtSignal()
    init_requested = pyqtSignal()

    def __init__(self, panel_id: str, title: str, workspace: Path | None = None):
        super().__init__()
        self.panel_id = panel_id
        self._agent_type = "sub"
        self._is_working = False
        self._workspace = Path(workspace).resolve() if workspace else Path.cwd()
        self._preview_context: tuple[str, str, int, int] | None = None
        self._opened_file: str | None = None
        self._context_enabled: bool = True
        self._current_tool_group = None
        self._pending_tool_groups: list = []

        self._file_search_manager = FileSearchManager(self._workspace)
        self._file_search_popup: FileSearchPopup | None = None

        self._setup_ui(title)
        self._setup_file_search()
        self._update_width()

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

        # Icon label
        self._icon_label = QLabel()
        self._icon_label.setObjectName("panelIcon")
        self._icon_label.setFixedSize(24, 24)
        self._icon_label.setScaledContents(True)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        hl.addWidget(self._icon_label)

        # Title label
        self._title_label = QLabel(title)
        self._title_label.setObjectName("panelTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        hl.addWidget(self._title_label)

        self._status_label = QLabel("idle")
        self._status_label.setObjectName("panelStatus")
        hl.addWidget(self._status_label)

        hl.addStretch()

        self._new_conv_btn = IconActionButton(
            text="+",
            tooltip="New conversation",
            object_name="headerAction",
            button_size=(28, 28),
            on_click=self._on_new_conversation,
        )
        hl.addWidget(self._new_conv_btn)

        self._history_btn = IconActionButton(
            text="☰",
            tooltip="History",
            object_name="headerAction",
            button_size=(28, 28),
            on_click=self._on_history,
        )
        hl.addWidget(self._history_btn)

        layout.addWidget(header)

        # ---- Floating history dropdown (popup, not in layout) ----
        self._history_dropdown = ConversationHistoryDropdown()
        self._history_dropdown.session_selected.connect(self._on_history_session_selected)
        self._history_dropdown.delete_session_requested.connect(self._on_history_delete)
        self._history_dropdown.rename_session_requested.connect(self._on_history_rename)

        # ---- Queued follow-up messages ----
        self._queue_preview = QWidget()
        self._queue_preview.setObjectName("queuePreview")
        self._queue_preview.setVisible(False)
        ql = QVBoxLayout(self._queue_preview)
        ql.setContentsMargins(16, 8, 16, 6)
        ql.setSpacing(2)

        self._queue_title = QLabel("Queued messages")
        self._queue_title.setObjectName("queueTitle")
        ql.addWidget(self._queue_title)

        self._queue_items = QLabel("")
        self._queue_items.setObjectName("queueItems")
        self._queue_items.setWordWrap(True)
        self._queue_items.setTextFormat(Qt.TextFormat.PlainText)
        ql.addWidget(self._queue_items)

        layout.addWidget(self._queue_preview)

        # ---- Messages area ----
        self._messages_area = MessagesArea()
        self._messages_area.edit_requested.connect(self._on_message_edit_requested)
        self._messages_area.edit_saved.connect(self._on_message_edit_saved)
        self._messages_area.edit_cancelled.connect(self._on_message_edit_cancelled)
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
        self._context_label.setWordWrap(True)
        cl.addWidget(self._context_label, 1)

        self._context_eye = IconActionButton(
            text="👁",
            tooltip="Include context (toggle)",
            object_name="contextEye",
            button_size=(24, 24),
            on_click=self._on_eye_toggled,
        )
        self._context_eye.setCheckable(True)
        self._context_eye.setChecked(True)
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
        self._input_field.setPlaceholderText("Message…  (@ file, / command)")
        self._input_field.send_message.connect(self._on_send)
        self._input_field.file_reference_requested.connect(self._on_file_reference_requested)
        self._input_field.command_palette_requested.connect(self._on_command_palette_requested)
        self._input_field.popup_navigate.connect(self._on_popup_navigate)
        icl.addWidget(self._input_field, 1)

        self._send_btn = IconActionButton(
            text="↑",
            object_name="sendBtn",
            button_size=(26, 26),
            on_click=self._on_send_btn_clicked,
        )

        icl.addWidget(self._send_btn)

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

        add_btn = IconActionButton(
            text="+",
            tooltip="添加上下文",
            object_name="secondaryBtn",
            button_size=(22, 18),
        )
        sl.addWidget(add_btn)

        at_btn = IconActionButton(
            text="@",
            tooltip="引用文件",
            object_name="secondaryBtn",
            button_size=(22, 18),
        )
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

        # Command palette popup (lightweight, no file search)
        self._cmd_popup = QListWidget()
        self._cmd_popup.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self._cmd_popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._cmd_popup.setFixedWidth(420)
        self._cmd_popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cmd_popup.itemClicked.connect(self._on_command_selected)
        self._cmd_popup.hide()

    def _update_width(self) -> None:
        """Update minimum width to fit header content.

        Calculate minimum width needed for header content (title + buttons).
        Let splitter control actual width through stretch factor.
        """
        # Force a layout update to get correct sizes
        self._title_label.updateGeometry()
        self._status_label.updateGeometry()

        # Use actual widget sizes instead of font metrics
        title_width = self._title_label.sizeHint().width()
        status_width = self._status_label.sizeHint().width()

        # Calculate minimum width:
        # - Left margin (hl.setContentsMargins(16, 0, 16, 0)): 16px
        # - Icon: 24px
        # - Spacing after icon: 8px (hl.setSpacing(8))
        # - Title: variable
        # - Spacing after title: 8px
        # - Status: variable
        # - Stretch: takes remaining space
        # - Spacing before buttons: 8px
        # - 2 buttons: 28px * 2
        # - Spacing between buttons: 8px
        # - Right margin: 16px
        min_width = 16 + 24 + 8 + title_width + 8 + status_width + 8 + (28 * 2) + 8 + 16
        # Add extra padding for safety
        min_width += 10
        self.setMinimumWidth(min_width)

    # ---- File reference handling ----

    def _on_file_reference_requested(self, query: str, position: QPoint) -> None:
        if not self._file_search_popup:
            return
        # Position popup above input, same width
        popup_w = self._input_field.width()
        self._file_search_popup.setFixedWidth(popup_w)
        # Calculate position: above the input field
        input_top = self._input_field.mapToGlobal(self._input_field.rect().topLeft())
        popup_h = self._file_search_popup.calculate_height()
        self._file_search_popup.move(input_top.x(), input_top.y() - popup_h)
        self._file_search_popup.set_query(query, waiting=True)
        self._file_search_popup.show()
        self._file_search_popup.raise_()

        # Run search synchronously via thread pool (fast: in-memory cache)
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=1)

        def _do_search():
            return self._file_search_manager._do_search(query)

        def _on_done(future):
            matches = future.result()
            if self._file_search_popup and self._file_search_popup.isVisible():
                self._file_search_popup.set_matches(matches)
            executor.shutdown(wait=False)

        future = executor.submit(_do_search)
        future.add_done_callback(_on_done)

    def _on_file_selected(self, file_path: Path) -> None:
        self._file_search_popup.hide()
        self._close_popup()
        self._input_field.setFocus()
        self._input_field.insert_file_reference(file_path)

    def _on_file_search_cancelled(self) -> None:
        self._file_search_popup.hide()
        self._cmd_popup.hide()
        self._close_popup()
        self._input_field.setFocus()

    def _on_agent_selected(self, agent_type: str) -> None:
        self._file_search_popup.hide()
        self._close_popup()
        self._input_field.setFocus()
        name = FileSearchPopup.AGENT_INFO.get(agent_type, (agent_type, ""))[0]
        self._input_field.insert_agent_reference(name)

    def _on_popup_navigate(self, direction: str) -> None:
        """Forward popup navigation from ChatInput to active popup."""
        if direction == "cancel":
            self._file_search_popup.hide()
            self._cmd_popup.hide()
            self._close_popup()
            return
        popup = self._file_search_popup if self._file_search_popup.isVisible() else self._cmd_popup
        if direction == "up":
            popup.move_up()
        elif direction == "down":
            popup.move_down()
        elif direction == "select":
            popup.select_current()

    def _close_popup(self) -> None:
        self._input_field.set_popup_active(False)

    def _on_message_edit_requested(self, content: str) -> None:
        """Handle edit request from a user message (legacy, for compatibility)."""
        self._input_field.set_text(content)
        self._input_field.setFocus()

    def _on_message_edit_saved(self, content: str, row) -> None:
        """Handle edit saved from a user message - remove original and prepare to send."""
        # Remove the original message row
        self._messages_area.remove_message_row(row)
        # Set the input text to the edited content
        self._input_field.set_text(content)
        self._input_field.setFocus()

    def _on_message_edit_cancelled(self) -> None:
        """Handle edit cancelled - just reset state."""
        pass

    # ---- Command palette (/ commands) ----

    SLASH_COMMANDS = [
        "/new",
        "/clear",
        "/help",
        "/compact",
        "/init",
    ]

    def _on_command_palette_requested(self, query: str, position: QPoint) -> None:
        """Show a popup with available slash commands above the input field."""
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        bg = "#1f1f1f" if dark else "#ffffff"
        border = "#2b2b2b" if dark else "#e0e0e0"
        fg = "#cccccc" if dark else "#333333"
        hover = "#2a2d2e" if dark else "#e8e8e8"
        sel_bg = "#094771" if dark else "#cce4f7"

        # Filter commands matching query
        q = query.lower()
        matches = [cmd for cmd in self.SLASH_COMMANDS if q in cmd.lower()]

        self._cmd_popup.clear()
        for cmd in matches:
            item = QListWidgetItem(f"  {cmd}")
            item.setData(Qt.ItemDataRole.UserRole, cmd)
            self._cmd_popup.addItem(item)
        if self._cmd_popup.count() > 0:
            self._cmd_popup.setCurrentRow(0)

        # Position above input, same width
        popup_w = self._input_field.width()
        self._cmd_popup.setFixedWidth(popup_w)
        input_top = self._input_field.mapToGlobal(self._input_field.rect().topLeft())
        h = min(self._cmd_popup.sizeHintForRow(0) * self._cmd_popup.count() + 12, 200)
        self._cmd_popup.setFixedHeight(h)
        self._cmd_popup.move(input_top.x(), input_top.y() - h)
        self._cmd_popup.show()
        self._cmd_popup.raise_()

    def _on_command_selected(self, item: QListWidgetItem) -> None:
        cmd = item.data(Qt.ItemDataRole.UserRole)
        if not cmd:
            return
        self._cmd_popup.hide()
        self._close_popup()
        self._input_field.setFocus()
        # Execute the command directly
        text = self._input_field.toPlainText()
        self._input_field.clear_text()
        self._execute_slash_command(cmd, text)

    def _execute_slash_command(self, cmd: str, original_text: str) -> None:
        """Execute a slash command."""
        if cmd == "/help":
            help_text = "可用命令：\n" + "\n".join(f"  {c}" for c in self.SLASH_COMMANDS)
            self.add_message("agent", help_text)
        elif cmd in ("/clear", "/new"):
            self.clear_conversation()
        elif cmd == "/compact":
            self.compact_requested.emit()
        elif cmd == "/init":
            self.init_requested.emit()

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

    def clear_file_context(self) -> None:
        """Clear attached file/selection context so next message won't include it."""
        self._opened_file = None
        self._preview_context = None
        self._context_bar.setVisible(False)

    def _on_eye_toggled(self) -> None:
        self._context_enabled = self._context_eye.isChecked()
        self._context_eye.setText("👁" if self._context_enabled else "🚫")

    def set_workspace(self, workspace: Path) -> None:
        self._workspace = Path(workspace).resolve()
        self._file_search_manager = FileSearchManager(self._workspace)

    def set_agent_type(self, agent_type: str) -> None:
        self._agent_type = agent_type
        # Update icon
        icon = get_agent_icon(agent_type, size=24)
        self._icon_label.setPixmap(icon.pixmap(24, 24))
        # Update title
        self._title_label.setText(get_agent_title(agent_type))
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
        summary: str | None = None,
        detail: str | None = None,
        expandable: bool = True,
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
            summary=summary,
            detail=detail,
            expandable=expandable,
        )

    def add_tool_call(
        self,
        tool_name: str,
        arguments: dict,
        summary: str | None = None,
        detail: str | None = None,
        expandable: bool = True,
    ) -> None:
        # One tool call -> one tool group row.
        self._current_tool_group = self._messages_area.add_tool_group()
        self._pending_tool_groups.append(self._current_tool_group)
        self._current_tool_group.add_tool_call(
            name=tool_name,
            arguments=arguments,
            success=None,
            duration_ms=0,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )

    def add_tool_result(
        self,
        tool_name: str,
        result: Any,
        error: str | None = None,
        summary: str | None = None,
        detail: str | None = None,
        expandable: bool | None = None,
    ) -> None:
        target_group = None
        if self._pending_tool_groups:
            target_group = self._pending_tool_groups.pop(0)
        elif hasattr(self, "_current_tool_group") and self._current_tool_group:
            target_group = self._current_tool_group

        if target_group:
            target_group.complete_tool_call(
                name=tool_name,
                result=result,
                error=error,
                duration_ms=100,
                summary=summary,
                detail=detail,
                expandable=expandable,
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
        short_id = checkpoint_id[-12:] if len(checkpoint_id) > 12 else checkpoint_id
        self._messages_area.add_message_row(
            role="agent",
            content=f"⚑ [{short_id}] {description}",
            timestamp=ts,
        )

    def handle_task_update(
        self,
        task_id: str,
        action: str,
        source: str,
        target: str,
        brief: str,
    ) -> None:
        """Render task/list updates in a compact, stable format."""
        is_main = self._agent_type in ("main",)
        am_source = self._agent_type == source
        am_target = self._agent_type == target
        is_local = source == target

        summary = str(brief or "").strip() or "task"
        source_badge = get_agent_badge(source)
        target_badge = get_agent_badge(target)

        if action == "created":
            if is_local:
                text = f"TODO ? Local ? {summary}"
            elif am_source:
                text = f"WAIT ? {target_badge} ? {summary}"
            elif am_target:
                text = f"TODO ? From {source_badge} ? {summary}"
            elif is_main:
                text = f"TASK ? {source_badge} -> {target_badge} ? {summary}"
            else:
                text = f"TASK ? {summary}"

        elif action == "completed":
            if am_source:
                text = f"DONE ? {target_badge} ? {summary}"
            elif am_target:
                text = f"DONE ? From {source_badge} ? {summary}"
            elif is_main:
                text = f"DONE ? {source_badge} -> {target_badge} ? {summary}"
            else:
                text = f"DONE ? {summary}"

        elif action == "failed":
            if am_source:
                text = f"FAIL ? {target_badge} ? {summary}"
            elif am_target:
                text = f"FAIL ? From {source_badge} ? {summary}"
            elif is_main:
                text = f"FAIL ? {source_badge} -> {target_badge} ? {summary}"
            else:
                text = f"FAIL ? {summary}"

        elif action == "cancelled":
            if am_source:
                text = f"CANCEL ? {target_badge} ? {summary}"
            elif am_target:
                text = f"CANCEL ? From {source_badge} ? {summary}"
            elif is_main:
                text = f"CANCEL ? {source_badge} -> {target_badge} ? {summary}"
            else:
                text = f"CANCEL ? {summary}"

        elif action == "started":
            if is_local:
                text = f"RUNNING ? Local ? {summary}"
            elif am_source:
                text = f"RUNNING ? {target_badge} ? {summary}"
            elif am_target:
                text = f"RUNNING ? From {source_badge} ? {summary}"
            elif is_main:
                text = f"RUNNING ? {source_badge} -> {target_badge} ? {summary}"
            else:
                text = f"RUNNING ? {summary}"

        else:
            text = f"TASK UPDATE ? {summary}"

        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role="agent",
            content=text,
            timestamp=ts,
            is_coordination=True,
        )

    # ---- Status ----

    def _set_working(self, working: bool) -> None:
        """Toggle send/stop button appearance."""
        self._is_working = working
        if working:
            self._send_btn.setText("■")
            self._send_btn.setObjectName("stopBtn")
        else:
            self._send_btn.setText("↑")
            self._send_btn.setObjectName("sendBtn")
        # Force style refresh
        self._send_btn.style().unpolish(self._send_btn)
        self._send_btn.style().polish(self._send_btn)

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
            self._set_working(True)
        else:
            self._status_indicator.stop()
            self._working_border.stop()
            self._set_working(False)

    def set_queue_preview(self, queued_messages: list[str]) -> None:
        if not queued_messages:
            self._queue_preview.setVisible(False)
            self._queue_items.setText("")
            return

        preview_lines = [f"• {msg}" for msg in queued_messages[:3]]
        if len(queued_messages) > 3:
            preview_lines.append(f"... and {len(queued_messages) - 3} more")
        self._queue_items.setText("\n".join(preview_lines))
        self._queue_preview.setVisible(True)

    # ---- Actions ----

    def _on_send(self) -> None:
        content = self._input_field.get_plain_text().strip()
        if not content:
            return

        # Handle slash commands (manual type + Enter without popup selection)
        if content.startswith("/"):
            cmd = content.split()[0].lower()
            ui_logger.debug("AgentPanel[{}]: slash command {}", self.panel_id, cmd)
            self._execute_slash_command(cmd, content)
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

        ui_logger.debug("AgentPanel[{}]: sending message ({} chars)", self.panel_id, len(final_message))
        self._input_field.clear_text()
        self._set_working(True)
        self.message_sent.emit(final_message)

        self._preview_context = None
        self._opened_file = None
        self._context_bar.setVisible(False)

    def _on_send_btn_clicked(self) -> None:
        """Handle send button click — send or interrupt based on state."""
        if self._is_working:
            self.interrupt_requested.emit()
        else:
            self._on_send()

    def _on_history(self) -> None:
        ui_logger.debug("AgentPanel[{}]: history button clicked", self.panel_id)
        if self._history_dropdown.isVisible():
            self._history_dropdown.hide()
        else:
            # Request session data and show dropdown
            self.history_requested.emit()
            # Dropdown will be shown after data is loaded via show_history_dropdown()

    def _on_new_conversation(self) -> None:
        ui_logger.debug("AgentPanel[{}]: new conversation button clicked", self.panel_id)
        self.new_conversation_requested.emit()

    def show_history_dropdown(self, sessions: list[dict], current_id: str | None = None) -> None:
        self._history_dropdown.populate(sessions, current_id)
        self._history_dropdown.show_dropdown(self._history_btn)

    def _on_history_session_selected(self, session_id: str) -> None:
        self.session_selected_from_dropdown.emit(session_id)

    def _on_history_new_conversation(self) -> None:
        self.new_conversation_requested.emit()

    def _on_history_delete(self, session_id: str) -> None:
        self.delete_session_requested.emit(session_id)

    def _on_history_rename(self, session_id: str, new_name: str) -> None:
        self.rename_session_requested.emit(session_id, new_name)

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
        self._debug_panel.setVisible(enabled)

    def hide_conv_buttons(self, hide: bool = True) -> None:
        self._history_btn.setHidden(hide)
        self._new_conv_btn.setHidden(hide)

    def clear_conversation(self) -> None:
        """Clear messages and notify backend."""
        self._messages_area.clear()
        self._pending_tool_groups.clear()
        self._current_tool_group = None
        self.conversation_cleared.emit()
