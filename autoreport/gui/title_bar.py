"""Custom title bar for frameless window - VSCode style."""

import sys
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QCursor, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMenuBar,
    QMenu,
    QVBoxLayout,
    QStyle,
    QStyleOptionTitleBar,
)

from .theme import get_theme_colors
from .scale import dpi_scale


class TitleBar(QWidget):
    """Custom title bar with menu and window controls.

    Features:
    - Integrated menu bar
    - Window drag support
    - System-native window controls (minimize/maximize/close)
    - Platform-specific styling (macOS/Windows)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_position = QPoint()
        self._is_macos = sys.platform == "darwin"
        self._is_windows = sys.platform == "win32"

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup title bar UI."""
        s = dpi_scale()
        self.setFixedHeight(int(40 * s))
        self.setObjectName("titleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Menu bar (left side)
        self._menu_bar = QMenuBar(self)
        self._menu_bar.setObjectName("titleBarMenuBar")

        # On macOS, native menu bar is preferred, but for custom title bar
        # we need to embed it
        layout.addWidget(self._menu_bar)

        layout.addStretch()

        # Window controls (right side)
        # On macOS, use system buttons (already in title bar)
        # On Windows/Linux, use custom buttons
        if not self._is_macos:
            self._controls_widget = QWidget(self)
            self._controls_widget.setObjectName("titleBarControls")
            controls_layout = QHBoxLayout(self._controls_widget)
            controls_layout.setContentsMargins(0, 0, int(8 * s), 0)
            controls_layout.setSpacing(0)

            # Minimize button - use standard icon
            self._minimize_btn = QPushButton()
            self._minimize_btn.setObjectName("titleBarMinimizeBtn")
            self._minimize_btn.setFixedSize(int(46 * s), int(40 * s))
            self._minimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._minimize_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMinButton))

            # Maximize/Restore button - use standard icon
            self._maximize_btn = QPushButton()
            self._maximize_btn.setObjectName("titleBarMaximizeBtn")
            self._maximize_btn.setFixedSize(int(46 * s), int(40 * s))
            self._maximize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._maximize_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))

            # Close button - use standard icon
            self._close_btn = QPushButton()
            self._close_btn.setObjectName("titleBarCloseBtn")
            self._close_btn.setFixedSize(int(46 * s), int(40 * s))
            self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._close_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))

            # Set tooltips for better UX
            self._minimize_btn.setToolTip("最小化")
            self._maximize_btn.setToolTip("最大化")
            self._close_btn.setToolTip("关闭")

            controls_layout.addWidget(self._minimize_btn)
            controls_layout.addWidget(self._maximize_btn)
            controls_layout.addWidget(self._close_btn)

            layout.addWidget(self._controls_widget)
        else:
            # On macOS, add spacing to account for system buttons
            # macOS traffic lights are on the left, so we need to add left margin
            layout.insertSpacing(0, int(80 * s))  # Space for macOS traffic lights

    def _apply_style(self) -> None:
        """Apply VSCode-style theme to title bar."""
        c = get_theme_colors()
        s = dpi_scale()

        # Update icons based on window state
        self._update_button_icons()

        self.setStyleSheet(f"""
            #titleBar {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
            }}
            #titleBarMenuBar {{
                background-color: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }}
            #titleBarMenuBar::item {{
                background-color: transparent;
                color: {c["fg"]};
                padding: {int(4 * s)}px {int(8 * s)}px;
                border-radius: {int(4 * s)}px;
                font-size: {int(13 * s)}px;
            }}
            #titleBarMenuBar::item:selected {{
                background-color: {c["selection"]};
            }}
            #titleBarMenuBar QMenu {{
                background-color: {c["context_bg"]};
                border: 1px solid {c["context_border"]};
                border-radius: {int(4 * s)}px;
                padding: {int(4 * s)}px;
            }}
            #titleBarMenuBar QMenu::item {{
                padding: {int(6 * s)}px {int(24 * s)}px;
                border-radius: {int(4 * s)}px;
                color: {c["fg"]};
            }}
            #titleBarMenuBar QMenu::item:selected {{
                background-color: {c["selection"]};
            }}
            #titleBarControls {{
                background-color: transparent;
            }}
            #titleBarMinimizeBtn,
            #titleBarMaximizeBtn {{
                background-color: transparent;
                border: none;
                padding: 0px;
            }}
            #titleBarMinimizeBtn:hover,
            #titleBarMaximizeBtn:hover {{
                background-color: {c["hover"]};
            }}
            #titleBarMinimizeBtn:pressed,
            #titleBarMaximizeBtn:pressed {{
                background-color: {c["border"]};
            }}
            #titleBarCloseBtn {{
                background-color: transparent;
                border: none;
                padding: 0px;
            }}
            #titleBarCloseBtn:hover {{
                background-color: {c["danger"]};
            }}
            #titleBarCloseBtn:pressed {{
                background-color: {c["danger_hover"]};
            }}
            /* macOS-specific styling */
            #titleBarMinimizeBtn,
            #titleBarMaximizeBtn,
            #titleBarCloseBtn {{
                border-radius: {'4px' if self._is_macos else '0px'};
            }}
        """)

    def _update_button_icons(self) -> None:
        """Update button icons based on window state."""
        if self._is_macos:
            return  # macOS uses system buttons

        if not hasattr(self, '_maximize_btn'):
            return  # Buttons not created yet

        window = self.window()
        if not window:
            return

        is_maximized = window.isMaximized()

        # Update maximize/restore icon
        if is_maximized:
            self._maximize_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton))
        else:
            self._maximize_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))

    def _connect_signals(self) -> None:
        """Connect button signals to window actions."""
        if not self._is_macos:
            self._minimize_btn.clicked.connect(self._on_minimize)
            self._maximize_btn.clicked.connect(self._on_maximize)
            self._close_btn.clicked.connect(self._on_close)

    def _on_minimize(self) -> None:
        """Handle minimize button click."""
        window = self.window()
        if window:
            window.showMinimized()

    def _on_maximize(self) -> None:
        """Handle maximize/restore button click."""
        window = self.window()
        if window:
            if window.isMaximized():
                window.showNormal()
            else:
                window.showMaximized()
            self._update_button_icons()

    def _on_close(self) -> None:
        """Handle close button click."""
        window = self.window()
        if window:
            window.close()

    def mousePressEvent(self, event) -> None:
        """Handle mouse press for window dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Only allow dragging from the title bar area, not from menu items
            pos = event.position().toPoint()
            if not self._menu_bar.geometry().contains(pos):
                self._drag_position = pos - self.window().frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event) -> None:
        """Handle mouse move for window dragging."""
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position:
            new_pos = event.position().toPoint() - self._drag_position
            self.window().move(new_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        """Handle double-click to maximize/restore."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Only allow double-click from title bar area, not from menu items
            pos = event.position().toPoint()
            if not self._menu_bar.geometry().contains(pos):
                self._on_maximize()
                event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Custom paint event for platform-specific rendering."""
        super().paintEvent(event)

        # On macOS, draw the title bar background to ensure consistency
        if self._is_macos:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    def get_menu_bar(self) -> QMenuBar:
        """Get the embedded menu bar."""
        return self._menu_bar

    def update_maximize_button(self, is_maximized: bool) -> None:
        """Update maximize button state."""
        self._update_button_icons()

    def nativeEvent(self, eventType, message):
        """Handle native Windows events for edge dragging."""
        if self._is_windows and eventType == b"windows_generic_MSG":
            msg = message
            if hasattr(msg, 'msg') and msg.msg == 0x0084:  # WM_NCHITTEST
                # Let Qt handle the event first
                result = super().nativeEvent(eventType, message)
                if result[1]:
                    return result

                # Check if mouse is in window edge area for resizing
                pos = QCursor.pos()
                window = self.window()
                if window:
                    window_pos = window.pos()
                    width = window.width()
                    height = window.height()

                    edge_margin = 6  # pixels

                    # Check edges and return corresponding hit test values
                    rel_y = pos.y() - window_pos.y()
                    rel_x = pos.x() - window_pos.x()

                    # Top edge
                    if rel_y <= edge_margin:
                        if rel_x <= edge_margin:
                            return (True, 13)  # HTTOPLEFT
                        if rel_x >= width - edge_margin:
                            return (True, 14)  # HTTOPRIGHT
                        return (True, 12)  # HTTOP

                    # Bottom edge
                    if rel_y >= height - edge_margin:
                        if rel_x <= edge_margin:
                            return (True, 16)  # HTBOTTOMLEFT
                        if rel_x >= width - edge_margin:
                            return (True, 17)  # HTBOTTOMRIGHT
                        return (True, 15)  # HTBOTTOM

                    # Left edge
                    if rel_x <= edge_margin:
                        return (True, 10)  # HTLEFT

                    # Right edge
                    if rel_x >= width - edge_margin:
                        return (True, 11)  # HTRIGHT

        return super().nativeEvent(eventType, message)
