"""Shared UI controls and rendering helpers."""

from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication, QComboBox, QFrame, QLabel, QListView, QMenu, QPushButton, QStyle, QStyledItemDelegate, QStyleFactory, QStyleOptionViewItem, QWidget

from ..theme import get_theme_colors


_SVG_ICONS = {
    "file": "file.svg",
    "new-file": "new-file.svg",
    "new-folder": "new-folder.svg",
    "refresh": "refresh.svg",
    "copy": "copy.svg",
    "settings": "settings.svg",
    "run": "run.svg",
    "preview": "preview.svg",
    "eye": "eye.svg",
    "eye-off": "eye-off.svg",
    "history": "history.svg",
    "code-context": "code-context.svg",
}
UI_HOVER_DELAY_MS = 2000


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
        self._tip: QWidget | None = None
        self._tip_label: QLabel | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(UI_HOVER_DELAY_MS)
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
        tip = QWidget()
        tip.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        tip.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        tip.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        tip.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        tip.setStyleSheet("background: transparent; border: none;")

        bubble = QLabel(self._text, tip)
        bubble.setObjectName("compactTooltipBubble")
        bubble.setStyleSheet(compact_tooltip_qss("QLabel#compactTooltipBubble"))
        bubble.adjustSize()
        tip.resize(bubble.size())
        bubble.move(0, 0)

        x = (anchor.width() - tip.width()) // 2
        tip.move(anchor.mapToGlobal(QPoint(x, anchor.height() + 3)))
        tip.show()
        self._tip = tip
        self._tip_label = bubble

    def _hide(self) -> None:
        if self._tip is None:
            return
        self._tip.hide()
        self._tip.deleteLater()
        self._tip = None
        self._tip_label = None


def compact_tooltip_qss(selector: str = "QLabel") -> str:
    """Shared compact tooltip style used instead of platform-native QToolTip."""
    c = get_theme_colors()
    return f"""
        {selector} {{
            background-color: {c["bg"]};
            color: {c["popup_fg"]};
            border: 1px solid {c["border"]};
            border-radius: {c["radius_md"]};
            padding: 2px 6px;
            font-size: 11px;
        }}
    """


def create_isolated_context_menu(anchor: QWidget | None = None) -> QMenu:
    """Create a context menu isolated from parent-widget QSS inheritance."""
    c = get_theme_colors()
    menu = QMenu()
    menu.setStyleSheet(
        f"""
        QMenu {{
            background-color: {c["context_bg"]};
            border: 1px solid {c["context_border"]};
            border-radius: {c["radius_md"]};
            padding: 4px;
        }}
        QMenu::item {{
            background-color: transparent;
            color: {c["popup_fg"]};
            padding: 4px 8px;
            margin: 0;
            font-size: 12px;
            border-radius: {c["radius_md"]};
        }}
        QMenu::indicator {{
            width: 0px;
            height: 0px;
        }}
        QMenu::item:selected {{
            background-color: {c["popup_hover"]};
        }}
        QMenu::item:hover {{
            background-color: {c["popup_hover"]};
        }}
        """
    )
    if anchor is not None:
        menu.setFont(anchor.font())
    return menu


def install_compact_tooltip(button: QPushButton, text: str) -> None:
    """Attach the shared compact tooltip to a button."""
    button.setToolTip("")
    button.setMouseTracking(True)
    existing = getattr(button, "_compact_tooltip_filter", None)
    if isinstance(existing, CompactTooltipFilter):
        existing._text = text
        existing._timer.stop()
        existing._hide()
        return
    tooltip_filter = CompactTooltipFilter(text, button)
    button.installEventFilter(tooltip_filter)
    button._compact_tooltip_filter = tooltip_filter  # keep QObject alive


