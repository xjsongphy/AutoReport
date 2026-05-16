"""Custom title bar for frameless window - VSCode style."""

import sys
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMenuBar,
    QMenu,
    QVBoxLayout,
)

from .theme import get_theme_colors
from .scale import dpi_scale


class TitleBar(QWidget):
    """Custom title bar with menu and window controls.

    Features:
    - Integrated menu bar
    - Window drag support
    - Minimize/Maximize/Close buttons
    - Platform-specific styling (macOS/Windows)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_position = QPoint()
        self._is_macos = sys.platform == "darwin"

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
        # On macOS, these are typically on the left, but for VSCode-style
        # we keep them on the right for consistency
        self._controls_widget = QWidget(self)
        self._controls_widget.setObjectName("titleBarControls")
        controls_layout = QHBoxLayout(self._controls_widget)
        controls_layout.setContentsMargins(0, 0, int(8 * s), 0)
        controls_layout.setSpacing(0)

        # Minimize button
        self._minimize_btn = QPushButton("−")
        self._minimize_btn.setObjectName("titleBarMinimizeBtn")
        self._minimize_btn.setFixedSize(int(46 * s), int(40 * s))
        self._minimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Maximize/Restore button
        self._maximize_btn = QPushButton("□")
        self._maximize_btn.setObjectName("titleBarMaximizeBtn")
        self._maximize_btn.setFixedSize(int(46 * s), int(40 * s))
        self._maximize_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Close button
        self._close_btn = QPushButton("×")
        self._close_btn.setObjectName("titleBarCloseBtn")
        self._close_btn.setFixedSize(int(46 * s), int(40 * s))
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        controls_layout.addWidget(self._minimize_btn)
        controls_layout.addWidget(self._maximize_btn)
        controls_layout.addWidget(self._close_btn)

        layout.addWidget(self._controls_widget)

    def _apply_style(self) -> None:
        """Apply VSCode-style theme to title bar."""
        c = get_theme_colors()
        s = dpi_scale()

        # Update button text based on platform
        if self._is_macos:
            self._minimize_btn.setText("−")
            self._maximize_btn.setText("□")
            self._close_btn.setText("×")
        else:
            # Windows-style symbols
            self._minimize_btn.setText("−")
            self._maximize_btn.setText("□")
            self._close_btn.setText("×")

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
                color: {c["fg"]};
                border: none;
                font-size: {int(16 * s)}px;
                font-weight: {c["fw_medium"]};
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
                color: {c["fg"]};
                border: none;
                font-size: {int(18 * s)}px;
                font-weight: {c["fw_semibold"]};
            }}
            #titleBarCloseBtn:hover {{
                background-color: #e81123;
                color: #ffffff;
            }}
            #titleBarCloseBtn:pressed {{
                background-color: #c90014;
                color: #ffffff;
            }}
        """)

    def _connect_signals(self) -> None:
        """Connect button signals to window actions."""
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
                self._maximize_btn.setText("□")
            else:
                window.showMaximized()
                self._maximize_btn.setText("❐")

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

    def get_menu_bar(self) -> QMenuBar:
        """Get the embedded menu bar."""
        return self._menu_bar

    def update_maximize_button(self, is_maximized: bool) -> None:
        """Update maximize button state."""
        if is_maximized:
            self._maximize_btn.setText("❐")
        else:
            self._maximize_btn.setText("□")
