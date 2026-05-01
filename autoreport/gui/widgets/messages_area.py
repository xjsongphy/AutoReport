"""Scrollable messages area container for chat display."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from .message_row import MessageRow
from .tool_call_group import ToolCallGroup


class MessagesArea(QScrollArea):
    """Scrollable container for chat messages with auto-scroll management.

    Features:
    - Auto-scroll to bottom when new messages are added
    - Detect user scroll (pause auto-scroll)
    - add_message_row() and add_tool_group() methods
    - Query methods for testing
    """

    def __init__(self, parent: QWidget | None = None):
        """Initialize messages area.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._auto_scroll_enabled = True
        self._user_scrolled = False

        self._setup_ui()
        self._connect_scroll_signals()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        # Container widget for all messages
        self._container = QWidget()
        self._container.setObjectName("messagesContainer")

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch()  # Push content to top

        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Minimal styling
        self.setObjectName("messagesArea")
        self.setStyleSheet("""
            QScrollArea#messagesArea {
                border: none;
                background-color: transparent;
            }
            QWidget#messagesContainer {
                background-color: transparent;
            }
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
    ) -> MessageRow:
        """Add a message row to the container.

        Args:
            role: Message role ("user" or "agent").
            content: Message content.
            timestamp: Time in HH:MM format.
            is_coordination: Whether this is a coordination message.

        Returns:
            The created MessageRow widget.
        """
        # Create row without parent to avoid thread issues
        # Qt will handle parent-child when added to layout
        row = MessageRow(
            role=role,
            content=content,
            timestamp=timestamp,
            is_coordination=is_coordination,
            parent=None,  # Let layout handle parent
        )

        # Find the stretch item and insert before it
        stretch_index = self._layout.count() - 1
        self._layout.insertWidget(stretch_index, row)

        # Auto-scroll if enabled
        if self._auto_scroll_enabled:
            self.scroll_to_bottom()

        return row

    def add_tool_group(self) -> ToolCallGroup:
        """Add a tool call group to the container.

        Returns:
            The created ToolCallGroup widget.
        """
        # Insert before the stretch spacer
        group = ToolCallGroup(parent=self._container)

        # Find the stretch item and insert before it
        stretch_index = self._layout.count() - 1
        self._layout.insertWidget(stretch_index, group)

        # Auto-scroll if enabled
        if self._auto_scroll_enabled:
            self.scroll_to_bottom()

        return group

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the messages area."""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear(self) -> None:
        """Remove all messages from the container."""
        # Remove all widgets except the stretch spacer
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

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
