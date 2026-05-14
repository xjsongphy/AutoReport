"""Shared UI controls for consistent button/dropdown behavior."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores wheel events and draws a clean chevron."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        x = self.width() - 16
        y = self.height() // 2 - 2
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark
        color = QColor("#999") if dark else QColor("#666")

        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(x, y, x + 5, y + 5)
        painter.drawLine(x + 5, y + 5, x + 10, y)
        painter.end()

    def showPopup(self) -> None:  # noqa: N802
        if self.count() == 0:
            self.addItem("（无可用项）")
            self.model().item(0).setEnabled(False)
        super().showPopup()


class IconActionButton(QPushButton):
    """Small clickable icon/text action button with shared defaults."""

    def __init__(
        self,
        text: str = "",
        tooltip: str = "",
        object_name: str = "",
        button_size: tuple[int, int] = (22, 22),
        icon_size: tuple[int, int] | None = None,
        on_click=None,
        parent=None,
    ):
        super().__init__(text, parent)
        if object_name:
            self.setObjectName(object_name)
        if tooltip:
            self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(*button_size)
        if icon_size is not None:
            self.setIconSize(QSize(*icon_size))
        if on_click is not None:
            self.clicked.connect(on_click)


def combo_box_qss(
    selector: str,
    *,
    border_color: str,
    background_color: str,
    foreground_color: str,
    hover_border_color: str,
    selection_bg: str,
    selection_fg: str,
    font_size: int = 12,
    padding: str = "4px 24px 4px 8px",
) -> str:
    """Build a reusable combo-box + popup list QSS fragment."""
    return f"""
        QComboBox{selector} {{
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: {padding};
            font-size: {font_size}px;
            background-color: {background_color};
            color: {foreground_color};
        }}
        QComboBox{selector}:hover {{
            border-color: {hover_border_color};
        }}
        QComboBox{selector}::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 0px;
            border: none;
            background: transparent;
        }}
        QComboBox{selector}::down-arrow {{
            image: none;
            width: 0px;
            height: 0px;
            border: none;
        }}
        QComboBox{selector} QAbstractItemView {{
            border: 1px solid {border_color};
            border-radius: 4px;
            background-color: {background_color};
            color: {foreground_color};
            selection-background-color: {selection_bg};
            selection-color: {selection_fg};
            padding: 4px;
            outline: none;
        }}
        QComboBox{selector} QAbstractItemView::item {{
            min-height: 22px;
            padding: 2px 8px;
            border: none;
        }}
        QComboBox{selector} QAbstractItemView::item:selected {{
            background-color: {selection_bg};
            color: {selection_fg};
        }}
    """


def filled_button_qss(
    selector: str,
    *,
    bg: str,
    fg: str,
    hover_bg: str,
    disabled_bg: str,
    disabled_fg: str,
) -> str:
    """Build a reusable filled button QSS fragment."""
    return f"""
        QPushButton{selector} {{
            background-color: {bg};
            color: {fg};
            border: none;
            border-radius: 4px;
            font-weight: 600;
            font-size: 12px;
            padding: 2px 12px;
        }}
        QPushButton{selector}:hover {{
            background-color: {hover_bg};
        }}
        QPushButton{selector}:disabled {{
            background-color: {disabled_bg};
            color: {disabled_fg};
        }}
    """
