"""Scrollable messages area container for chat display."""

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ..theme import get_theme_colors
from .message_row import MessageRow
from .tool_call_group import ToolCallGroup


class MessagesArea(QScrollArea):
    """Scrollable container for chat messages with auto-scroll management.

    Features:
    - Auto-scroll to bottom when new messages are added
    - Detect user scroll (pause auto-scroll)
    - add_message_row() and add_tool_group() methods
    - Query methods for testing
    - Track latest user message for editing
    - Support in-place editing with message retraction
    """

    edit_requested = pyqtSignal(str)
    edit_saved = pyqtSignal(str, object)  # content, row_widget
    edit_cancelled = pyqtSignal()
    rollback_requested = pyqtSignal(str, object)  # checkpoint_id, row_widget

    def __init__(self, parent: QWidget | None = None):
        """Initialize messages area.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._auto_scroll_enabled = True
        self._user_scrolled = False
        self._latest_user_row: MessageRow | None = None
        self._editing_row: MessageRow | None = None

        self._setup_ui()
        self._connect_scroll_signals()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        # Container widget for all messages
        self._container = QWidget(self)
        self._container.setObjectName("messagesContainer")

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 8, 0, 4)
        self._layout.setSpacing(0)
        self._layout.addStretch()  # Push content to top

        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Minimal styling
        c = get_theme_colors()
        self.setObjectName("messagesArea")
        self.setStyleSheet(f"""
            QScrollArea#messagesArea {{
                border: none;
                background-color: {c["panel_bg"]};
            }}
            QWidget#messagesContainer {{
                background-color: {c["messages_bg"]};
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c["scrollbar"]};
                min-height: 30px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {c["scrollbar_hover"]};
            }}
            QScrollBar::handle:vertical:pressed {{
                background-color: {c["scrollbar_hover"]};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

    def _connect_scroll_signals(self) -> None:
        """Connect scroll bar signals to detect user scrolling."""
        scrollbar = self.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll_value_changed)

    def _on_scroll_value_changed(self, value: int) -> None:
        """Handle scroll value changes to detect user scroll.

        Args:
            value: New scroll bar value.
        """
        scrollbar = self.verticalScrollBar()
        max_value = scrollbar.maximum()

        # Calculate how far we are from the bottom
        distance_from_bottom = max_value - value

        # If user scrolls away from bottom (more than 10px threshold)
        # Also check if value is significantly less than what would be "at bottom"
        # This handles the case where max is small but we're clearly not at bottom
        if distance_from_bottom > 10:
            self._user_scrolled = True
            self._auto_scroll_enabled = False
        # If user scrolls to bottom (within 10px threshold)
        elif distance_from_bottom >= 0 and distance_from_bottom <= 10:
            self._user_scrolled = False
            self._auto_scroll_enabled = True
        # Edge case: if value > max, we're definitely not at bottom
        elif value > max_value:
            self._user_scrolled = True
            self._auto_scroll_enabled = False

    def _update_auto_scroll_state(self) -> None:
        """Update auto-scroll state based on current scroll position.

        This is called when we need to check the scroll position
        without waiting for the signal to fire.
        """
        scrollbar = self.verticalScrollBar()
        value = scrollbar.value()
        max_value = scrollbar.maximum()

        # If scrolled away from bottom (more than 10px threshold)
        if max_value - value > 10:
            self._auto_scroll_enabled = False
        else:
            self._auto_scroll_enabled = True

    def check_scroll_position(self) -> tuple:
        """Check current scroll position (for debugging).

        Returns:
            Tuple of (value, maximum, difference)
        """
        scrollbar = self.verticalScrollBar()
        value = scrollbar.value()
        max_value = scrollbar.maximum()
        return (value, max_value, max_value - value)

    def add_message_row(
        self,
        role: str,
        content: str,
        timestamp: str = "",
        is_coordination: bool = False,
        render_as_user_bubble: bool = False,
        agent_name: str = "Agent",
        summary: str | None = None,
        detail: str | None = None,
        expandable: bool = True,
    ) -> MessageRow:
        """Add a message row to the container."""
        row = MessageRow(
            role=role,
            content=content,
            timestamp=timestamp,
            is_coordination=is_coordination,
            render_as_user_bubble=render_as_user_bubble,
            agent_name=agent_name,
            summary=summary,
            detail=detail,
            expandable=expandable,
            agent_chain_prev=False,
            agent_chain_next=False,
            parent=self._container,
        )

        # Connect edit signals for user messages
        if role == "user":
            row.edit_requested.connect(self.edit_requested.emit)
            row.edit_saved.connect(self._on_edit_saved)
            row.edit_cancelled.connect(self._on_edit_cancelled)
        if role == "user" or render_as_user_bubble:
            row.rollback_requested.connect(self.rollback_requested.emit)

        # Handle editable state — only latest user message is editable
        if role == "user":
            # Make previous user message non-editable
            if self._latest_user_row:
                self._latest_user_row.set_editable(False)
            # This new message becomes editable
            self._latest_user_row = row
            row.set_editable(True)
            # User messages are immediately complete (non-streaming),
            # so hover toolbar and context actions should be available.
            row.mark_complete()
        else:
            # Non-user rows are added as complete messages, so hover actions
            # (e.g. agent copy button) should be available immediately.
            row.mark_complete()

        # Find the stretch item and insert before it
        stretch_index = self._layout.count() - 1
        self._layout.insertWidget(stretch_index, row)
        self._update_timeline_chains()

        # Auto-scroll if enabled
        if self._auto_scroll_enabled:
            self.scroll_to_bottom()

        return row

    def attach_checkpoint_to_latest_outbound(self, checkpoint_id: str) -> bool:
        for row in reversed(self.get_message_rows()):
            if not (getattr(row, "_role", "") == "user" or getattr(row, "_render_as_user_bubble", False)):
                continue
            if getattr(row, "_checkpoint_id", None):
                continue
            row.set_checkpoint_id(checkpoint_id)
            return True
        return False

    def add_tool_group(self) -> ToolCallGroup:
        """Add a tool call group to the container.

        Returns:
            The created ToolCallGroup.
        """
        # Insert before the stretch spacer
        group = ToolCallGroup(parent=self._container)

        # Find the stretch item and insert before it
        stretch_index = self._layout.count() - 1
        self._layout.insertWidget(stretch_index, group)
        self._update_timeline_chains()

        # Auto-scroll if enabled
        if self._auto_scroll_enabled:
            self.scroll_to_bottom()

        return group

    def _timeline_widgets(self) -> list[QWidget]:
        widgets: list[QWidget] = []
        for i in range(self._layout.count() - 1):
            item = self._layout.itemAt(i)
            if item and item.widget():
                widgets.append(item.widget())
        return widgets

    def last_timeline_widget(self) -> QWidget | None:
        widgets = self._timeline_widgets()
        return widgets[-1] if widgets else None

    def _is_chainable_timeline_item(self, widget: QWidget) -> bool:
        if isinstance(widget, ToolCallGroup):
            return True
        if isinstance(widget, MessageRow):
            return getattr(widget, "_role", "") == "agent" and not getattr(widget, "_render_as_user_bubble", False)
        return False

    def _set_widget_chain(self, widget: QWidget, prev_link: bool, next_link: bool) -> None:
        if isinstance(widget, MessageRow):
            widget.set_agent_chain(prev_link, next_link)
        elif isinstance(widget, ToolCallGroup):
            widget.set_timeline_chain(prev_link, next_link)

    def _update_timeline_chains(self) -> None:
        widgets = self._timeline_widgets()
        chainable = [self._is_chainable_timeline_item(widget) for widget in widgets]
        for i, widget in enumerate(widgets):
            if not chainable[i]:
                continue
            prev_link = i > 0 and chainable[i - 1]
            next_link = i + 1 < len(widgets) and chainable[i + 1]
            self._set_widget_chain(widget, prev_link, next_link)

    def add_task_row(self, text: str, row_type: str = "task_update") -> None:
        """Add a task-related message row (waitlist, todolist, notification).

        Args:
            text: Display text for the task row.
            row_type: "waitlist", "todolist", "task_update", or "task_summary".
        """
        row = MessageRow(
            role="system",
            content=text,
            timestamp="",
            is_coordination=True,
            parent=self._container,
        )

        # Find the stretch item and insert before it
        stretch_index = self._layout.count() - 1
        self._layout.insertWidget(stretch_index, row)
        self._update_timeline_chains()

        if self._auto_scroll_enabled:
            self.scroll_to_bottom()

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the messages area."""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def follow_streaming_if_enabled(self) -> None:
        """Keep following streaming output unless user has scrolled up."""
        self._update_auto_scroll_state()
        if not self._auto_scroll_enabled:
            return
        # Defer until layout/size updates from appended text are applied.
        QTimer.singleShot(0, self.scroll_to_bottom)

    def clear(self) -> None:
        """Remove all messages from the container."""
        # Remove all widgets except the stretch spacer
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Reset latest-user pointer to avoid accessing deleted row widgets.
        self._latest_user_row = None
        self._editing_row = None

    def _on_edit_saved(self, content: str, row: MessageRow) -> None:
        """Handle edit saved signal from a message row."""
        self._editing_row = row
        self.edit_saved.emit(content, row)

    def _on_edit_cancelled(self) -> None:
        """Handle edit cancelled signal from a message row."""
        self._editing_row = None
        self.edit_cancelled.emit()

    def remove_message_row(self, row: MessageRow) -> None:
        """Remove a specific message row from the container.

        Args:
            row: The MessageRow widget to remove.
        """
        # Find and remove the row
        for i in range(self._layout.count() - 1):  # Exclude stretch spacer
            item = self._layout.itemAt(i)
            if item and item.widget() == row:
                self._layout.removeWidget(row)
                row.deleteLater()
                # If this was the latest user row, reset it
                if row == self._latest_user_row:
                    self._latest_user_row = None
                # If this was the editing row, reset it
                if row == self._editing_row:
                    self._editing_row = None
                self._update_timeline_chains()
                break

        # Auto-scroll if enabled
        if self._auto_scroll_enabled:
            self.scroll_to_bottom()

    def retract_from_row(self, row: MessageRow) -> None:
        """Remove `row` and every following message/tool row."""
        start_index = -1
        for i in range(self._layout.count() - 1):  # Exclude stretch spacer
            item = self._layout.itemAt(i)
            if item and item.widget() == row:
                start_index = i
                break

        if start_index < 0:
            return

        for i in range(self._layout.count() - 2, start_index - 1, -1):
            item = self._layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            self._layout.removeWidget(widget)
            widget.deleteLater()

        self._latest_user_row = None
        self._editing_row = None
        rows = self.get_message_rows()
        for msg_row in reversed(rows):
            if msg_row._role == "user":
                self._latest_user_row = msg_row
                msg_row.set_editable(True)
                break
        self._update_timeline_chains()

        if self._auto_scroll_enabled:
            self.scroll_to_bottom()

    # ---- Query methods for testing ----

    def message_count(self) -> int:
        """Return the total number of message widgets.

        Returns:
            Count of MessageRow and ToolCallGroup widgets.
        """
        return self._layout.count() - 1  # Exclude stretch spacer

    def auto_scroll_enabled(self) -> bool:
        """Check if auto-scroll is enabled.

        Returns:
            True if auto-scroll is enabled.
        """
        return self._auto_scroll_enabled

    def vertical_scrollbar(self):
        """Get the vertical scrollbar for testing.

        Returns:
            The vertical QScrollBar.
        """
        self._update_auto_scroll_state()
        return self.verticalScrollBar()

    def is_scrollable(self) -> bool:
        """Check if the area is scrollable.

        Returns:
            True if scrollbars are enabled.
        """
        return self.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    def get_message_rows(self) -> list[MessageRow]:
        """Get all MessageRow widgets in the container.

        Returns:
            List of MessageRow widgets.
        """
        rows = []
        for i in range(self._layout.count() - 1):  # Exclude stretch spacer
            item = self._layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, MessageRow):
                    rows.append(widget)
        return rows

    def get_tool_groups(self) -> list[ToolCallGroup]:
        """Get all ToolCallGroup widgets in the container.

        Returns:
            List of ToolCallGroup widgets.
        """
        groups = []
        for i in range(self._layout.count() - 1):  # Exclude stretch spacer
            item = self._layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, ToolCallGroup):
                    groups.append(widget)
        return groups