class _ComboPopupDelegate(QStyledItemDelegate):
    """Draw combo popup rows using current-index selection, not hover selection."""

    def __init__(self, combo: QComboBox, parent=None):
        super().__init__(parent)
        self._combo = combo

    @staticmethod
    def _radius_px(value: str) -> float:
        try:
            return float(str(value).strip().removesuffix("px"))
        except ValueError:
            return 4.0

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # noqa: N802
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        c = get_theme_colors()
        opt.textElideMode = Qt.TextElideMode.ElideRight

        is_current = index.row() == self._combo.currentIndex()
        is_hovered = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        bg = c["selectionBlue"] if is_current else (c["hover"] if is_hovered else None)

        opt.state &= ~QStyle.StateFlag.State_Selected
        opt.state &= ~QStyle.StateFlag.State_MouseOver
        opt.palette.setColor(opt.palette.ColorRole.Text, QColor(c["fg"]))
        opt.palette.setColor(opt.palette.ColorRole.HighlightedText, QColor(c["fg"]))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if bg is not None:
            radius = self._radius_px(c.get("radius_sm", "4px"))
            rect = opt.rect.adjusted(0, 0, -1, -1)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(bg))
            painter.drawRoundedRect(rect, radius, radius)

        QApplication.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        painter.restore()


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores wheel events and draws a clean chevron."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrame(False)
        # Force a cross-platform style path (avoid macOS native popup look).
        fusion = QStyleFactory.create("Fusion")
        if fusion is not None:
            self.setStyle(fusion)

        # Use a non-native popup view so QSS hover/font are applied consistently.
        popup_view = QListView(self)
        popup_view.setObjectName("comboPopupView")
        popup_view.setFrameShape(QFrame.Shape.NoFrame)
        popup_view.setUniformItemSizes(True)
        popup_view.setSpacing(0)
        popup_view.setMouseTracking(True)
        popup_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        popup_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        popup_view.viewport().setMouseTracking(True)
        popup_view.viewport().installEventFilter(self)
        popup_view.setItemDelegate(_ComboPopupDelegate(self, popup_view))
        self.setView(popup_view)

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        x = self.width() - 16
        y = self.height() // 2 - 2
        c = get_theme_colors()
        color = QColor(c["muted"])

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
        self._apply_popup_style()
        super().showPopup()
        # Keep popup position consistent across platforms: directly below combo.
        view = self.view()
        if view and view.window():
            view.setFont(self.font())
            popup = view.window()
            popup.setWindowFlags(
                Qt.WindowType.Popup
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.NoDropShadowWindowHint
            )
            self._style_popup_host(popup)
            # Stronger overlap to eliminate visual seam between combo and popup.
            popup.move(self.mapToGlobal(QPoint(0, self.height() - 2)))
            popup.show()
            self._apply_popup_mask(popup)

    def eventFilter(self, obj, event):  # noqa: N802
        view = self.view()
        if view and obj is view.viewport():
            et = event.type()
            if et in (event.Type.Leave, event.Type.Hide):
                sel = view.selectionModel()
                if sel:
                    sel.clearSelection()
        return super().eventFilter(obj, event)

    def _apply_popup_style(self) -> None:
        c = get_theme_colors()
        radius = c.get("radius_md", "6px")
        item_radius = c.get("radius_sm", "4px")
        border_color = c.get("input_border", c["border"])
        border_width = c.get("input_border_width", "1px")
        row_height = 30
        view = self.view()
        if view is None:
            return
        view.setStyleSheet(
            f"""
            QListView#comboPopupView {{
                border: {border_width} solid {border_color};
                border-radius: {radius};
                background-color: {c["bg"]};
                color: {c["fg"]};
                outline: none;
                padding: 0;
            }}
            QListView#comboPopupView::item {{
                border: none;
                background: transparent;
                color: {c["fg"]};
                padding: 0 8px;
                margin: 0;
                min-height: {row_height}px;
                max-height: {row_height}px;
                border-radius: {item_radius};
            }}
            QListView#comboPopupView::item:selected {{
                background-color: {c["selectionBlue"]};
                color: {c["fg"]};
            }}
            QListView#comboPopupView::item:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}
            QListView#comboPopupView::item:selected:hover {{
                background-color: {c["selectionBlue"]};
                color: {c["fg"]};
                border-radius: {item_radius};
            }}
            """
        )

    def _style_popup_host(self, popup: QWidget) -> None:
        popup.setContentsMargins(0, 0, 0, 0)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        popup.setAutoFillBackground(False)
        popup.setStyleSheet("background: transparent; border: none;")

    def _apply_popup_mask(self, popup: QWidget) -> None:
        radius = 6.0
        try:
            radius = float(str(get_theme_colors().get("radius_md", "6px")).removesuffix("px"))
        except ValueError:
            pass
        path = QPainterPath()
        rect = QRectF(QRect(popup.rect()).adjusted(0, 0, -1, -1))
        if rect.isEmpty():
            return
        path.addRoundedRect(rect, radius, radius)
        popup.setMask(QRegion(path.toFillPolygon().toPolygon()))


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


