"""Animated status indicator — Codex CLI style with spinner and elapsed timer."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


def _fmt_elapsed(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m {s:02}s"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02}m {s:02}s"


_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class StatusIndicator(QWidget):
    """Live task status row with spinner, header text, and elapsed timer.

    Mimics Codex's StatusIndicatorWidget: spinner + header + (elapsed · esc to interrupt).
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._visible = False
        self._elapsed = 0
        self._frame_idx = 0
        self._header = "Working"

        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(100)  # 10 fps for spinner + counter
        self._timer.timeout.connect(self._tick)

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(6)

        self._spinner_label = QLabel()
        self._spinner_label.setObjectName("statusSpinner")
        self._spinner_label.setFixedWidth(16)
        self._spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._spinner_label)

        self._header_label = QLabel(self._header)
        self._header_label.setObjectName("statusHeader")
        layout.addWidget(self._header_label)

        self._elapsed_label = QLabel()
        self._elapsed_label.setObjectName("statusElapsed")
        layout.addWidget(self._elapsed_label)

        self._hint_label = QLabel()
        self._hint_label.setObjectName("statusHint")
        layout.addWidget(self._hint_label)

        layout.addStretch()
        self.setVisible(False)

    def start(self, header: str = "Working") -> None:
        self._header = header
        self._header_label.setText(header)
        self._elapsed = 0
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
        self._elapsed += 1
        self._frame_idx = (self._frame_idx + 1) % len(_SPINNER_FRAMES)
        self._update_display()

    def _update_display(self) -> None:
        self._spinner_label.setText(_SPINNER_FRAMES[self._frame_idx])
        elapsed_text = _fmt_elapsed(self._elapsed // 10)
        self._elapsed_label.setText(f"({elapsed_text})")
        self._hint_label.setText("· Esc 中断")

    def is_running(self) -> bool:
        return self._visible
