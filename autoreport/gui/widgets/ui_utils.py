"""Shared UI controls and rendering helpers."""

from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton, QWidget

from ..theme import get_theme_colors


_SVG_ICONS = {
    "new-file": "new-file.svg",
    "new-folder": "new-folder.svg",
    "refresh": "refresh.svg",
    "copy": "copy.svg",
    "settings": "settings.svg",
}


def render_svg_icon(name: str, color: QColor, size: int = 16) -> QIcon:
    """Render a local SVG icon tinted to the requested color."""
    svg_file = _SVG_ICONS.get(name)
    svg_path = Path(__file__).parent / svg_file if svg_file else None
    if svg_path is None or not svg_path.exists():
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setPen(color)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "?")
        painter.end()
        return QIcon(pixmap)

    screen = QApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen is not None else 1.0
    actual_size = int(size * dpr)
    pixmap = QPixmap(actual_size, actual_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    QSvgRenderer(str(svg_path)).render(painter, QRectF(0.0, 0.0, float(size), float(size)))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return QIcon(pixmap)


class CompactTooltipFilter(QObject):
    """Small VS Code-like tooltip for icon buttons (2 s hover delay)."""

    def __init__(self, text: str, parent: QWidget):
        super().__init__(parent)
        self._text = text
        self._tip: QLabel | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._delayed_show)
        self._anchor: QWidget | None = None

    def eventFilter(self, obj, event):
        if event.type() in (
            event.Type.Leave,
            event.Type.MouseButtonPress,
            event.Type.Hide,
        ):
            self._timer.stop()
            self._anchor = None
            self._hide()
            return False

        if isinstance(obj, QWidget) and obj.isEnabled():
            if event.type() == event.Type.Enter:
                self._anchor = obj
                self._timer.start()
            elif event.type() == event.Type.MouseMove and self._anchor is None:
                # When a button becomes visible/enabled under an already-stationary cursor,
                # Enter may not fire; a subsequent move should still start tooltip delay.
                self._anchor = obj
                self._timer.start()
        return False

    def _delayed_show(self) -> None:
        if self._anchor:
            self._show(self._anchor)

    def _show(self, anchor: QWidget) -> None:
        self._hide()
        tip = QLabel(self._text)
        tip.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        tip.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        tip.setStyleSheet(compact_tooltip_qss())
        tip.adjustSize()
        x = (anchor.width() - tip.width()) // 2
        tip.move(anchor.mapToGlobal(QPoint(x, anchor.height() + 3)))
        tip.show()
        self._tip = tip

    def _hide(self) -> None:
        if self._tip is None:
            return
        self._tip.hide()
        self._tip.deleteLater()
        self._tip = None


def compact_tooltip_qss(selector: str = "QLabel") -> str:
    """Shared compact tooltip style used instead of platform-native QToolTip."""
    c = get_theme_colors()
    return f"""
        {selector} {{
            background-color: {c["surface"]};
            color: {c["fg"]};
            border: 1px solid {c["border"]};
            border-radius: 6px;
            padding: 2px 6px;
            font-size: 11px;
        }}
    """


def install_compact_tooltip(button: QPushButton, text: str) -> None:
    """Attach the shared compact tooltip to a button."""
    button.setToolTip("")
    button.setMouseTracking(True)
    tooltip_filter = CompactTooltipFilter(text, button)
    button.installEventFilter(tooltip_filter)
    button._compact_tooltip_filter = tooltip_filter  # keep QObject alive


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
            install_compact_tooltip(self, tooltip)
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
            border-radius: 4px;
            color: {foreground_color};
        }}
        QComboBox{selector} QAbstractItemView::item:selected {{
            background-color: transparent;
            color: {foreground_color};
        }}
        QComboBox{selector} QAbstractItemView::item:hover {{
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