class TextButton(QPushButton):
    """Text button with border, transparent background, and configurable color."""

    def __init__(
        self,
        text: str = "",
        tooltip: str = "",
        color: str = "",
        hover_bg: str = "",
        object_name: str = "",
        on_click=None,
        parent=None,
    ):
        super().__init__(text, parent)
        if object_name:
            self.setObjectName(object_name)
        if tooltip:
            install_compact_tooltip(self, tooltip)

        c = get_theme_colors()
        apply_text_button_style(
            self,
            color=color or c["fg"],
            hover_bg=hover_bg or c["hover"],
        )
        if on_click is not None:
            self.clicked.connect(on_click)


def text_button_qss(
    selector: str = "",
    *,
    color: str = "",
    hover_bg: str = "",
    hover_color: str | None = None,
    border: str | None = None,
    hover_border: str | None = None,
    padding: str = "4px 12px",
    font_size: int = 12,
    radius: str | None = None,
) -> str:
    """Build the shared outlined text-button style used by ``TextButton``."""
    c = get_theme_colors()
    effective_color = color or c["fg"]
    return outlined_button_qss(
        selector,
        fg=effective_color,
        border=border or effective_color,
        hover_bg=hover_bg or c["hover"],
        hover_fg=hover_color or effective_color,
        hover_border=hover_border or border or effective_color,
        padding=padding,
        font_size=font_size,
        radius=radius or c["radius_sm"],
    )


def apply_text_button_style(
    button: QPushButton,
    *,
    color: str = "",
    hover_bg: str = "",
    hover_color: str | None = None,
    border: str | None = None,
    hover_border: str | None = None,
    padding: str = "4px 12px",
    font_size: int = 12,
    radius: str | None = None,
) -> None:
    """Apply the shared ``TextButton`` styling to an existing QPushButton."""
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        text_button_qss(
            "",
            color=color,
            hover_bg=hover_bg,
            hover_color=hover_color,
            border=border,
            hover_border=hover_border,
            padding=padding,
            font_size=font_size,
            radius=radius,
        )
    )


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
    radius: str = "4px",
    popup_radius: str | None = None,
    item_radius: str = "0px",
) -> str:
    """Build a reusable combo-box + popup list QSS fragment."""
    c = get_theme_colors()
    effective_popup_radius = popup_radius if popup_radius is not None else radius
    return f"""
        QComboBox{selector} {{
            border: 1px solid {border_color};
            border-radius: {radius};
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
            border-radius: {effective_popup_radius};
            background: transparent;
            color: {foreground_color};
            selection-background-color: {selection_bg};
            selection-color: {selection_fg};
            padding: 0;
            outline: none;
        }}
        QComboBox{selector} QAbstractItemView::viewport {{
            border: none;
            border-radius: {effective_popup_radius};
            background-color: {background_color};
            padding: 0;
        }}
        QComboBox{selector} QAbstractItemView::item {{
            min-height: 22px;
            padding: 0 8px;
            border: none;
            border-radius: {item_radius};
            color: {foreground_color};
            background: transparent;
        }}
        QComboBox{selector} QAbstractItemView::item:selected {{
            background-color: {selection_bg};
            color: {selection_fg};
        }}
        QComboBox{selector} QAbstractItemView::item:hover {{
            background-color: {c["hover"]};
            color: {foreground_color};
        }}
        QComboBox{selector} QAbstractItemView::item:selected:hover {{
            background-color: {selection_bg};
            color: {selection_fg};
            border-radius: {item_radius};
        }}
    """


