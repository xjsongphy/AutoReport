"""Base popup dropdown component with unified styling.

This provides a consistent foundation for all dropdown/popover UI elements
in the application, including:
- Conversation history dropdown
- File search popup
- Command palette
- Form selector dropdowns (QComboBox replacement)

Features:
- Unified dark/light theme styling
- Popup window with frameless hint
- Click-outside-to-hide behavior
- Keyboard navigation support
- No selection highlight (text field shows current selection)
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QListWidget, QWidget


class BasePopupDropdown(QListWidget):
    """Base dropdown component with unified styling and fade animations.

    All custom dropdowns should inherit from this class to ensure
    consistent appearance and behavior across the application.
    """

    # Signals for subclasses to emit
    item_activated = pyqtSignal(object)  # Emitted when an item is selected
    cancelled = pyqtSignal()  # Emitted when dropdown is cancelled

    # Default sizes
    DEFAULT_WIDTH = 320
    MAX_HEIGHT = 300

    def __init__(self, parent: QWidget | None = None):
        """Initialize the base dropdown.

        Args:
            parent: Parent widget (typically None for popup windows)
        """
        super().__init__(parent)
        self.setObjectName("basePopupDropdown")

        # Setup as a popup window
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Initially hidden
        self.setVisible(False)

        # Setup UI
        self._setup_base_ui()
        self._apply_theme()

    def _setup_base_ui(self) -> None:
        """Setup base UI components common to all dropdowns."""
        # Disable horizontal scrollbar
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Set default size
        self.setFixedWidth(self.DEFAULT_WIDTH)
        self.setMaximumHeight(self.MAX_HEIGHT)

        # Connect base signals
        self.itemClicked.connect(self._on_item_clicked)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _apply_theme(self) -> None:
        """Apply unified theme styling."""
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        # Theme colors
        bg = "#1f1f1f" if dark else "#ffffff"
        border = "#2b2b2b" if dark else "#e0e0e0"
        fg = "#cccccc" if dark else "#333333"
        hover = "#2a2d2e" if dark else "#f5f5f5"

        self.setStyleSheet(f"""
            QListWidget#{self.objectName()} {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
                outline: none;
                padding: 2px;
            }}
            QListWidget#{self.objectName()}::item {{
                border-radius: 4px;
                margin: 1px 4px;
                padding: 6px 8px;
                color: {fg};
            }}
            QListWidget#{self.objectName()}::item:hover {{
                background-color: {hover};
            }}
            QListWidget#{self.objectName()}::item:selected {{
                background-color: transparent;
                color: {fg};
            }}
        """)

    # ---- Show/Hide Methods ----

    def show_dropdown(self, parent_widget: QWidget | None = None) -> None:
        """Show the dropdown.

        Args:
            parent_widget: Widget to position below (if None, uses current position)
        """
        if parent_widget:
            # Position below parent widget
            from PyQt6.QtCore import QPoint
            global_pos = parent_widget.mapToGlobal(QPoint(0, parent_widget.height()))
            self.move(global_pos)

        self.setVisible(True)
        self.raise_()
        self.setFocus()

    def hide(self) -> None:
        """Hide the dropdown."""
        super().hide()

    # ---- Item Selection ----

    def _on_item_clicked(self, item) -> None:
        """Handle item click - emit signal and hide."""
        self.item_activated.emit(item)
        self.hide()

    def _on_item_double_clicked(self, item) -> None:
        """Handle item double click - emit signal and hide."""
        self.item_activated.emit(item)
        self.hide()

    # ---- Keyboard Navigation ----

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Handle keyboard shortcuts."""
        from PyQt6.QtGui import QKeyEvent

        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            # Activate current item
            current = self.currentItem()
            if current:
                self.item_activated.emit(current)
            self.hide()
        elif event.key() == Qt.Key.Key_Escape:
            # Cancel
            self.cancelled.emit()
            self.hide()
        else:
            super().keyPressEvent(event)
