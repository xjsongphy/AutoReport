"""Shared timeline widgets for agent messages, thinking, and tool calls."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ..theme import get_theme_colors

TIMELINE_DOT_CENTER_Y = 11
TIMELINE_DOT_SIZE = 7
TIMELINE_RAIL_WIDTH = 12


class TimelineRail(QWidget):
    """Draw a fixed-position dot and optional chain lines.

    The dot center is anchored to the first text line, so multi-line content
    cannot vertically re-center the marker.
    """

    def __init__(self, dot_color: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        if dot_color is None:
            dot_color = get_theme_colors()["timeline_dot"]
        self._dot_color = dot_color
        self._prev_link = False
        self._next_link = False
        self._dot_center_y: float | None = None
        self.setFixedWidth(TIMELINE_RAIL_WIDTH)
        # Keep rail height coupled to row content instead of consuming free
        # vertical space in sparse timelines.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
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

    def set_dot_center_y(self, dot_center_y: float | None) -> None:
        if self._dot_center_y == dot_center_y:
            return
        self._dot_center_y = dot_center_y
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx = self.width() / 2
        dot_radius = TIMELINE_DOT_SIZE / 2
        dot_center_y = (
            self._dot_center_y
            if self._dot_center_y is not None
            else TIMELINE_DOT_CENTER_Y
        )
        dot_top = dot_center_y - dot_radius
        dot_bottom = dot_center_y + dot_radius

        painter.setPen(QColor(get_theme_colors()["border"]))
        if self._prev_link:
            painter.drawLine(int(cx), 0, int(cx), int(dot_top))
        if self._next_link:
            painter.drawLine(int(cx), int(dot_bottom), int(cx), self.height())

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._dot_color))
        painter.drawEllipse(QRectF(cx - dot_radius, dot_top, TIMELINE_DOT_SIZE, TIMELINE_DOT_SIZE))
        painter.end()
