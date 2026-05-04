"""Animated working border beam — VS Code Copilot Chat style.

VS Code uses a conic-gradient border beam (::before/::after pseudo-elements)
that rotates around the input container while the agent is working.
In PyQt6 we emulate this with QPainter + QConicalGradient + QTimer.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QConicalGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class WorkingBorder(QWidget):
    """Animated shimmer border that wraps around a target widget.

    Paints a thin rotating conic-gradient beam along its perimeter,
    matching VS Code's .chat-input-container.working::before/::after.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._angle = 135.0
        self._opacity = 0.0
        self._target_opacity = 0.0
        self._running = False

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._tick)

        self.setVisible(False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        # Fill parent completely
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        super().resizeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        super().showEvent(event)

    def start(self) -> None:
        self._running = True
        self._target_opacity = 1.0
        self.setVisible(True)
        self._timer.start()

    def stop(self) -> None:
        self._target_opacity = 0.0
        self._running = False
        # Keep timer running briefly for fade-out
        if not self._timer.isActive():
            self._timer.start()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._opacity < 0.01:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0

        r = max(w, h) * 0.8

        beam_color = QColor("#0078d4")
        transparent = QColor(0, 0, 0, 0)

        grad = QConicalGradient(cx, cy, self._angle)
        grad.setColorAt(0.0, transparent)
        grad.setColorAt(0.65, beam_color.lighter(120))
        grad.setColorAt(0.72, beam_color)
        grad.setColorAt(0.78, beam_color.lighter(120))
        grad.setColorAt(0.85, transparent)
        grad.setColorAt(1.0, transparent)

        pen = QPen()
        pen.setWidthF(1.5)
        pen.setBrush(grad)

        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Draw rounded rect inset from widget bounds
        inset = 2
        p.drawRoundedRect(inset, inset, w - 2 * inset, h - 2 * inset, 8, 8)

        p.end()

    def _tick(self) -> None:
        # Update angle for rotation
        self._angle = (self._angle + 1.8) % 360.0

        # Smooth fade in/out
        if abs(self._opacity - self._target_opacity) < 0.01:
            if not self._running and self._opacity < 0.01:
                self._timer.stop()
                self.setVisible(False)
            return
        else:
            self._opacity += (self._target_opacity - self._opacity) * 0.12

        self.update()
