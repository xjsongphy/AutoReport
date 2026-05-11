"""Status badge — compact, boxed, centered status indicator."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget, QPushButton


_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class StatusIndicator(QPushButton):
    """Status badge with spinner, boxed style, centered text.

    States:
    - Idle: gray badge, "Idle"
    - Thinking: blue spinner + "Thinking"
    - Tool: amber spinner + "Running Tool"
    - Error: red badge, "Error"
    - Debug: purple badge, "Debug"
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._visible = False
        self._frame_idx = 0
        self._status = "idle"
        self._clickable = False

        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.clicked.connect(self._on_clicked)

        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._spinner_label = QLabel()
        self._spinner_label.setObjectName("statusSpinner")
        self._spinner_label.setFixedWidth(12)
        self._spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._spinner_label)

        self._status_label = QLabel()
        self._status_label.setObjectName("statusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        self._update_style()
        self.setVisible(False)

    def _update_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        # Status colors
        colors = {
            "idle": ("#3c3c3c", "#737373"),      # bg, fg
            "thinking": ("#1a3a5a", "#0078d4"),
            "tool": ("#5a4a1a", "#cca700"),
            "error": ("#5a1a1a", "#f44747"),
            "debug": ("#3a1a5a", "#b180d7"),
        }

        bg, fg = colors.get(self._status, colors["idle"])

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {bg};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
                text-align: center;
            }}
            QPushButton:hover {{
                border: 1px solid {fg};
            }}
            QLabel#statusSpinner {{
                color: {fg};
                font-size: 11px;
            }}
            QLabel#statusLabel {{
                color: {fg};
                font-size: 11px;
            }}
        """)

    def start(self, status: str = "thinking") -> None:
        status_map = {
            "thinking": ("Thinking", True),
            "running_tool": ("Running Tool", True),
            "tool": ("Running Tool", True),
        }
        text, spin = status_map.get(status, ("Working", True))
        self.set_status(status, text)
        if spin:
            self._timer.start()
        self.setVisible(True)

    def stop(self) -> None:
        self._timer.stop()
        self.set_status("idle", "Idle")
        self.setVisible(False)

    def set_status(self, status: str, text: str | None = None) -> None:
        self._status = status
        if text is None:
            text_map = {
                "idle": "Idle",
                "thinking": "Thinking",
                "running_tool": "Running Tool",
                "tool": "Running Tool",
                "error": "Error",
                "debug_mode": "Debug",
            }
            text = text_map.get(status, status.title())
        self._status_label.setText(text)
        self._update_style()

    def _tick(self) -> None:
        self._frame_idx = (self._frame_idx + 1) % len(_SPINNER_FRAMES)
        self._spinner_label.setText(_SPINNER_FRAMES[self._frame_idx])

    def _on_clicked(self) -> None:
        pass  # Can add click handler later (e.g., show debug panel)

    def is_running(self) -> bool:
        return self._timer.isActive()
