"""Form selector dropdown component - unified replacement for QComboBox.

This component provides a consistent dropdown selector for form inputs,
with the same styling and animations as other dropdown components in the app.

Usage:
    dropdown = FormSelectorDropdown()
    dropdown.add_item("value1", "Display Label 1")
    dropdown.add_item("value2", "Display Label 2")
    dropdown.set_current_value("value1")
    dropdown.value_changed.connect(callback)
"""

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..theme import get_theme_colors
from .base_popup_dropdown import BasePopupDropdown
from .ui_utils import input_button_qss


class _SelectorButton(QPushButton):
    """Button that triggers the dropdown and displays current selection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("selectorButton")
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        """Paint button with chevron indicator."""
        from PyQt6.QtGui import QPainter, QPainterPath, QPen, QColor
        from PyQt6.QtCore import QPointF

        super().paintEvent(event)

        # Draw chevron on the right side
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get theme color
        c = get_theme_colors()
        color = QColor(c["muted"])

        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        # Draw chevron
        x = self.width() - 14
        y = self.height() // 2
        path = QPainterPath()
        path.moveTo(x - 4, y - 2)
        path.lineTo(x, y + 2)
        path.lineTo(x + 4, y - 2)
        painter.drawPath(path)

        painter.end()


class FormSelectorDropdown(QWidget):
    """Form selector dropdown with unified styling.

    A replacement for QComboBox with consistent appearance and animations.

    Signals:
        value_changed: Emitted when selection changes (new_value)
    """

    value_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        """Initialize the form selector dropdown."""
        super().__init__(parent)
        self._items = []  # List of (value, label) tuples
        self._current_value = None

        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self) -> None:
        """Setup UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create the popup dropdown
        self._popup = BasePopupDropdown()
        self._popup.item_activated.connect(self._on_item_selected)
        self._popup.cancelled.connect(self._on_popup_cancelled)

        # Create the selector button
        self._button = _SelectorButton()
        self._button.clicked.connect(self._show_dropdown)
        layout.addWidget(self._button)

        # Install event filter to detect clicks outside
        self._popup.installEventFilter(self)

    def _apply_theme(self) -> None:
        """Apply theme styling."""
        c = get_theme_colors()

        self._button.setStyleSheet(
            input_button_qss(
                "#selectorButton",
                padding="4px 24px 4px 8px",
                font_size=12,
                radius=c["radius_sm"],
            )
        )

    # ---- Public API ----

    def add_item(self, value: object, label: str) -> None:
        """Add an item to the dropdown.

        Args:
            value: The value associated with this item
            label: Display label for the item
        """
        self._items.append((value, label))

        # Add to popup
        from PyQt6.QtWidgets import QListWidgetItem
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, value)
        self._popup.addItem(item)

        # Update button if this is the first item
        if len(self._items) == 1:
            self.set_current_value(value)

    def set_current_value(self, value: object) -> None:
        """Set the current value.

        Args:
            value: The value to select
        """
        self._current_value = value

        # Find and display the label
        for val, label in self._items:
            if val == value:
                self._button.setText(label)
                break

    def current_value(self) -> object:
        """Get the current value."""
        return self._current_value

    def clear(self) -> None:
        """Clear all items."""
        self._items.clear()
        self._popup.clear()
        self._button.setText("")
        self._current_value = None

    def count(self) -> int:
        """Return the number of items."""
        return len(self._items)

    # ---- Internal Methods ----

    def _show_dropdown(self) -> None:
        """Show the dropdown popup below the button."""
        # Populate items (in case they were cleared)
        self._popup.clear()
        for value, label in self._items:
            from PyQt6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, value)
            self._popup.addItem(item)

        # Position and show
        self._popup.show_dropdown(self._button)

    def _on_item_selected(self, item) -> None:
        """Handle item selection from dropdown.

        Args:
            item: The QListWidgetItem that was selected
        """
        value = item.data(Qt.ItemDataRole.UserRole)
        self.set_current_value(value)
        self.value_changed.emit(value)

    def _on_popup_cancelled(self) -> None:
        """Handle popup cancellation (Escape key)."""
        self._button.setFocus()

    # ---- Keyboard Support ----

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Handle keyboard shortcuts."""
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_F4):
            # Show dropdown
            self._show_dropdown()
        else:
            super().keyPressEvent(event)
