"""Agent panel — Codex CLI style with flat timeline, status indicator, and clean input."""

from datetime import datetime
from pathlib import Path
import time
from typing import Any
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import (
    QStyle,
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
from autoreport.gui.scale import scaled
from autoreport.gui.widgets.chat_input import ChatInput
from autoreport.gui.widgets.conversation_history import ConversationHistoryDropdown
from autoreport.gui.widgets.debug_panel import DebugPanel
from autoreport.gui.widgets.file_search_popup import FileSearchPopup
from autoreport.gui.widgets.ui_utils import IconActionButton, NoWheelComboBox, render_svg_icon
from autoreport.utils.agent_labels import get_agent_badge, get_agent_title, get_agent_icon
from autoreport.gui.widgets.messages_area import MessagesArea
from autoreport.interfaces.types import ApiDebugMessage
from autoreport.utils.logging_config import ui_logger
from ..theme import get_theme_colors


class _ComposerTopFade(QWidget):
    """Top fade mask above composer: alpha from 0% (top) to 100% (bottom)."""

    def __init__(self, base_color: QColor, parent: QWidget | None = None):
        super().__init__(parent)
        self._base_color = QColor(base_color)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)

    def set_base_color(self, base_color: QColor) -> None:
        self._base_color = QColor(base_color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        grad = QLinearGradient(0, 0, 0, max(1, self.height()))
        top = QColor(self._base_color)
        bottom = QColor(self._base_color)
        top.setAlpha(0)
        # Keep fade visible but lighter to avoid "heavier opacity" after z-order fixes.
        bottom.setAlpha(210)
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bottom)
        p.fillRect(self.rect(), grad)


