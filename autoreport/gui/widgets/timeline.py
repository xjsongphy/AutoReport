"""Shared timeline widgets for agent messages, thinking, and tool calls."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ..theme import get_theme_colors

TIMELINE_DOT_CENTER_Y = 11
TIMELINE_DOT_SIZE = 7
TIMELINE_RAIL_WIDTH = 12
TIMELINE_AGENT_DOT = "#9ca3af"


class TimelineRail(QWidget):
    """Draw a fixed-position dot and optional chain lines.

    The dot center is anchored to the first text line, so multi-line content
    cannot vertically re-center the marker.
    """

    def __init__(self, dot_color: str = TIMELINE_AGENT_DOT, parent: QWidget | None = None):
        super().__init__(parent)
        self._dot_color = dot_color
        self._prev_link = False
        self._next_link = False
        self.setFixedWidth(TIMELINE_RAIL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_dot_color(self, dot_color: str) -> None:
        if self._dot_color == dot_color:
            return
        self._dot_color = dot_color
        self.update()

    def set_chain(self, prev_link: bool, next_link: bool) -> None:
        if self._prev_link == prev_link and self._next_link == next_link:
            return
        self._prev_link = prev_link
        self._next_link = next_link
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx = self.width() / 2
        dot_radius = TIMELINE_DOT_SIZE / 2
        dot_top = TIMELINE_DOT_CENTER_Y - dot_radius
        dot_bottom = TIMELINE_DOT_CENTER_Y + dot_radius

        painter.setPen(QColor(get_theme_colors()["border"]))
        if self._prev_link:
            painter.drawLine(int(cx), 0, int(cx), int(dot_top))
        if self._next_link:
            painter.drawLine(int(cx), int(dot_bottom), int(cx), self.height())

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._dot_color))
        painter.drawEllipse(QRectF(cx - dot_radius, dot_top, TIMELINE_DOT_SIZE, TIMELINE_DOT_SIZE))
        painter.end()