def line_edit_qss(
    selector: str,
    *,
    border_color: str,
    focus_border_color: str,
    background_color: str,
    foreground_color: str,
    disabled_bg: str,
    disabled_fg: str,
    radius: str = "4px",
    font_size: int = 13,
    padding: str = "6px 10px",
) -> str:
    """Build a reusable QLineEdit style fragment."""
    return f"""
        QLineEdit{selector} {{
            border: 1px solid {border_color};
            border-radius: {radius};
            padding: {padding};
            font-size: {font_size}px;
            background-color: {background_color};
            color: {foreground_color};
        }}
        QLineEdit{selector}:focus {{
            border-color: {focus_border_color};
        }}
        QLineEdit{selector}:disabled {{
            background-color: {disabled_bg};
            color: {disabled_fg};
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
    border: str = "none",
    radius: str = "4px",
    padding: str = "2px 12px",
    font_size: int = 12,
    font_weight: str | None = None,
) -> str:
    """Build a reusable filled button QSS fragment."""
    c = get_theme_colors()
    effective_weight = font_weight or c["fw_semibold"]
    return f"""
        QPushButton{selector} {{
            background-color: {bg};
            color: {fg};
            border: {border};
            border-radius: {radius};
            font-weight: {effective_weight};
            font-size: {font_size}px;
            padding: {padding};
        }}
        QPushButton{selector}:hover {{
            background-color: {hover_bg};
        }}
        QPushButton{selector}:disabled {{
            background-color: {disabled_bg};
            color: {disabled_fg};
        }}
    """


def outlined_button_qss(
    selector: str,
    *,
    fg: str,
    border: str,
    hover_bg: str,
    bg: str = "transparent",
    hover_fg: str | None = None,
    hover_border: str | None = None,
    disabled_bg: str = "transparent",
    disabled_fg: str | None = None,
    disabled_border: str | None = None,
    radius: str = "4px",
    padding: str = "6px 16px",
    font_size: int = 12,
    font_weight: str | None = None,
) -> str:
    """Build a reusable outlined text button QSS fragment."""
    c = get_theme_colors()
    effective_hover_fg = hover_fg or fg
    effective_hover_border = hover_border or border
    effective_disabled_fg = disabled_fg or c["muted"]
    effective_disabled_border = disabled_border or c["border"]
    effective_weight = font_weight or c["fw_normal"]
    return f"""
        QPushButton{selector} {{
            background-color: {bg};
            color: {fg};
            border: 1px solid {border};
            border-radius: {radius};
            font-size: {font_size}px;
            font-weight: {effective_weight};
            padding: {padding};
        }}
        QPushButton{selector}:hover {{
            background-color: {hover_bg};
            color: {effective_hover_fg};
            border-color: {effective_hover_border};
        }}
        QPushButton{selector}:disabled {{
            background-color: {disabled_bg};
            color: {effective_disabled_fg};
            border-color: {effective_disabled_border};
        }}
    """


def secondary_filled_button_qss(
    selector: str,
    *,
    radius: str | None = None,
    padding: str = "8px 20px",
    font_size: int = 13,
    font_weight: str | None = None,
) -> str:
    """Build a reusable secondary button with persistent background color."""
    c = get_theme_colors()
    return outlined_button_qss(
        selector,
        fg=c["secondaryBtnFg"],
        border=c["secondaryBtnBorder"],
        hover_bg=c["secondaryBtnHoverBg"],
        bg=c["secondaryBtnBg"],
        hover_border=c["secondaryBtnHoverBorder"],
        disabled_bg=c["inputDisabledBg"],
        disabled_fg=c["inputDisabledFg"],
        radius=radius or c["radius_md"],
        padding=padding,
        font_size=font_size,
        font_weight=font_weight,
    )


def ghost_button_qss(
    selector: str,
    *,
    fg: str | None = None,
    hover_bg: str | None = None,
    hover_fg: str | None = None,
    radius: str | None = None,
    padding: str = "8px 16px",
    font_size: int = 13,
    font_weight: str | None = None,
) -> str:
    """Build a reusable ghost button with hover-only background."""
    c = get_theme_colors()
    return f"""
        QPushButton{selector} {{
            background-color: transparent;
            color: {fg or c["secondaryBtnFg"]};
            border: none;
            border-radius: {radius or c["radius_md"]};
            padding: {padding};
            font-size: {font_size}px;
            font-weight: {font_weight or c["fw_normal"]};
        }}
        QPushButton{selector}:hover {{
            background-color: {hover_bg or c["hover"]};
            color: {hover_fg or c["cancelHoverFg"]};
        }}
        QPushButton{selector}:disabled {{
            color: {c["muted"]};
        }}
    """


def danger_filled_button_qss(
    selector: str,
    *,
    radius: str | None = None,
    padding: str = "4px 10px",
    font_size: int = 12,
    font_weight: str | None = None,
) -> str:
    """Build a reusable destructive filled text button QSS fragment."""
    c = get_theme_colors()
    return filled_button_qss(
        selector,
        bg=c["danger"],
        fg=c["primaryBtnFg"],
        hover_bg=c["danger_hover"],
        disabled_bg=c["inputDisabledBg"],
        disabled_fg=c["inputDisabledFg"],
        radius=radius or c["radius_sm"],
        padding=padding,
        font_size=font_size,
        font_weight=font_weight,
    )


def dashed_button_qss(
    selector: str,
    *,
    fg: str,
    border: str,
    hover_bg: str,
    bg: str = "transparent",
    hover_fg: str | None = None,
    hover_border: str | None = None,
    radius: str = "4px",
    padding: str = "8px 16px",
    font_size: int = 13,
    font_weight: str | None = None,
) -> str:
    """Build a reusable dashed text button QSS fragment."""
    c = get_theme_colors()
    return f"""
        QPushButton{selector} {{
            background-color: {bg};
            color: {fg};
            border: 1px dashed {border};
            border-radius: {radius};
            font-size: {font_size}px;
            font-weight: {font_weight or c["fw_normal"]};
            padding: {padding};
        }}
        QPushButton{selector}:hover {{
            background-color: {hover_bg};
            color: {hover_fg or fg};
            border-color: {hover_border or border};
        }}
    """


def input_button_qss(
    selector: str,
    *,
    padding: str = "4px 24px 4px 8px",
    font_size: int = 12,
    radius: str | None = None,
) -> str:
    """Build a reusable input-like selector button QSS fragment."""
    c = get_theme_colors()
    return f"""
        QPushButton{selector} {{
            background-color: {c["input_bg"]};
            border: 1px solid {c["input_border"]};
            border-radius: {radius or c["radius_sm"]};
            padding: {padding};
            text-align: left;
            color: {c["inputFg"]};
            font-size: {font_size}px;
        }}
        QPushButton{selector}:hover {{
            border-color: {c["buttonBlue"]};
        }}
        QPushButton{selector}:pressed {{
            background-color: {c["input_bg"]};
        }}
    """


def link_button_qss(selector: str, *, font_size: int = 13, padding: str = "2px 0") -> str:
    """Build a reusable link-style text button QSS fragment."""
    c = get_theme_colors()
    return f"""
        QPushButton{selector} {{
            background-color: transparent;
            border: none;
            border-bottom: 1px solid transparent;
            color: {c["buttonBlue"]};
            font-size: {font_size}px;
            text-align: left;
            padding: {padding};
        }}
        QPushButton{selector}:hover {{
            color: {c["buttonBlue"]};
            border-bottom: 1px solid {c["buttonBlue"]};
        }}
    """
