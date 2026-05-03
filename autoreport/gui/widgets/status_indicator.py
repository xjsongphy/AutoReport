"""Animated status indicator — VS Code Copilot Chat style spinner."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class StatusIndicator(QWidget):
    """Minimal spinner + status text row."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._visible = False
        self._frame_idx = 0
        self._header = "Working"

        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.setSpacing(6)

        self._spinner_label = QLabel()
        self._spinner_label.setObjectName("statusSpinner")
        self._spinner_label.setFixedWidth(14)
        self._spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._spinner_label)

        self._header_label = QLabel(self._header)
        self._header_label.setObjectName("statusHeader")
        layout.addWidget(self._header_label)

        layout.addStretch()
        self.setVisible(False)

    def start(self, header: str = "Working") -> None:
        self._header = header
        self._header_label.setText(header)
        self._frame_idx = 0
        self._visible = True
        self.setVisible(True)
        self._update_display()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._visible = False
        self.setVisible(False)

    def set_header(self, header: str) -> None:
        self._header = header
        self._header_label.setText(header)

    def _tick(self) -> None:
        self._frame_idx = (self._frame_idx + 1) % len(_SPINNER_FRAMES)
        self._update_display()

    def _update_display(self) -> None:
        self._spinner_label.setText(_SPINNER_FRAMES[self._frame_idx])

    def is_running(self) -> bool:
        return self._visible