class AgentPanel(QWidget):
    """Codex CLI-style agent panel with flat timeline, status bar, and composer."""

    message_sent = pyqtSignal(str)
    file_context_attached = pyqtSignal(object)
    interrupt_requested = pyqtSignal()
    _debug_msg_signal = pyqtSignal(object)
    history_requested = pyqtSignal()
    new_conversation_requested = pyqtSignal()
    session_selected_from_dropdown = pyqtSignal(str)
    delete_session_requested = pyqtSignal(str)
    rename_session_requested = pyqtSignal(str, str)
    conversation_cleared = pyqtSignal()
    thinking_finished = pyqtSignal(str, str, bool)
    compact_requested = pyqtSignal()
    init_requested = pyqtSignal()
    agent_type_changed = pyqtSignal(str)
    rollback_requested = pyqtSignal(str, object)

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
        self._thinking_row = None
        self._thinking_started_at: float | None = None
        self._thinking_detail = ""
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(1000)
        self._thinking_timer.timeout.connect(self._update_thinking_timer)
        self._agent_selector: NoWheelComboBox | None = None
        self._composer_horizontal_margin = scaled(16)

        self._file_search_manager = FileSearchManager(self._workspace)
        self._file_search_executor = ThreadPoolExecutor(max_workers=1)
        self._file_search_ticket = 0
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
        header = QWidget(self)
        header.setObjectName("panelHeader")
        header.setFixedHeight(36)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(8)
        self._header = header
        self._header_layout = hl

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

        if self.panel_id != "main":
            self._title_label.setVisible(False)
            self._agent_selector = NoWheelComboBox()
            self._agent_selector.setObjectName("subAgentSelector")
            self._agent_selector.addItem("Main", "main")
            self._agent_selector.addItem("Data Analysis", "data_analysis")
            self._agent_selector.addItem("Plotting", "plotting")
            self._agent_selector.addItem("Theory", "theory")
            self._agent_selector.addItem("Report", "report")
            self._agent_selector.setMinimumContentsLength(12)
            self._agent_selector.setSizeAdjustPolicy(NoWheelComboBox.SizeAdjustPolicy.AdjustToContents)
            self._agent_selector.currentIndexChanged.connect(self._on_agent_selector_changed)
            hl.addWidget(self._agent_selector)

        self._status_label = QLabel("Idle")
        self._status_label.setObjectName("panelStatus")
        hl.addWidget(self._status_label)

        hl.addStretch()

        self._new_conv_btn = IconActionButton(
            text="+",
            tooltip="New conversation",
            object_name="headerAction",
            button_size=(22, 22),
            icon_size=(16, 16),
            on_click=self._on_new_conversation,
        )
        hl.addWidget(self._new_conv_btn)

        self._history_btn = IconActionButton(
            tooltip="History",
            object_name="headerAction",
            button_size=(22, 22),
            icon_size=(16, 16),
            on_click=self._on_history,
        )
        hl.addWidget(self._history_btn)
        self._setup_header_icons()

        layout.addWidget(header)

        # ---- Floating history dropdown (popup, not in layout) ----
        self._history_show_pending = False
        self._history_dropdown = ConversationHistoryDropdown(self)
        self._history_dropdown.session_selected.connect(self._on_history_session_selected)
        self._history_dropdown.delete_session_requested.connect(self._on_history_delete)
        self._history_dropdown.rename_session_requested.connect(self._on_history_rename)

        # ---- Queued follow-up messages ----
        self._queue_preview = QWidget(self)
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
        self._messages_area.rollback_requested.connect(self.rollback_requested.emit)
        layout.addWidget(self._messages_area, 1)

        # ---- Debug panel (hidden) ----
        self._debug_panel = DebugPanel()
        self._debug_panel.setVisible(False)
        layout.addWidget(self._debug_panel)

        # ---- Composer (floating input + dock bar) ----
        c = get_theme_colors()
        self._composer_top_fade = _ComposerTopFade(QColor(c["messages_bg"]), self)
        self._composer_top_fade.setObjectName("composerTopFade")
        self._composer_top_fade.setFixedHeight(scaled(18))
        self._composer_top_fade.setStyleSheet("QWidget#composerTopFade { border: none; background: transparent; }")

        self._composer_host = QWidget(self)
        self._composer_host.setObjectName("composerHost")
        composer_host_layout = QHBoxLayout(self._composer_host)
        composer_host_layout.setContentsMargins(
            self._composer_horizontal_margin,
            0,
            self._composer_horizontal_margin,
            0,
        )
        composer_host_layout.setSpacing(0)
        self._composer_host_layout = composer_host_layout

        self._input_container = QWidget(self._composer_host)
        self._input_container.setObjectName("inputContainer")
        self._input_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        composer_layout = QVBoxLayout(self._input_container)
        composer_layout.setContentsMargins(0, 0, 0, 0)
        composer_layout.setSpacing(0)

        input_top = QWidget(self._input_container)
        input_top.setObjectName("composerInputTop")
        icl = QHBoxLayout(input_top)
        icl.setContentsMargins(12, 10, 12, 10)
        icl.setSpacing(0)

        self._input_field = ChatInput()
        self._input_field.setPlaceholderText("Message…  (@ file, / command)")
        self._input_field.send_message.connect(self._on_send)
        self._input_field.file_reference_requested.connect(self._on_file_reference_requested)
        self._input_field.command_palette_requested.connect(self._on_command_palette_requested)
        self._input_field.popup_navigate.connect(self._on_popup_navigate)
        self._input_field.height_changed.connect(self._on_input_height_changed)
        icl.addWidget(self._input_field, 1)

        self._send_btn = IconActionButton(
            text="↑",
            object_name="sendBtn",
            button_size=(22, 22),
            on_click=self._on_send_btn_clicked,
        )
        composer_layout.addWidget(input_top)

        divider = QWidget(self._input_container)
        divider.setObjectName("composerDivider")
        divider.setFixedHeight(1)
        composer_layout.addWidget(divider)

        # ---- Dock bar ----
        secondary_bar = QWidget(self._input_container)
        secondary_bar.setObjectName("secondaryToolbar")
        sl = QHBoxLayout(secondary_bar)
        sl.setContentsMargins(12, 4, 12, 4)
        sl.setSpacing(2)
        sl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        add_btn = IconActionButton(
            text="+",
            tooltip="添加上下文",
            object_name="secondaryBtn",
            button_size=(22, 22),
        )
        sl.addWidget(add_btn)

        at_btn = IconActionButton(
            text="@",
            tooltip="引用文件",
            object_name="secondaryBtn",
            button_size=(22, 22),
        )
        sl.addWidget(at_btn)

        self._context_separator = QLabel("|")
        self._context_separator.setObjectName("contextSeparator")
        self._context_separator.setVisible(False)
        sl.addWidget(self._context_separator)

        c = get_theme_colors()
        self._context_file_icon = render_svg_icon("file", QColor(c["fg"]), size=14)
        self._context_disabled_icon = render_svg_icon("eye-off", QColor(c["muted"]), size=14)
        self._context_attachment_btn = QPushButton("")
        self._context_attachment_btn.setObjectName("contextAttachmentBtn")
        self._context_attachment_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._context_attachment_btn.setIconSize(QSize(14, 14))
        self._context_attachment_btn.setCheckable(True)
        self._context_attachment_btn.setChecked(True)
        self._context_attachment_btn.setVisible(False)
        self._context_attachment_btn.clicked.connect(self._on_context_attachment_toggled)
        sl.addWidget(self._context_attachment_btn)

        sl.addStretch()

        self._secondary_status = QLabel("")
        self._secondary_status.setObjectName("secondaryStatus")
        sl.addWidget(self._secondary_status)
        sl.addWidget(self._send_btn)

        composer_layout.addWidget(secondary_bar)
        composer_host_layout.addWidget(self._input_container, 1)
        self._composer_host.installEventFilter(self)
        self._input_container.installEventFilter(self)
        layout.addWidget(self._composer_host)
        self._composer_bottom_gap = QWidget(self)
        self._composer_bottom_gap.setObjectName("composerBottomGap")
        self._composer_bottom_gap.setFixedHeight(0)
        layout.addWidget(self._composer_bottom_gap)
        self._layout = layout
        self._reflow_composer(stick_if_bottom=False, defer_once=False)

    def _setup_header_icons(self) -> None:
        c = get_theme_colors()
        icon_color = QColor(c["fg"])
        self._history_btn.setIcon(render_svg_icon("history", icon_color, size=16))

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
        # Measure visible header widgets directly to avoid clipping by stale metrics.
        widgets = [self._icon_label]
        if self._agent_selector is not None and self._agent_selector.isVisible():
            widgets.append(self._agent_selector)
        elif self._title_label.isVisible():
            widgets.append(self._title_label)
        widgets.extend([self._status_label, self._new_conv_btn, self._history_btn])

        spacing = self._header_layout.spacing() if hasattr(self, "_header_layout") else 8
        margins = self._header_layout.contentsMargins() if hasattr(self, "_header_layout") else None
        margin_total = (margins.left() + margins.right()) if margins else 32
        content_width = sum(w.sizeHint().width() for w in widgets)
        gap_count = max(0, len(widgets) - 1)
        header_min_width = margin_total + content_width + (gap_count * spacing) + 24
        min_width = max(header_min_width, self._content_minimum_width())
        self.setMinimumWidth(min_width)
        self._reflow_composer(stick_if_bottom=False, defer_once=False)

    def _content_minimum_width(self) -> int:
        width = 0
        for row in self._messages_area.get_message_rows():
            hint_fn = getattr(row, "context_chip_panel_width_hint", None)
            if callable(hint_fn):
                width = max(width, int(hint_fn()))
        return width

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow_composer(stick_if_bottom=True, defer_once=True)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Initial splitter/layout negotiation can leave an outdated minimum width
        # until first maximize/restore; refresh once when panel is shown.
        QTimer.singleShot(0, self._update_width)
        QTimer.singleShot(0, lambda: self._reflow_composer(stick_if_bottom=False, defer_once=False))

    def _sync_composer_gap(self) -> None:
        """Keep bottom gap height equal to horizontal gutter width around composer."""
        if not hasattr(self, "_composer_bottom_gap"):
            return
        left, _right = self._composer_anchor_bounds()
        side_gap = max(0, int(left))
        if self._composer_bottom_gap.height() != side_gap:
            self._composer_bottom_gap.setFixedHeight(side_gap)

    def _sync_messages_bottom_inset(self) -> None:
        """Prevent composer/fade from covering the last message rows."""
        if not hasattr(self, "_messages_area") or not hasattr(self, "_composer_host"):
            return
        messages_rect = self._messages_area.geometry()
        composer_rect = self._composer_host.geometry()
        overlap = max(0, messages_rect.bottom() - composer_rect.top() + 1)
        # Reserve space only for the composer body. The fade should sit on top of
        # live message content, otherwise the gradient becomes a flat dark band.
        self._messages_area.setViewportMargins(0, 0, 0, overlap)

    def _update_composer_fade_geometry(self) -> None:
        if (
            not hasattr(self, "_composer_top_fade")
            or not hasattr(self, "_composer_host")
            or not hasattr(self, "_input_container")
        ):
            return
        fade_h = self._composer_top_fade.height()
        input_top_left = self._input_container.mapTo(self, QPoint(0, 0))
        self._composer_top_fade.setGeometry(
            input_top_left.x(),
            max(0, input_top_left.y() - fade_h),
            self._input_container.width(),
            fade_h,
        )
        self._composer_top_fade.raise_()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj in (getattr(self, "_input_container", None), getattr(self, "_composer_host", None)):
            if event.type() in (
                QEvent.Type.Move,
                QEvent.Type.Resize,
                QEvent.Type.Show,
                QEvent.Type.LayoutRequest,
            ):
                self._update_composer_fade_geometry()
        return super().eventFilter(obj, event)

    def _on_input_height_changed(self, _height: int) -> None:
        """Keep message viewport bottom-anchored when composer grows/shrinks."""
        self._reflow_composer(stick_if_bottom=True, defer_once=True)

    def _composer_anchor_bounds(self) -> tuple[int, int]:
        """Return (left, right) anchor x positions for composer in panel coordinates."""
        panel_w = max(1, self.width())
        left = self._composer_horizontal_margin
        if hasattr(self, "_icon_label") and self._icon_label is not None:
            left = self._icon_label.mapTo(self, QPoint(0, 0)).x()

        min_width = 220
        max_right = panel_w - self._composer_horizontal_margin
        right = max_right
        right = min(max_right, max(right, left + min_width))
        left = max(0, left)
        return left, right

    def _update_composer_alignment(self) -> None:
        """Align composer to avatar-left and current panel width."""
        if not hasattr(self, "_composer_host_layout"):
            return
        left, right = self._composer_anchor_bounds()
        right_gap = max(0, self.width() - right)
        margins = self._composer_host_layout.contentsMargins()
        if margins.left() != left or margins.right() != right_gap:
            self._composer_host_layout.setContentsMargins(left, 0, right_gap, 0)

    def _reflow_composer(self, *, stick_if_bottom: bool, defer_once: bool) -> None:
        """Apply composer alignment, gap and fade updates in a single transaction."""
        was_near_bottom = self._messages_area.is_near_bottom() if stick_if_bottom else False
        self._update_composer_alignment()
        self._messages_area.refresh_layout_for_width_change()
        self._sync_composer_gap()
        self._update_composer_fade_geometry()
        self._sync_messages_bottom_inset()
        self._composer_host.raise_()
        self._composer_bottom_gap.raise_()
        self._composer_top_fade.raise_()
        if stick_if_bottom:
            self._messages_area.stick_to_bottom_if_tracking(was_near_bottom)
        if defer_once:
            QTimer.singleShot(0, lambda: self._reflow_composer(stick_if_bottom=stick_if_bottom, defer_once=False))

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

        # Run search via persistent single-worker pool; discard stale completions.
        self._file_search_ticket += 1
        ticket = self._file_search_ticket
        future = self._file_search_executor.submit(self._file_search_manager._do_search, query)
        future.add_done_callback(lambda f: QTimer.singleShot(0, lambda: self._apply_file_search_result(ticket, f)))

    def _apply_file_search_result(self, ticket: int, future) -> None:
        if ticket != self._file_search_ticket:
            return
        try:
            matches = future.result()
        except Exception:
            matches = []
        if self._file_search_popup and self._file_search_popup.isVisible():
            self._file_search_popup.set_matches(matches)

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
        """Handle edit saved from a user message: retract and resend immediately."""
        self._messages_area.retract_from_row(row)
        self._pending_tool_groups.clear()
        self._current_tool_group = None
        self._send_content(content)

    def _on_message_edit_cancelled(self) -> None:
        """Handle edit cancelled - just reset state."""
        pass

    def closeEvent(self, event) -> None:  # noqa: N802
        self._file_search_manager.close()
        self._file_search_executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

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
        c = get_theme_colors()

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
        self._cmd_popup.setStyleSheet(f"""
            QListWidget {{
                background-color: {c["bg"]};
                border: 1px solid {c["border"]};
                border-radius: {c["radius_md"]};
                outline: none;
                padding: 2px;
                color: {c["popup_fg"]};
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-radius: {c["radius_sm"]};
            }}
            QListWidget::item:hover {{
                background-color: {c["popup_hover"]};
            }}
            QListWidget::item:selected {{
                background-color: {c["tree_sel_bg"]};
                color: {c["tree_sel_fg"]};
            }}
        """)
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
        self._set_context_attachment(Path(file_path).name, file_path)

    def set_preview_context(self, file_path: str, selected_text: str, start_line: int, end_line: int) -> None:
        self._preview_context = (file_path, selected_text, start_line, end_line)
        self._opened_file = None
        self._context_enabled = True
        lines = end_line - start_line + 1
        label = f"{lines} line{'s' if lines > 1 else ''} selected"
        self._set_context_attachment(label, file_path)

    def clear_file_context(self) -> None:
        """Clear attached file/selection context so next message won't include it."""
        self._opened_file = None
        self._preview_context = None
        self._context_separator.setVisible(False)
        self._context_attachment_btn.setVisible(False)

    def _set_context_attachment(self, label: str, tooltip_path: str) -> None:
        self._context_attachment_btn.setChecked(True)
        self._context_attachment_btn.setText(label)
        self._context_attachment_btn.setToolTip(tooltip_path)
        self._context_attachment_btn.setIcon(self._context_file_icon)
        self._context_separator.setVisible(True)
        self._context_attachment_btn.setVisible(True)
        self._sync_context_attachment_width()
        self._reflow_composer(stick_if_bottom=True, defer_once=True)

    def _sync_context_attachment_width(self) -> None:
        """Recompute attachment chip width so pasted/long labels expand immediately."""
        btn = self._context_attachment_btn
        text_w = btn.fontMetrics().horizontalAdvance(btn.text() or "")
        icon_w = btn.iconSize().width() if not btn.icon().isNull() else 0
        style = btn.style()
        frame = style.pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, None, btn) * 2
        left_pad = 6
        right_pad = 6
        icon_gap = 6 if icon_w else 0
        min_w = text_w + icon_w + icon_gap + left_pad + right_pad + frame
        btn.setMinimumWidth(max(0, min_w))
        btn.adjustSize()

    def _on_context_attachment_toggled(self) -> None:
        self._context_enabled = self._context_attachment_btn.isChecked()
        icon = self._context_file_icon if self._context_enabled else self._context_disabled_icon
        self._context_attachment_btn.setIcon(icon)
        self._sync_context_attachment_width()
        self._reflow_composer(stick_if_bottom=True, defer_once=True)

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
        if self._agent_selector is not None:
            idx = self._agent_selector.findData(agent_type)
            if idx >= 0 and idx != self._agent_selector.currentIndex():
                self._agent_selector.blockSignals(True)
                self._agent_selector.setCurrentIndex(idx)
                self._agent_selector.blockSignals(False)

    @property
    def agent_type(self) -> str:
        return self._agent_type

    def _on_agent_selector_changed(self, index: int) -> None:
        if self._agent_selector is None or index < 0:
            return
        agent_type = str(self._agent_selector.currentData() or "")
        if not agent_type or agent_type == self._agent_type:
            return
        self.agent_type_changed.emit(agent_type)

    # ---- Messages ----

    def add_message(
        self,
        role: str,
        content: str,
        source: str = "user",
        coordination: bool = False,
        streaming: bool = False,
        display_mode: str | None = None,
        bubble_title: str | None = None,
        bubble_align: str | None = None,
        bubble_on_timeline: bool = False,
        bubble_collapsible: bool = True,
        allow_edit: bool | None = None,
    ) -> None:
        resolved_display_mode = display_mode or ("bubble" if role == "user" else "agent_markdown")
        resolved_bubble_align = bubble_align or ("right" if role == "user" else "left")

        if streaming and role == "agent" and not content:
            return

        if role == "agent" and resolved_display_mode == "agent_markdown":
            last = self._messages_area.last_timeline_widget()
            if (
                getattr(last, "_role", "") == "agent"
                and getattr(last, "_display_mode", "") == "agent_markdown"
                and not getattr(last, "_complete", True)
            ):
                if streaming:
                    last.append_content(content)
                    self._current_tool_group = None
                    if streaming:
                        self._messages_area.follow_streaming_if_enabled()
                    return

        ts = datetime.now().strftime("%H:%M")
        agent_name = self._title_label.text() or "Agent"
        row = self._messages_area.add_message_row(
            role=role,
            content=content,
            timestamp=ts,
            is_coordination=coordination,
            display_mode=resolved_display_mode,
            bubble_align=resolved_bubble_align,
            bubble_title=bubble_title,
            bubble_on_timeline=bubble_on_timeline,
            bubble_collapsible=bubble_collapsible,
            allow_edit=allow_edit,
            agent_name=agent_name,
        )
        self._update_width()
        if streaming and role == "agent":
            row._complete = False
        if role == "agent" and resolved_display_mode == "agent_markdown":
            self._current_tool_group = None
        self._update_composer_alignment()

    def add_tool_call(
        self,
        tool_name: str,
        arguments: dict,
        summary: str | None = None,
        detail: str | None = None,
        expandable: bool = True,
    ) -> None:
        # Tool calls signal the end of thinking/streaming
        self.finish_thinking()

        last = self._messages_area.last_timeline_widget()
        if (
            getattr(last, "_role", "") == "agent"
            and getattr(last, "_display_mode", "") == "agent_markdown"
            and not getattr(last, "_complete", True)
        ):
            last.mark_complete()
        self._current_tool_group = self._messages_area.add_tool_group()
        self._pending_tool_groups.append(self._current_tool_group)
        self._current_tool_group.add_tool_call(
            name=tool_name,
            arguments=arguments,
            success=None,
            duration_ms=0,
            summary=summary,
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
            )

    def start_thinking(self) -> None:
        if self._thinking_row is not None:
            return
        self._thinking_started_at = time.monotonic()
        self._thinking_detail = ""
        ts = datetime.now().strftime("%H:%M")
        agent_name = self._title_label.text() or "Agent"
        self._thinking_row = self._messages_area.add_message_row(
            role="agent",
            content="",
            timestamp=ts,
            display_mode="thought",
            bubble_title="Thought for 1s",
            bubble_collapsible=True,
            agent_name=agent_name,
        )
        self._thinking_row._complete = False
        self._thinking_row.set_thinking_row_style(True)
        self._thinking_timer.start()
        self._update_composer_alignment()

    def append_thinking(self, thinking: str) -> None:
        self.start_thinking()
        if self._thinking_row is None:
            return
        if thinking:
            self._thinking_detail = self._merge_thinking_chunk(self._thinking_detail, thinking)
        self._thinking_row.set_bubble_content(self._thinking_detail)
        self._messages_area.follow_streaming_if_enabled()

    @staticmethod
    def _merge_thinking_chunk(current: str, chunk: str) -> str:
        if not current:
            return chunk
        if chunk.startswith(current):
            return chunk
        if current.endswith(chunk):
            return current
        max_overlap = min(len(current), len(chunk))
        for size in range(max_overlap, 0, -1):
            if current[-size:] == chunk[:size]:
                return current + chunk[size:]
        return current + chunk

    def finish_thinking(self) -> None:
        if self._thinking_row is None:
            return
        row = self._thinking_row
        elapsed = self._thinking_elapsed_seconds()
        summary = f"Thought for {elapsed}s"
        detail = (self._thinking_detail or "").strip()
        # Always complete the thinking row, even if empty
        # This preserves timeline order and prevents spacing issues
        row.set_bubble_title(summary)
        row.mark_complete()
        if detail:
            self.thinking_finished.emit(summary, detail, True)
        self._thinking_row = None
        self._thinking_started_at = None
        self._thinking_detail = ""
        self._thinking_timer.stop()

    def _thinking_elapsed_seconds(self) -> int:
        if self._thinking_started_at is None:
            return 0
        return max(1, int(time.monotonic() - self._thinking_started_at))

    def _update_thinking_timer(self) -> None:
        if self._thinking_row is None:
            self._thinking_timer.stop()
            return
        self._thinking_row.set_bubble_title(f"Thought for {self._thinking_elapsed_seconds()}s")

    def add_error(self, source: str, message: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role="agent",
            content=f"✗ {source}: {message}",
            timestamp=ts,
        )

    def add_checkpoint(self, checkpoint_id: str, description: str) -> None:
        # Hide internal pre-message sentinel checkpoints from UI.
        if (description or "").strip().lower().startswith("pre:"):
            self._messages_area.attach_checkpoint_to_latest_outbound(checkpoint_id)
            return
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
        am_source = self._agent_type == source
        am_target = self._agent_type == target

        summary = str(brief or "").strip() or "task"
        target_badge = get_agent_badge(target)
        source_badge = get_agent_badge(source)

        status_text = {
            "created": "○ 完成任务",
            "started": "● 进行中",
            "completed": "✓ 已完成",
            "cancelled": "✗ 已取消",
            "failed": "⚠ 失败",
        }

        if action in ("created", "started"):
            if am_source:
                text = f"⏳ 等待{target_badge}: {summary}"
            elif am_target:
                text = f"📋 {status_text[action]}：{summary}"
            else:
                text = f"📋 {status_text[action]}：{summary}"

        elif action == "completed":
            if am_target:
                text = f"📋 {status_text[action]}：{summary}"
            else:
                text = f"✅ {source_badge} 完成了任务：{summary}"

        elif action == "failed":
            if am_target:
                text = f"📋 {status_text[action]}：{summary}"
            else:
                text = f"⚠ {source_badge} 任务失败：{summary}"

        elif action == "cancelled":
            if am_target:
                text = f"📋 {status_text[action]}：{summary}"
            else:
                text = f"✗ {source_badge} 任务已取消：{summary}"

        else:
            text = f"任务更新 {action}: {summary}"

        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role="agent",
            content=text,
            timestamp=ts,
            is_coordination=True,
        )

    def add_task_block(self, todolist: list[dict], waitlist: list[dict]) -> None:
        """Render full Task block with Todo/Wait sections."""
        lines = ["Task", "", "Todo"]
        if todolist:
            for item in todolist[:10]:
                brief = str(item.get("brief", "")).strip() or "task"
                status = str(item.get("status", "pending")).lower()
                done = status in {"completed", "cancelled", "failed"}
                marker = "☑" if done else "☐"
                lines.append(f"- {marker} {brief}")
        else:
            lines.append("- —")

        lines.append("")
        lines.append("Wait")
        if waitlist:
            for item in waitlist[:10]:
                brief = str(item.get("brief", "")).strip() or "task"
                status = str(item.get("status", "pending")).lower()
                done = status in {"completed", "cancelled", "failed"}
                marker = "☑" if done else "☐"
                lines.append(f"- {marker} {brief}")
        else:
            lines.append("- —")

        ts = datetime.now().strftime("%H:%M")
        self._messages_area.add_message_row(
            role="agent",
            content="\n".join(lines),
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
            "idle": ("Idle", False, "status_idle"),
            "thinking": ("Thinking", True, "status_think"),
            "running_tool": ("Tool", True, "status_tool"),
            "error": ("Error", False, "status_error"),
            "debug_mode": ("Debug", False, "status_debug"),
        }
        label, active, color_key = status_map.get(
            status,
            (status.replace("_", " ").title(), False, "status_idle"),
        )
        self._status_label.setText(label)
        colors = get_theme_colors()
        self._status_label.setStyleSheet(f"color: {colors.get(color_key, colors['status_idle'])};")

        # Thinking rows should be driven by real thinking chunks from model
        # responses. Status events may arrive out-of-order and create phantom
        # thought rows if they start thinking UI directly.
        if status != "thinking":
            self.finish_thinking()

        if active:
            self._set_working(True)
        else:
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

        self._input_field.clear_text()
        self._send_content(content)

    def _send_content(self, content: str) -> None:
        """Send user message content (with file context if available)."""
        # Build file context info
        file_context = None
        if self._context_enabled:
            if self._preview_context:
                fp, text, s, e = self._preview_context
                file_context = {
                    "type": "selection",
                    "file": fp,
                    "start_line": s,
                    "end_line": e,
                    "content": text
                }
            elif self._opened_file:
                file_context = {
                    "type": "file",
                    "file": self._opened_file
                }

        ui_logger.debug("AgentPanel[{}]: sending message ({} chars)", self.panel_id, len(content))
        self._set_working(True)
        # CRITICAL: Emit file context signal BEFORE user message signal
        # This ensures MainWindow caches the context before processing the user message
        if file_context:
            self.file_context_attached.emit(file_context)
        self.message_sent.emit(content)

        # Clear context state (after use)
        self._preview_context = None
        self._opened_file = None
        self._context_separator.setVisible(False)
        self._context_attachment_btn.setVisible(False)

    def _on_send_btn_clicked(self) -> None:
        """Handle send button click — send or interrupt based on state."""
        if self._is_working:
            self.interrupt_requested.emit()
        else:
            self._on_send()

    def _on_history(self) -> None:
        ui_logger.debug("AgentPanel[{}]: history button clicked", self.panel_id)
        if self._history_dropdown.isVisible() or self._history_show_pending:
            self._history_show_pending = False
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
        self._history_show_pending = True
        QTimer.singleShot(0, self._show_history_dropdown_now)

    def _show_history_dropdown_now(self) -> None:
        if not self._history_show_pending:
            return
        self._history_show_pending = False
        self._history_dropdown.show_dropdown(self._history_btn)

    def _on_history_session_selected(self, session_id: str) -> None:
        self.session_selected_from_dropdown.emit(session_id)

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
        self._update_width()
        self._update_composer_alignment()
        self._pending_tool_groups.clear()
        self._current_tool_group = None
        self.conversation_cleared.emit()
