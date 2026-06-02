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

from PyQt6.QtCore import QEvent, QPoint, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainterPath, QPalette, QRegion
from PyQt6.QtWidgets import QApplication, QAbstractItemView, QFrame, QListWidget, QWidget

from ..theme import get_theme_colors


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
    DEFAULT_MAX_VISIBLE_ITEMS = 8
    DEFAULT_ROW_HEIGHT = 30

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        max_visible_items: int = DEFAULT_MAX_VISIBLE_ITEMS,
    ):
        """Initialize the base dropdown.

        Args:
            parent: Parent widget (typically None for popup windows)
        """
        super().__init__(parent)
        self.setObjectName("basePopupDropdown")
        self._max_visible_items = max(1, int(max_visible_items))
        self._anchor_widget: QWidget | None = None
        self._popup_border_width = 1
        self._popup_radius = 6

        # Popup semantics match combo-box dropdowns; do not use Tool here,
        # otherwise the history list behaves like an independent window.
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(False)
        self._event_filter_installed = False

        # Initially hidden
        self.setVisible(False)

        # Setup UI
        self._setup_base_ui()
        self._apply_theme()

    def _setup_base_ui(self) -> None:
        """Setup base UI components common to all dropdowns."""
        # Disable horizontal scrollbar
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setContentsMargins(0, 0, 0, 0)
        self.setMouseTracking(True)
        self.viewport().setObjectName("basePopupDropdownViewport")
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.viewport().setAutoFillBackground(True)
        self.viewport().setMouseTracking(True)
        self.verticalScrollBar().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.verticalScrollBar().setAutoFillBackground(False)

        # Set default size
        self.setFixedWidth(self.DEFAULT_WIDTH)
        self.setMaximumHeight(self.MAX_HEIGHT)

        # Connect base signals
        self.itemClicked.connect(self._on_item_clicked)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _apply_theme(self) -> None:
        """Apply popup-list styling copied from the API combo popup.

        Keep this implementation local to custom dropdowns. Do not call into
        NoWheelComboBox or mutate API config combo styles from here.
        """
        c = get_theme_colors()
        radius = c.get("radius_md", "6px")
        item_radius = c.get("radius_sm", "4px")
        border_color = c.get("input_border", c["border"])
        border_width = c.get("input_border_width", "1px")
        row_height = self.DEFAULT_ROW_HEIGHT
        bg = c["bg"]
        self._popup_border_width = self._css_px_to_int(border_width, 1)
        self._popup_radius = self._css_px_to_int(radius, 6)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.transparent)
        palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.transparent)
        self.setPalette(palette)

        viewport_palette = self.viewport().palette()
        viewport_palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.transparent)
        viewport_palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.transparent)
        self.viewport().setPalette(viewport_palette)
        self.viewport().setStyleSheet(f"""
            QWidget#basePopupDropdownViewport {{
                background-color: {bg};
                border: none;
                border-radius: 0;
            }}
        """)

        self.setStyleSheet(f"""
            QListWidget#{self.objectName()} {{
                border: {border_width} solid {border_color};
                border-radius: {radius};
                background-color: {bg};
                color: {c["fg"]};
                outline: none;
                padding: 0;
            }}
            QListWidget#{self.objectName()}::viewport {{
                border: none;
                border-radius: 0;
                background-color: {bg};
                padding: 0;
            }}
            QListWidget#{self.objectName()}::item {{
                border: none;
                background: transparent;
                color: {c["fg"]};
                padding: 0 12px;
                margin: 0;
                min-height: {row_height}px;
                max-height: {row_height}px;
                border-radius: {item_radius};
            }}
            QListWidget#{self.objectName()}::item:selected {{
                background-color: {c["selectionBlue"]};
                color: {c["fg"]};
            }}
            QListWidget#{self.objectName()}::item:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}
            QListWidget#{self.objectName()}::item:selected:hover {{
                background-color: {c["selectionBlue"]};
                color: {c["fg"]};
                border-radius: {item_radius};
            }}
            QListWidget#{self.objectName()} QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 4px 2px 4px 0px;
                border: none;
                border-radius: 0;
            }}
            QListWidget#{self.objectName()} QScrollBar::handle:vertical {{
                background: {c["scrollbar"]};
                border: none;
                min-height: 28px;
                border-radius: {item_radius};
                margin: 2px 2px;
            }}
            QListWidget#{self.objectName()} QScrollBar::handle:vertical:hover {{
                background: {c["scrollbar_hover"]};
                border: none;
                border-radius: {item_radius};
            }}
            QListWidget#{self.objectName()} QScrollBar::add-line:vertical,
            QListWidget#{self.objectName()} QScrollBar::sub-line:vertical,
            QListWidget#{self.objectName()} QScrollBar::add-page:vertical,
            QListWidget#{self.objectName()} QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
                border-radius: 0;
                height: 0px;
            }}
        """)
        self._update_rounded_mask()

    @staticmethod
    def _css_px_to_int(value: str, fallback: int) -> int:
        try:
            return max(0, int(float(str(value).strip().removesuffix("px"))))
        except (TypeError, ValueError):
            return fallback

    def _update_rounded_mask(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._popup_radius, self._popup_radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_rounded_mask()

    # ---- Show/Hide Methods ----

    def set_max_visible_items(self, count: int) -> None:
        self._max_visible_items = max(1, int(count))

    def _apply_popup_height(self, max_visible_items: int | None = None) -> None:
        max_items = max(1, int(max_visible_items or self._max_visible_items))
        count = self.count()
        if count <= 0:
            return

        visible_rows = min(count, max_items)
        row_h = self.sizeHintForRow(0)
        if row_h <= 0:
            row_h = self.DEFAULT_ROW_HEIGHT
        frame = self.frameWidth() * 2
        spacing = max(0, self.spacing()) * max(0, visible_rows - 1)
        height = min(self.MAX_HEIGHT, (row_h * visible_rows) + spacing + frame + 2)
        self.setFixedHeight(max(row_h + frame + 2, height))
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if count > max_items
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def show_dropdown(
        self,
        parent_widget: QWidget | None = None,
        *,
        align: str = "left",
        y_offset: int = 0,
        max_visible_items: int | None = None,
    ) -> None:
        """Show the dropdown.

        Args:
            parent_widget: Widget to position below (if None, uses current position)
        """
        # Ensure first-open geometry uses final styled metrics.
        self.ensurePolished()
        self.updateGeometry()
        self._apply_popup_height(max_visible_items)
        self.updateGeometries()
        self.viewport().updateGeometry()

        if parent_widget:
            self._anchor_widget = parent_widget
            # First-open can race with pending layout updates, which may report
            # stale size/position and cause the popup to overlap its trigger.
            parent_widget.ensurePolished()
            parent_widget.updateGeometry()

            top_left = parent_widget.mapToGlobal(QPoint(0, 0))
            anchor_bottom = top_left.y() + parent_widget.height()
            if align == "right":
                x = top_left.x() + parent_widget.width() - self.width()
            else:
                x = top_left.x()
            y = anchor_bottom + y_offset

            screen = QApplication.screenAt(top_left)
            if screen is not None:
                avail = screen.availableGeometry()
                x = max(avail.left() + 8, min(x, avail.right() - self.width() - 8))
                if y + self.height() > avail.bottom() - 8:
                    y = max(
                        avail.top() + 8,
                        top_left.y() - self.height() - y_offset,
                    )
            self.move(x, y)

        self.setVisible(True)
        self.raise_()
        self.setFocus()

    def hide(self) -> None:
        """Hide the dropdown."""
        super().hide()
        self._remove_app_event_filter()
        if self._anchor_widget is not None:
            if hasattr(self._anchor_widget, "setDown"):
                self._anchor_widget.setDown(False)
            QApplication.sendEvent(self._anchor_widget, QEvent(QEvent.Type.Leave))
            self._anchor_widget.clearFocus()
            self._anchor_widget.repaint()
            self._anchor_widget.update()
            self._anchor_widget = None

    def _install_app_event_filter(self) -> None:
        if self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._event_filter_installed = True

    def _remove_app_event_filter(self) -> None:
        if not self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._event_filter_installed = False

    def eventFilter(self, obj, event):  # noqa: N802
        if self.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                global_pos = event.globalPos()
            if not self.geometry().contains(global_pos):
                self.hide()
                # Do not consume the click; let the underlying widget handle it.
                return False
        return super().eventFilter(obj, event)

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
