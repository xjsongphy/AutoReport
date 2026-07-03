"""Message cell — VS Code Copilot Chat style.

- User messages: right-aligned rounded bubble
- Agent messages: flat layout with avatar + markdown content + bottom copy
- Code blocks: monospace card with right-side copy icon (hover visible)
"""

import re
from functools import lru_cache

from PyQt6.QtCore import QEvent, QMargins, QObject, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QClipboard,
    QColor,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPen,
    QWheelEvent,
)

from ..scale import scaled_size
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
)

from .markdown_renderer import render_markdown
from ..theme import get_theme_colors
from .timeline import TIMELINE_RAIL_WIDTH, TimelineRail
from .ui_utils import create_isolated_context_menu, install_compact_tooltip, render_svg_icon
from ...utils.editor_context import parse_editor_context

TIMELINE_EVENT_ROW_HEIGHT = 34
COLLAPSE_LINE_LIMIT = 5
TIMELINE_TEXT_LEFT_GUTTER = 4
USER_BUBBLE_CONTENT_MARGINS = QMargins(10, 10, 10, 10)
_CODE_BLOCK_PATTERN = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

class _DisclosureArrow(QWidget):
    def __init__(self, expanded: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._expanded = expanded
        self.setFixedSize(10, 10)

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(get_theme_colors()["muted"]), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        cx = self.width() // 2
        cy = self.height() // 2
        if self._expanded:
            painter.drawLine(cx - 3, cy - 1, cx, cy + 2)
            painter.drawLine(cx, cy + 2, cx + 3, cy - 1)
        else:
            painter.drawLine(cx - 1, cy - 3, cx + 2, cy)
            painter.drawLine(cx + 2, cy, cx - 1, cy + 3)
        painter.end()


class _SummaryHeader(QWidget):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):  # noqa: N802
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class _DisclosureHeaderBar(QWidget):
    """Shared collapsible-row header: clickable host laying out ``[text][arrow][stretch]``.

    Used by both the think row (MessageRow) and tool-call groups so their
    disclosure arrows sit immediately to the right of the text — not pushed to
    the far edge — and align to the first text line. Callers keep working
    against the same label/arrow/arrow-host objects they already style, via the
    accessors below.
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        text_format: Qt.TextFormat = Qt.TextFormat.PlainText,
        contents_margins: tuple[int, int, int, int] = (0, 0, 0, 0),
        spacing: int = 4,
    ) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(*contents_margins)
        self._layout.setSpacing(spacing)

        self._text_label = QLabel(self)
        self._text_label.setObjectName("toolCallHeaderText")
        self._text_label.setTextFormat(text_format)
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        # Single-line (no wrap) + Preferred so the label takes its natural width
        # and the arrow follows the text; a trailing stretch pins the pair left.
        # Long summaries clip the same way the think row already does; full
        # content lives in the expanded body.
        self._text_label.setWordWrap(False)
        self._text_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        self._arrow = _DisclosureArrow(False, self)
        self._arrow_host = QWidget(self)
        self._arrow_host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        ahl = QVBoxLayout(self._arrow_host)
        ahl.setContentsMargins(0, 0, 0, 0)
        ahl.setSpacing(0)
        ahl.addWidget(self._arrow, 0, Qt.AlignmentFlag.AlignTop)

        self._layout.addWidget(self._text_label, 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addWidget(self._arrow_host, 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addStretch(1)

    def set_text(self, text: str) -> None:
        self._text_label.setText(text or "")

    def set_text_format(self, fmt: Qt.TextFormat) -> None:
        self._text_label.setTextFormat(fmt)

    def set_arrow_visible(self, visible: bool) -> None:
        self._arrow.setVisible(visible)

    def set_expanded(self, expanded: bool) -> None:
        self._arrow.set_expanded(expanded)
        self.align_arrow_to_first_line()

    def text_label(self) -> QLabel:
        return self._text_label

    def arrow(self) -> _DisclosureArrow:
        return self._arrow

    def arrow_host(self) -> QWidget:
        return self._arrow_host

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        """Insert a widget before the trailing stretch (kept inline, left of it)."""
        self._layout.insertWidget(self._layout.count() - 1, widget, stretch, Qt.AlignmentFlag.AlignTop)

    def align_arrow_to_first_line(self) -> None:
        """Center the arrow on the text's first line."""
        line_height = max(1, self._text_label.fontMetrics().height())
        arrow_height = max(1, self._arrow.height())
        top_offset = max(0, (line_height - arrow_height) // 2)
        self._arrow_host.layout().setContentsMargins(0, top_offset, 0, 0)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def click(self) -> None:
        self.clicked.emit()


class _ElidedLabel(QLabel):
    """Single-line label that preserves full text while displaying an elided copy."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._full_text = str(text or "")
        super().setText(self._full_text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(False)

    @property
    def full_text(self) -> str:
        return self._full_text

    def set_full_text(self, text: str) -> None:
        self._full_text = str(text or "")
        self._update_elided_text()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_elided_text()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._update_elided_text()

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = self.fontMetrics()
        return QSize(metrics.horizontalAdvance(self._full_text), metrics.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        metrics = self.fontMetrics()
        return QSize(20, metrics.height())

    def _update_elided_text(self) -> None:
        width = max(20, self.width())
        elided = self.fontMetrics().elidedText(
            self._full_text,
            Qt.TextElideMode.ElideMiddle,
            width,
        )
        if self.text() != elided:
            super().setText(elided)


def _parse_code_blocks(content: str) -> list[tuple[str, str | None]]:
    """Split content into segments: (text, None) for text, (code, language) for code."""
    parts: list[tuple[str, str | None]] = []
    last_end = 0
    for m in _CODE_BLOCK_PATTERN.finditer(content):
        if m.start() > last_end:
            parts.append((content[last_end:m.start()], None))
        lang = m.group(1) or None
        code = m.group(2).rstrip()
        parts.append((code, lang))
        last_end = m.end()
    if last_end < len(content):
        parts.append((content[last_end:], None))
    if not parts:
        parts.append((content, None))
    return parts


@lru_cache(maxsize=8)
def _copy_icon(color: str = "") -> QIcon:
    if not color:
        color = get_theme_colors()["muted"]
    return render_svg_icon("copy", QColor(color), size=16)


@lru_cache(maxsize=8)
def _file_chip_icon(color: str = "") -> QIcon:
    if not color:
        color = get_theme_colors()["muted"]
    return render_svg_icon("file", QColor(color), size=14)


def _parse_editor_context_block(content: str) -> tuple[str | None, str | None, str]:
    parsed = parse_editor_context(content)
    if not parsed.get("has_context"):
        return None, None, content
    return (
        parsed.get("chip_text"),
        parsed.get("chip_tooltip"),
        str(parsed.get("bubble_text") or ""),
    )


def _message_payload_from_content(content: str) -> dict[str, object]:
    parsed = parse_editor_context(content)
    if parsed.get("has_context"):
        return {
            "text": str(parsed.get("bubble_text") or ""),
            "editor_context": parsed.get("context"),
            "chip_text": parsed.get("chip_text"),
            "chip_tooltip": parsed.get("chip_tooltip"),
        }
    return {
        "text": str(content or ""),
        "editor_context": None,
        "chip_text": None,
        "chip_tooltip": None,
    }


def _plain_user_message_payload(text: str) -> dict[str, object]:
    return {
        "text": str(text or ""),
        "editor_context": None,
        "chip_text": None,
        "chip_tooltip": None,
    }


def _timeline_bottom_padding(widget: QWidget) -> int:
    return max(8, int(round(widget.fontMetrics().lineSpacing() * 0.5)))


def _plain_markdown_with_raw_map(raw_markdown: str) -> tuple[str, list[int]]:
    plain: list[str] = []
    raw_positions: list[int] = []
    i = 0
    line_start = True
    while i < len(raw_markdown):
        ch = raw_markdown[i]

        if raw_markdown.startswith("```", i):
            i += 3
            line_start = False
            continue

        if line_start:
            j = i
            while j < len(raw_markdown) and raw_markdown[j] in " \t":
                j += 1
            if j < len(raw_markdown) and raw_markdown[j] == "#":
                while j < len(raw_markdown) and raw_markdown[j] == "#":
                    j += 1
                if j < len(raw_markdown) and raw_markdown[j] == " ":
                    i = j + 1
                    line_start = False
                    continue
            if raw_markdown.startswith(("- ", "* ", "+ "), j):
                i = j + 2
                line_start = False
                continue

        if ch == "\\" and i + 1 < len(raw_markdown):
            i += 1
            ch = raw_markdown[i]

        matched_marker = False
        for marker in ("**", "__", "~~", "`", "*", "_"):
            if raw_markdown.startswith(marker, i):
                i += len(marker)
                matched_marker = True
                line_start = False
                break
        if matched_marker:
            continue

        plain.append("\n" if ch == "\r" else ch)
        raw_positions.append(i)
        line_start = ch == "\n"
        i += 1

    return "".join(plain), raw_positions


def _expand_inline_markdown_selection(raw_markdown: str, start: int, end: int) -> tuple[int, int]:
    for marker in ("```", "**", "__", "~~", "`", "*", "_"):
        changed = True
        while changed:
            changed = False
            if (
                start >= len(marker)
                and raw_markdown[start - len(marker):start] == marker
                and raw_markdown.find(marker, start, min(len(raw_markdown), end + len(marker))) >= 0
            ):
                start -= len(marker)
                changed = True
            if (
                end + len(marker) <= len(raw_markdown)
                and raw_markdown[end:end + len(marker)] == marker
                and raw_markdown.rfind(marker, max(0, start - len(marker)), end) >= 0
            ):
                end += len(marker)
                changed = True
    return start, end


_BLOCK_PREFIX_RE = re.compile(
    r"[ \t]*(?:>{1,}\s*|#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)"
)


def _expand_block_marker(raw: str, start: int, end: int) -> tuple[int, int]:
    """Grow a raw range to include the leading block marker of its first line.

    Rendered markdown drops line prefixes (``- ``, ``## ``, ``> ``, ``1. ``),
    so a selection that starts at a line's content beginning maps to a raw
    position just *after* the prefix \u2014 copying it would lose the prefix and
    yield non-markdown text.  When the selection begins exactly at that
    content start, pull ``start`` back over the prefix so the copied range is
    valid markdown.
    """
    line_start = raw.rfind("\n", 0, start) + 1  # 0 when no preceding newline
    m = _BLOCK_PREFIX_RE.match(raw, line_start)
    if m and start <= m.end():
        start = line_start
    # Preserve the trailing newline when the selection ends at a line boundary,
    # so multi-line copies keep their line breaks.
    if end < len(raw) and raw[end] == "\n":
        end += 1
    return start, end


def _raw_markdown_for_selected_text(raw_markdown: str, selected_text: str) -> str:
    selected = selected_text.replace("\u2029", "\n").replace("\u2028", "\n")
    if not selected:
        return raw_markdown

    plain, raw_positions = _plain_markdown_with_raw_map(raw_markdown)
    start_plain = plain.find(selected)
    if start_plain < 0:
        return raw_markdown

    end_plain = start_plain + len(selected)
    if end_plain <= start_plain or end_plain > len(raw_positions):
        return raw_markdown
    start_raw = raw_positions[start_plain]
    end_raw = raw_positions[end_plain - 1] + 1
    start_raw, end_raw = _expand_inline_markdown_selection(raw_markdown, start_raw, end_raw)
    start_raw, end_raw = _expand_block_marker(raw_markdown, start_raw, end_raw)
    return raw_markdown[start_raw:end_raw]


def _opaque_bounds(pixmap) -> QRect:
    image = pixmap.toImage()
    width = image.width()
    height = image.height()
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for y in range(height):
        for x in range(width):
            if QColor(image.pixelColor(x, y)).alpha() > 0:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return QRect()
    return QRect(min_x, min_y, (max_x - min_x) + 1, (max_y - min_y) + 1)


class _CodeBlockWidget(QWidget):
    """VS Code-style code block with right-side hover-visible copy icon."""

    def __init__(self, code: str, language: str | None, parent=None):
        super().__init__(parent)
        self._code = code
        self._language = language
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("codeBlockCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar with language label (left) and copy icon (right)
        header = QWidget(self)
        header.setObjectName("codeBlockHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 4, 4, 4)
        hl.setSpacing(8)

        lang_label = QLabel(self._language or "code")
        lang_label.setObjectName("codeBlockLang")
        hl.addWidget(lang_label)
        hl.addStretch()

        w, h = scaled_size(30, 24)
        self._copy_btn = QPushButton()
        self._copy_btn.setObjectName("codeBlockCopyBtn")
        self._copy_btn.setIcon(_copy_icon())
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setFixedSize(w, h)
        install_compact_tooltip(self._copy_btn, "Copy")
        self._copy_btn.clicked.connect(self._copy)
        hl.addWidget(self._copy_btn)

        layout.addWidget(header)

        # Code content
        code_label = QLabel(self._code)
        code_label.setObjectName("codeBlockContent")
        code_label.setWordWrap(True)
        code_label.setTextFormat(Qt.TextFormat.PlainText)
        code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        code_label.setContentsMargins(12, 0, 12, 10)
        layout.addWidget(code_label)

    def _copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._code, QClipboard.Mode.Clipboard)


class _NestedScrollPlainTextEdit(QPlainTextEdit):
    """Prevent wheel scroll from chaining into the outer messages area."""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        super().wheelEvent(event)
        event.accept()


class _FadeMask(QWidget):
    def __init__(self, base_color: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._base_color = QColor(base_color)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_base_color(self, color: str) -> None:
        self._base_color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        gradient = QLinearGradient(0, 0, 0, max(1, self.height()))
        top = QColor(self._base_color)
        bottom = QColor(self._base_color)
        top.setAlpha(0)
        bottom.setAlpha(255)
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)
        painter.fillRect(self.rect(), gradient)


class _ExpandableContentWidget(QWidget):
    toggled = pyqtSignal(bool)
    overflow_changed = pyqtSignal()

    def __init__(
        self,
        label: QLabel,
        *,
        fade_color: str,
        line_limit: int = COLLAPSE_LINE_LIMIT,
        collapsed_text: str | None = None,
        expanded_text: str | None = None,
        clamp_collapsed: bool = True,
        overlay_host: QWidget | None = None,
        toggle_host: QWidget | None = None,
        toggle_host_margins: QMargins | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._line_limit = max(1, int(line_limit))
        self._expanded = False
        self._self_hovered = False
        self._host_hovered = False
        self._has_overflow = False
        self._max_content_width: int | None = None
        self._clamp_collapsed = clamp_collapsed
        self._overlay_host = overlay_host or self
        self._toggle_host = toggle_host or self._overlay_host
        self._toggle_host_margins = toggle_host_margins or QMargins(0, 0, 0, 0)
        self._collapsed_text = str(label.text() if collapsed_text is None else collapsed_text)
        default_expanded = self._collapsed_text if expanded_text is None else expanded_text
        self._expanded_text = str(default_expanded or "")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._label = label
        self._label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._label.setMinimumWidth(0)
        self._layout.addWidget(self._label)

        self._fade = _FadeMask(fade_color, self._overlay_host)
        self._fade.setObjectName("messageFadeMask")
        self._fade.hide()

        self._toggle_btn = QPushButton("Show More", self._toggle_host)
        self._toggle_btn.setObjectName("messageExpandBtn")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_from_button)
        self._toggle_btn.hide()

        self.setMouseTracking(True)
        if self._overlay_host is not self:
            self._overlay_host.setMouseTracking(True)
            self._overlay_host.installEventFilter(self)
        if self._toggle_host not in {self, self._overlay_host}:
            self._toggle_host.setMouseTracking(True)
            self._toggle_host.installEventFilter(self)
        self._refresh_clamp()

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self._self_hovered = True
        self._update_toggle_visibility()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._self_hovered = False
        self._update_toggle_visibility()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_clamp()
        self._position_overlay()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched in {self._overlay_host, self._toggle_host}:
            if event.type() in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
                self._host_hovered = True
                self._update_toggle_visibility()
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                self._host_hovered = False
                self._update_toggle_visibility()
            elif event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
                self._position_overlay()
        return super().eventFilter(watched, event)

    def setMaximumContentWidth(self, width: int) -> None:
        width = max(40, int(width))
        if self._max_content_width == width:
            return
        self._max_content_width = width
        self._label.setMaximumWidth(width)
        self._refresh_clamp()

    def set_text(self, text: str) -> None:
        value = str(text or "")
        self._collapsed_text = value
        self._expanded_text = value
        self._refresh_clamp()

    def set_collapsed_text(self, text: str) -> None:
        self._collapsed_text = str(text or "")
        self._refresh_clamp()

    def set_expanded_text(self, text: str) -> None:
        self._expanded_text = str(text or "")
        self._refresh_clamp()

    def set_texts(self, collapsed_text: str, expanded_text: str, *, clamp_collapsed: bool) -> None:
        self._collapsed_text = str(collapsed_text or "")
        self._expanded_text = str(expanded_text or "")
        self._clamp_collapsed = bool(clamp_collapsed)
        self._refresh_clamp()

    def label(self) -> QLabel:
        return self._label

    def is_expanded(self) -> bool:
        return self._expanded

    def has_overflow(self) -> bool:
        return self._has_overflow

    def can_toggle(self) -> bool:
        return self._has_distinct_expanded_text() or self._has_overflow or self._expanded

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if self._expanded == expanded:
            self._refresh_clamp()
            return
        self._expanded = expanded
        self._refresh_clamp()

    def _toggle_from_button(self) -> None:
        if not self.can_toggle():
            return
        self._expanded = not self._expanded
        self._refresh_clamp()
        self.toggled.emit(self._expanded)

    def _has_distinct_expanded_text(self) -> bool:
        return bool(self._expanded_text) and self._expanded_text != self._collapsed_text

    def _display_text(self) -> str:
        if self._expanded and self._has_distinct_expanded_text():
            return self._expanded_text
        return self._collapsed_text

    def _collapsed_height(self) -> int:
        margins = self._label.contentsMargins()
        return (
            self._label.fontMetrics().height() * self._line_limit
            + margins.top()
            + margins.bottom()
            + 2
        )

    def _text_height_for_width(self, width: int) -> int:
        text = self._display_text()
        margins = self._label.contentsMargins()
        content_width = max(1, width - margins.left() - margins.right())
        flags = int(Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextExpandTabs)
        rect = self._label.fontMetrics().boundingRect(
            QRect(0, 0, content_width, 100000),
            flags,
            text,
        )
        return rect.height() + margins.top() + margins.bottom()

    def _label_width(self) -> int:
        width = self._max_content_width if self._max_content_width is not None else self.width()
        width = max(40, int(width))
        if not self._clamp_collapsed and self.can_toggle():
            width -= self._toggle_btn.sizeHint().width() + 8
        return max(40, width)

    def _refresh_clamp(self) -> None:
        display_text = self._display_text()
        if self._label.text() != display_text:
            self._label.setText(display_text)

        label_width = self._label_width()
        old_overflow = self._has_overflow
        if self._clamp_collapsed and not self._has_distinct_expanded_text():
            natural_height = max(
                self._text_height_for_width(label_width),
                self._label.heightForWidth(label_width),
            )
            collapsed_height = self._collapsed_height()
            self._has_overflow = natural_height > (collapsed_height + 2)
            if self._expanded or not self._has_overflow:
                self._label.setMinimumHeight(0)
                self._label.setMaximumHeight(16777215)
            else:
                self._label.setMinimumHeight(collapsed_height)
                self._label.setMaximumHeight(collapsed_height)
        else:
            self._has_overflow = False
            self._label.setMinimumHeight(0)
            self._label.setMaximumHeight(16777215)
        self._label.setMaximumWidth(label_width)

        self._fade.setVisible(self._clamp_collapsed and self._has_overflow and not self._expanded)
        self._toggle_btn.setText("Show less" if self._expanded else "Show More")
        self._update_toggle_visibility()
        self._position_overlay()
        self.updateGeometry()
        if old_overflow != self._has_overflow:
            self.overflow_changed.emit()

    def _update_toggle_visibility(self) -> None:
        self._toggle_btn.setVisible((self._self_hovered or self._host_hovered) and self.can_toggle())

    def _position_overlay(self) -> None:
        overlay_rect = self._overlay_host.rect()
        fade_height = max(28, self._label.fontMetrics().lineSpacing() * 2)
        fade_bottom = overlay_rect.height()
        self._fade.setGeometry(
            0,
            max(0, fade_bottom - fade_height),
            overlay_rect.width(),
            fade_height,
        )
        self._toggle_btn.adjustSize()
        btn_size = self._toggle_btn.size()
        toggle_host_rect = self._toggle_host.rect()
        btn_x = max(
            self._toggle_host_margins.left(),
            toggle_host_rect.width() - self._toggle_host_margins.right() - btn_size.width(),
        )
        btn_y = max(
            self._toggle_host_margins.top(),
            toggle_host_rect.height() - self._toggle_host_margins.bottom() - btn_size.height(),
        )
        self._toggle_btn.move(
            btn_x,
            btn_y,
        )
        self._fade.raise_()
        self._toggle_btn.raise_()


class MessageRow(QWidget):
    """Render a chat message matching VS Code Copilot Chat's visual style."""

    # Signal emitted when user clicks edit button on their message
    edit_requested = pyqtSignal(str)

    # Signal emitted when user saves an edit (content, row_widget)
    edit_saved = pyqtSignal(str, object)

    # Signal emitted when user cancels an edit
    edit_cancelled = pyqtSignal()

    # Signal emitted when user requests rollback to the checkpoint before this row.
    rollback_requested = pyqtSignal(str, object)

    # Signal emitted when a collapsible row is expanded/collapsed.
    expanded_changed = pyqtSignal()

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str = "",
        is_coordination: bool = False,
        display_mode: str = "agent_markdown",
        bubble_align: str = "left",
        bubble_title: str | None = None,
        bubble_on_timeline: bool = False,
        bubble_collapsible: bool = True,
        allow_edit: bool | None = None,
        agent_name: str = "Agent",
        agent_chain_prev: bool = False,
        agent_chain_next: bool = False,
        message_id: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._role = role
        self._content = content
        self._message_payload = _message_payload_from_content(content)
        self._timestamp = timestamp
        self._is_coordination = is_coordination
        if display_mode == "agent_markdown" and role == "user":
            display_mode = "bubble"
        if display_mode == "bubble" and bubble_align == "left" and role == "user":
            bubble_align = "right"
        if allow_edit is None:
            allow_edit = role == "user" and display_mode == "bubble" and bubble_align == "right"
        self._display_mode = display_mode
        self._bubble_align = bubble_align
        self._bubble_title = bubble_title
        self._bubble_on_timeline = bubble_on_timeline
        self._bubble_collapsible = bubble_collapsible
        self._allow_edit = allow_edit
        self._agent_name = agent_name
        self._complete = False
        self._agent_content_layout: QVBoxLayout | None = None
        self._user_footer: QWidget | None = None
        self._editable = False
        self._user_bubble_container: QWidget | None = None
        self._expanded = False
        self._wrapping_labels: list[QLabel] = []
        self._raw_markdown_labels: dict[QLabel, str] = {}
        self._agent_chain_prev = agent_chain_prev
        self._agent_chain_next = agent_chain_next
        self._message_id = message_id
        self._timeline_rail: TimelineRail | None = None
        self._bubble_header: QWidget | None = None
        self._bubble_arrow_widget: _DisclosureArrow | None = None
        self._bubble_arrow_host: QWidget | None = None
        self._bubble_title_label: QLabel | None = None
        self._summary_header: QWidget | None = None
        self._summary_arrow_widget: _DisclosureArrow | None = None
        self._summary_arrow_host: QWidget | None = None
        self._summary_text_label: QLabel | None = None
        self._detail_label: QLabel | None = None
        self._detail_widget: QWidget | None = None
        self._is_thinking_row = False
        self._user_actions_visible = False
        self._editing = False  # Track if in edit mode
        self._original_text_widget: QWidget | None = None  # Store original widget when editing
        self._edit_widget: QPlainTextEdit | None = None  # Edit mode widget
        self._save_btn: QPushButton | None = None  # Save button in edit mode
        self._cancel_btn: QPushButton | None = None  # Cancel button in edit mode
        self._edit_actions_widget: QWidget | None = None
        self._edit_bubble_widget: QWidget | None = None
        self._user_bubble_widget: QWidget | None = None
        self._user_bubble_layout: QVBoxLayout | None = None
        self._context_chip_widget: QWidget | None = None
        self._context_chip_label: QLabel | None = None
        self._checkpoint_id: str | None = None
        self._bubble_text = str(self._message_payload["text"] or "")
        self._context_chip_text = self._message_payload["chip_text"]
        self._context_chip_tooltip = self._message_payload["chip_tooltip"]
        self._body_content_widget: _ExpandableContentWidget | None = None
        self._setup_ui()
        self._setup_hover_handler()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        outer = QWidget(self)
        outer.setObjectName("msgOuterContainer")
        outer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._outer_layout = QVBoxLayout(outer)
        self._outer_layout.setContentsMargins(16, 0, 16, 0)
        self._outer_layout.setSpacing(0)

        if self._is_coordination:
            coord = QLabel("[Main Agent → Sub Agent]")
            coord.setObjectName("msgCoordination")
            self._outer_layout.addWidget(coord)

        if self._uses_bubble_layout() and self._bubble_align == "right":
            self._outer_layout.setContentsMargins(16, 6, 16, 6)
            row = QWidget(outer)
            row.setObjectName("userMessageRow")
            row.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)
            rl.addStretch(1)

            self._user_bubble_container = QWidget(row)
            self._user_bubble_container.setObjectName("userMessageBubbleContainer")
            self._user_bubble_container.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred,
            )
            bcl = QVBoxLayout(self._user_bubble_container)
            bcl.setContentsMargins(0, 0, 0, 0)
            bcl.setSpacing(0)

            bubble = QWidget(self._user_bubble_container)
            bubble.setObjectName("userMessageBubble")
            bubble.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            bl = QVBoxLayout(bubble)
            bl.setContentsMargins(USER_BUBBLE_CONTENT_MARGINS)
            bl.setSpacing(0)
            self._user_bubble_widget = bubble
            self._user_bubble_layout = bcl

            self._populate_bubble_content(bl, bubble_type="right")

            bcl.addWidget(bubble)

            # Footer with edit/copy buttons (hover visible, right-aligned)
            self._user_footer = QWidget(self._user_bubble_container)
            self._user_footer.setObjectName("userMsgFooter")
            fl = QHBoxLayout(self._user_footer)
            fl.setContentsMargins(0, 2, 0, 4)
            fl.setSpacing(2)

            fl.addStretch()

            w, h = scaled_size(30, 24)
            self._edit_btn = QPushButton("✎")
            self._edit_btn.setObjectName("userEditBtn")
            self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            install_compact_tooltip(self._edit_btn, "Edit & Resend")
            self._edit_btn.setFixedSize(w, h)
            self._edit_btn.clicked.connect(self._request_edit)
            fl.addWidget(self._edit_btn)

            self._user_copy_btn = QPushButton()
            self._user_copy_btn.setObjectName("userCopyBtn")
            self._user_copy_btn.setIcon(_copy_icon())
            self._user_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._user_copy_btn.setFixedSize(w, h)
            install_compact_tooltip(self._user_copy_btn, "Copy")
            self._user_copy_btn.clicked.connect(self._copy_content)
            fl.addWidget(self._user_copy_btn)

            bcl.addWidget(self._user_footer)
            self._set_user_actions_visible(False)

            rl.addWidget(self._user_bubble_container, 0, Qt.AlignmentFlag.AlignHCenter)
            rl.addStretch(1)
            self._outer_layout.addWidget(row)
        else:
            row = QWidget(outer)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)

            if self._uses_timeline():
                self._timeline_rail = TimelineRail(parent=row)
                rl.addWidget(self._timeline_rail, 0, Qt.AlignmentFlag.AlignLeft)

            self._agent_content_layout = QVBoxLayout()
            self._agent_content_layout.setContentsMargins(
                0,
                0,
                0,
                _timeline_bottom_padding(self),
            )
            self._agent_content_layout.setSpacing(0)
            rl.addLayout(self._agent_content_layout, 1)
            self._outer_layout.addWidget(row)
            if self._uses_bubble_layout():
                bubble_host = QWidget(row)
                bubble_host.setObjectName("leftBubbleHost")
                host_layout = QVBoxLayout(bubble_host)
                host_layout.setContentsMargins(0, 0, 0, _timeline_bottom_padding(self))
                host_layout.setSpacing(0)
                bubble = QWidget(bubble_host)
                bubble.setObjectName("userMessageBubble")
                bubble.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
                bubble_layout = QVBoxLayout(bubble)
                bubble_layout.setContentsMargins(USER_BUBBLE_CONTENT_MARGINS)
                bubble_layout.setSpacing(0)
                self._user_bubble_widget = bubble
                self._populate_bubble_content(bubble_layout, bubble_type="left")
                host_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
                self._agent_content_layout.addWidget(bubble_host)
                self._update_left_bubble_width()
            else:
                self._rebuild_agent_content()
            self._update_agent_chain()

        layout.addWidget(outer)

    def _populate_bubble_content(self, layout: QVBoxLayout, *, bubble_type: str) -> None:
        if bubble_type == "right" and self._context_chip_text:
            layout.addWidget(
                self._build_context_chip(self._context_chip_text),
                0,
                Qt.AlignmentFlag.AlignLeft,
            )
            if self._bubble_text:
                layout.addSpacing(8)
        text = QLabel(self._bubble_text)
        text.setObjectName("userMessageText")
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        text.installEventFilter(self)
        c = get_theme_colors()
        text.setStyleSheet(f"color: {c['editor_fg']}; background-color: transparent;")
        collapsed_text, expanded_text, clamp_collapsed = self._bubble_text_strategy()
        self._body_content_widget = self._build_expandable_content_widget(
            text,
            fade_color=c["bubble_bg"],
            collapsed_text=collapsed_text,
            expanded_text=expanded_text,
            clamp_collapsed=clamp_collapsed,
            overlay_host=None,
            toggle_host=self._user_bubble_widget,
            toggle_host_margins=layout.contentsMargins(),
        )
        self._body_content_widget.toggled.connect(self._on_bubble_expanded_changed)
        self._body_content_widget.overflow_changed.connect(self._refresh_bubble_header)
        layout.addWidget(self._body_content_widget)

    def _build_context_chip(self, chip_text: str) -> QWidget:
        chip = QWidget(self)
        chip.setObjectName("userContextChip")
        chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        chip_layout = QHBoxLayout(chip)
        chip_layout.setContentsMargins(10, 0, 10, 0)
        chip_layout.setSpacing(6)
        chip.setFixedHeight(30)

        icon = render_svg_icon("code-context", QColor(get_theme_colors()["muted"]), size=16).pixmap(16, 16)
        icon_label = QLabel(chip)
        icon_label.setObjectName("userContextChipIcon")
        icon_label.setFixedSize(16, 16)
        icon_label.setPixmap(icon)
        icon_label.setScaledContents(False)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        text_label = _ElidedLabel(chip_text, chip)
        text_label.setObjectName("userContextChipText")
        text_label.installEventFilter(self)
        text_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        text_label.setMinimumHeight(18)
        text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text_label.setContentsMargins(0, 0, 0, 0)
        if self._context_chip_tooltip:
            text_label.setToolTip(self._context_chip_tooltip)
            chip.setToolTip(self._context_chip_tooltip)
        chip_layout.addWidget(text_label, 1, Qt.AlignmentFlag.AlignVCenter)
        self._context_chip_widget = chip
        self._context_chip_label = text_label
        self._sync_context_chip_width()
        return chip

    def _clear_agent_content(self) -> None:
        self._wrapping_labels = []
        self._raw_markdown_labels = {}
        self._body_content_widget = None
        self._bubble_header = None
        self._bubble_arrow_widget = None
        self._bubble_arrow_host = None
        self._bubble_title_label = None
        self._summary_header = None
        self._summary_arrow_widget = None
        self._summary_arrow_host = None
        self._summary_text_label = None
        self._detail_label = None
        self._detail_widget = None
        if self._agent_content_layout is None:
            return
        while self._agent_content_layout.count():
            item = self._agent_content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                inner = item.layout()
                while inner.count():
                    inner_item = inner.takeAt(0)
                    if inner_item.widget():
                        inner_item.widget().deleteLater()

    def _rebuild_agent_content(self) -> None:
        self._clear_agent_content()
        if self._agent_content_layout is None:
            return
        if self._display_mode == "thought":
            self._agent_content_layout.addWidget(self._build_summary_widget())
            self._detail_widget = self._build_detail_widget()
            self._agent_content_layout.addWidget(self._detail_widget)
            self._detail_widget.setVisible(self._expanded and self._has_detail())
            self._apply_text_width_constraints()
            self._sync_timeline_dot_alignment()
            return

        text_label = self._build_agent_markdown_label(self._content)
        self._agent_content_layout.addWidget(text_label)
        self._apply_text_width_constraints()
        self._sync_timeline_dot_alignment()

    def _build_agent_markdown_label(self, raw_markdown: str) -> QLabel:
        label = QLabel(render_markdown(raw_markdown))
        label.setObjectName("agentMessageText")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(False)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        label.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        label.setContentsMargins(0, 2, 0, 6)
        label.setMinimumWidth(0)
        label.installEventFilter(self)
        self._wrapping_labels.append(label)
        self._raw_markdown_labels[label] = raw_markdown
        return label

    def append_content(self, delta: str) -> None:
        """Append streaming text delta and rebuild content area."""
        if not delta:
            return
        self._content += delta
        self._rebuild_agent_content()
        self._apply_text_width_constraints()

    def set_agent_chain(self, prev_link: bool, next_link: bool) -> None:
        self._agent_chain_prev = prev_link
        self._agent_chain_next = next_link
        self._update_agent_chain()

    def _update_agent_chain(self) -> None:
        if self._timeline_rail is not None:
            self._timeline_rail.set_chain(self._agent_chain_prev, self._agent_chain_next)

    def _has_detail(self) -> bool:
        return bool(self._content)

    def _build_summary_widget(self) -> QWidget:
        widget = _DisclosureHeaderBar(
            self,
            text_format=Qt.TextFormat.PlainText,
            contents_margins=(0, 2, 0, 6),
            spacing=4,
        )
        widget.setMinimumHeight(TIMELINE_EVENT_ROW_HEIGHT)
        widget.setObjectName("toolCallHeader")
        self._summary_header = widget
        self._summary_text_label = widget.text_label()
        self._summary_arrow_widget = widget.arrow()
        self._summary_arrow_host = widget.arrow_host()
        widget.set_text(self._bubble_title or "")
        widget.set_arrow_visible(self._bubble_collapsible and self._has_detail())
        self._sync_summary_arrow_alignment()
        self._sync_timeline_dot_alignment()
        widget.setCursor(
            Qt.CursorShape.PointingHandCursor
            if (self._bubble_collapsible and self._has_detail())
            else Qt.CursorShape.ArrowCursor
        )
        widget.clicked.connect(self._toggle_summary)
        self._refresh_summary_header()
        return widget

    def _build_detail_widget(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(TIMELINE_TEXT_LEFT_GUTTER, 2, 0, 0)
        layout.setSpacing(0)
        label = self._build_agent_markdown_label(self._content or "")
        self._detail_label = label
        layout.addWidget(label)
        return widget

    def _toggle_summary(self) -> None:
        if not (self._bubble_collapsible and self._has_detail()):
            return
        self._expanded = not self._expanded
        if self._detail_widget is not None:
            self._detail_widget.setVisible(self._expanded)
        self._refresh_summary_header()
        self.expanded_changed.emit()

    def set_summary_text(self, summary: str) -> None:
        self._bubble_title = summary
        self._refresh_summary_header()

    def set_detail_text(self, detail: str) -> None:
        self._bubble_text = detail or ""
        self._content = detail or ""
        if self._detail_label is not None:
            self._detail_label.setText(render_markdown(detail or ""))
            self._raw_markdown_labels[self._detail_label] = detail or ""
            self._apply_text_width_constraints()
        elif self._agent_content_layout is not None:
            expanded = self._expanded
            self._rebuild_agent_content()
            self._expanded = expanded
        if self._detail_widget is not None:
            self._detail_widget.setVisible(self._expanded and self._has_detail())
        self._refresh_summary_header()

    def _refresh_summary_header(self) -> None:
        can_expand = self._bubble_collapsible and self._has_detail()
        if self._summary_text_label is not None:
            self._summary_text_label.setText(self._bubble_title or "")
        if self._summary_arrow_widget is not None:
            self._summary_arrow_widget.setVisible(can_expand)
            self._summary_arrow_widget.set_expanded(self._expanded)
        self._sync_summary_arrow_alignment()
        self._sync_timeline_dot_alignment()
        if self._summary_header is not None:
            self._summary_header.setCursor(
                Qt.CursorShape.PointingHandCursor if can_expand else Qt.CursorShape.ArrowCursor
            )
        self._apply_thinking_text_style()

    def _build_bubble_header(self) -> QWidget:
        widget = _SummaryHeader(self)
        if self._bubble_on_timeline:
            # Keep timeline events on a fixed vertical pitch.
            widget.setMinimumHeight(TIMELINE_EVENT_ROW_HEIGHT)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._bubble_header = widget
        widget.setObjectName("toolCallHeader" if self._display_mode == "thought" else "msgSummaryHeader")

        self._bubble_arrow_widget = _DisclosureArrow(self._expanded, widget)
        self._bubble_arrow_host = QWidget(widget)
        self._bubble_arrow_host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        ahl = QVBoxLayout(self._bubble_arrow_host)
        ahl.setContentsMargins(0, 0, 0, 0)
        ahl.setSpacing(0)
        ahl.addWidget(self._bubble_arrow_widget, 0, Qt.AlignmentFlag.AlignTop)
        left_margin = 4 if self._bubble_on_timeline else 0
        layout.setContentsMargins(left_margin, 4, 0, 6)

        self._bubble_title_label = QLabel(self._bubble_title or "", widget)
        self._bubble_title_label.setObjectName("toolCallHeaderText")
        self._bubble_title_label.setTextFormat(Qt.TextFormat.PlainText)
        self._bubble_title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._bubble_title_label.setWordWrap(True)
        self._bubble_title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._bubble_title_label.setMinimumWidth(0)
        layout.addWidget(self._bubble_title_label, 1, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._bubble_arrow_host, 0, Qt.AlignmentFlag.AlignTop)
        self._sync_bubble_arrow_alignment()
        self._sync_timeline_dot_alignment()

        widget.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._can_toggle_bubble()
            else Qt.CursorShape.ArrowCursor
        )
        widget.clicked.connect(self._toggle_bubble)
        self._refresh_bubble_header()
        return widget

    def _toggle_bubble(self) -> None:
        if not self._can_toggle_bubble():
            return
        self._set_bubble_expanded(not self._expanded)

    def _set_bubble_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        if self._body_content_widget is not None:
            self._body_content_widget.set_expanded(self._expanded)
        self._refresh_bubble_header()
        self.expanded_changed.emit()

    def set_bubble_title(self, title: str | None) -> None:
        if self._display_mode == "thought":
            self.set_summary_text(title or "")
            return
        self._bubble_title = title
        if self._body_content_widget is not None:
            collapsed_text, expanded_text, clamp_collapsed = self._bubble_text_strategy()
            self._body_content_widget.set_texts(
                collapsed_text,
                expanded_text,
                clamp_collapsed=clamp_collapsed,
            )
        self._refresh_bubble_header()

    def set_bubble_content(self, content: str) -> None:
        if self._display_mode == "thought":
            self.set_detail_text(content)
            return
        self._bubble_text = content or ""
        self._content = content or ""
        if self._body_content_widget is not None:
            collapsed_text, expanded_text, clamp_collapsed = self._bubble_text_strategy()
            self._body_content_widget.set_texts(
                collapsed_text,
                expanded_text,
                clamp_collapsed=clamp_collapsed,
            )
            self._apply_text_width_constraints()
        self._refresh_bubble_header()

    def _on_bubble_expanded_changed(self, expanded: bool) -> None:
        self._expanded = expanded
        self._refresh_bubble_header()

    def _refresh_bubble_header(self) -> None:
        self._sync_timeline_dot_alignment()
        self._apply_thinking_text_style()

    def _can_toggle_bubble(self) -> bool:
        if not self._bubble_collapsible:
            return False
        if self._body_content_widget is None:
            return False
        return self._body_content_widget.can_toggle()

    def _align_arrow_to_first_line(self, arrow_host, text_label, arrow_widget) -> None:
        """Align disclosure arrow center to the first text line center."""
        if arrow_host is None or text_label is None or arrow_widget is None:
            return
        line_height = max(1, text_label.fontMetrics().height())
        arrow_height = max(1, arrow_widget.height())
        top_offset = max(0, (line_height - arrow_height) // 2)
        host_layout = arrow_host.layout()
        if isinstance(host_layout, QVBoxLayout):
            host_layout.setContentsMargins(0, top_offset, 0, 0)

    def _sync_summary_arrow_alignment(self) -> None:
        self._align_arrow_to_first_line(
            self._summary_arrow_host, self._summary_text_label, self._summary_arrow_widget
        )

    def _sync_bubble_arrow_alignment(self) -> None:
        self._align_arrow_to_first_line(
            self._bubble_arrow_host, self._bubble_title_label, self._bubble_arrow_widget
        )

    @staticmethod
    def _first_line_center_y(top_offset: int, line_height: int) -> float:
        return float(top_offset + (max(1, line_height) / 2.0))

    def _sync_timeline_dot_alignment(self) -> None:
        """Align timeline dot center to the first visible text line center."""
        if self._timeline_rail is None:
            return
        if self._summary_text_label is not None and self._summary_header is not None:
            metrics = self._summary_text_label.fontMetrics()
            line_height = metrics.height()
            margins = self._summary_header.layout().contentsMargins() if self._summary_header.layout() else None
            top = margins.top() if margins is not None else 0
            self._timeline_rail.set_dot_center_y(self._first_line_center_y(top, line_height))
            return
        if self._bubble_title_label is not None and self._bubble_header is not None:
            metrics = self._bubble_title_label.fontMetrics()
            line_height = metrics.height()
            margins = self._bubble_header.layout().contentsMargins() if self._bubble_header.layout() else None
            top = margins.top() if margins is not None else 0
            self._timeline_rail.set_dot_center_y(self._first_line_center_y(top, line_height))
            return
        if self._body_content_widget is not None:
            label = self._body_content_widget.label()
            metrics = label.fontMetrics()
            line_height = metrics.height()
            top = label.contentsMargins().top()
            self._timeline_rail.set_dot_center_y(self._first_line_center_y(top, line_height))
            return
        # Plain agent messages: align to first markdown label first line.
        if self._wrapping_labels:
            label = self._wrapping_labels[0]
            metrics = label.fontMetrics()
            line_height = metrics.height()
            top = label.contentsMargins().top()
            self._timeline_rail.set_dot_center_y(self._first_line_center_y(top, line_height))
            return
        self._timeline_rail.set_dot_center_y(None)

    def set_thinking_row_style(self, enabled: bool) -> None:
        self._is_thinking_row = enabled
        self._apply_thinking_text_style()

    def _apply_thinking_text_style(self) -> None:
        color = get_theme_colors()["muted"] if self._is_thinking_row else ""
        sheet = f"color: {color}; background-color: transparent;" if color else ""
        for label in (
            self._summary_text_label,
            self._detail_label,
            self._bubble_title_label,
        ):
            if label is not None:
                label.setStyleSheet(sheet)
        if self._body_content_widget is not None:
            self._body_content_widget.label().setStyleSheet(sheet)

    def mark_complete(self) -> None:
        """Mark streaming complete — enable hover-triggered actions."""
        self._complete = True
        if hasattr(self, "_footer"):
            self._footer.setVisible(True)
            self._set_agent_actions_visible(False)
        if self._user_footer:
            self._user_footer.setVisible(True)
            self._set_user_actions_visible(False)

    def set_editable(self, editable: bool) -> None:
        """Set whether this user message can be edited.

        Only the most recent user message should be editable.
        """
        if not self._allow_edit:
            return
        self._editable = editable
        if self._complete and self._user_footer:
            self._set_user_actions_visible(False)

    def _request_edit(self) -> None:
        """Enter edit mode for this user message."""
        if self._allow_edit and self._editable:
            self.enter_edit_mode()

    def enter_edit_mode(self) -> None:
        """Show a dedicated edit bubble in-place."""
        if not self._is_outbound_message() or self._editing:
            return

        self._editing = True
        self._set_user_actions_visible(False)  # Hide edit/copy buttons
        if self._user_bubble_container is None or self._user_bubble_layout is None:
            self._editing = False
            return

        c = get_theme_colors()
        edit_style = (
            f"QPlainTextEdit#userMessageEdit {{"
            f"color: {c['editor_fg']};"
            f"background-color: {c['edit_bubble_bg']};"
            f"border: 1px solid {c['edit_bubble_border']};"
            f"border-radius: 4px; padding: 4px;"
            f"}}"
        )

        edit_content = self._bubble_text

        edit_bubble = QWidget(self._user_bubble_container)
        edit_bubble.setObjectName("userEditBubble")
        edit_bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        ebl = QVBoxLayout(edit_bubble)
        ebl.setContentsMargins(USER_BUBBLE_CONTENT_MARGINS)
        ebl.setSpacing(0)

        edit = _NestedScrollPlainTextEdit(edit_content or "")
        edit.setObjectName("userMessageEdit")
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        edit.setStyleSheet(edit_style)
        edit.installEventFilter(self)
        edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        edit.document().setDocumentMargin(4.0)
        edit.viewport().setStyleSheet(f"background-color: {c['edit_bubble_bg']};")
        pal = edit.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(c["edit_bubble_bg"]))
        pal.setColor(QPalette.ColorRole.Text, QColor(c["editor_fg"]))
        edit.setPalette(pal)
        self._edit_widget = edit
        ebl.addWidget(edit)

        actions = QWidget(edit_bubble)
        actions.setObjectName("userEditActions")
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 6, 0, 0)
        al.setSpacing(6)
        al.addStretch()

        w, h = scaled_size(52, 24)
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setObjectName("userCancelBtn")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setFixedSize(w, h)
        self._cancel_btn.clicked.connect(self._cancel_edit)
        al.addWidget(self._cancel_btn)

        self._save_btn = QPushButton("发送")
        self._save_btn.setObjectName("userSaveBtn")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setFixedSize(w, h)
        self._save_btn.clicked.connect(self._save_edit)
        al.addWidget(self._save_btn)

        ebl.addWidget(actions)
        self._edit_actions_widget = actions
        self._edit_bubble_widget = edit_bubble

        if self._user_bubble_widget:
            self._user_bubble_widget.setVisible(False)
        if self._user_footer:
            self._user_footer.setVisible(False)
        self._user_bubble_layout.insertWidget(1, edit_bubble)

        if self._user_bubble_container is not None:
            self._user_bubble_container.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred,
            )
            self._user_bubble_container.setMinimumWidth(max(80, self.width() - 32))
            self._user_bubble_container.setMaximumWidth(max(80, self.width() - 32))
        self._update_edit_widget_height()
        self._edit_widget.setFocus()
        self._edit_widget.textChanged.connect(self._update_edit_widget_height)

    def _save_edit(self) -> None:
        """Save the edited content and emit signal."""
        if not self._editing or not self._edit_widget:
            return

        new_content = self._edit_widget.toPlainText()
        self._content = new_content  # Update stored content
        self._message_payload = _plain_user_message_payload(new_content)
        self._bubble_text = new_content
        self._context_chip_text = None
        self._context_chip_tooltip = None
        self.exit_edit_mode()
        self.edit_saved.emit(new_content, self)

    def _cancel_edit(self) -> None:
        """Cancel editing and restore original content."""
        if not self._editing:
            return
        self.exit_edit_mode()
        self.edit_cancelled.emit()

    def exit_edit_mode(self) -> None:
        """Restore original text widget and footer buttons."""
        if not self._editing:
            return

        self._editing = False

        if self._edit_widget:
            self._edit_widget.removeEventFilter(self)
            self._edit_widget.setParent(None)
            self._edit_widget.deleteLater()
            self._edit_widget = None

        if self._edit_actions_widget:
            self._edit_actions_widget.setParent(None)
            self._edit_actions_widget.deleteLater()
            self._edit_actions_widget = None

        if self._edit_bubble_widget:
            self._edit_bubble_widget.setParent(None)
            self._edit_bubble_widget.deleteLater()
            self._edit_bubble_widget = None

        if self._user_bubble_widget:
            self._user_bubble_widget.setVisible(True)

        # Restore original footer buttons
        if self._user_footer:
            layout = self._user_footer.layout()
            if layout:
                while layout.count():
                    item = layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

                w, h = scaled_size(30, 24)
                layout.addStretch()

                self._edit_btn = QPushButton("✎")
                self._edit_btn.setObjectName("userEditBtn")
                self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                install_compact_tooltip(self._edit_btn, "Edit & Resend")
                self._edit_btn.setFixedSize(w, h)
                self._edit_btn.clicked.connect(self._request_edit)
                self._edit_btn.setEnabled(self._editable)
                layout.addWidget(self._edit_btn)

                self._user_copy_btn = QPushButton()
                self._user_copy_btn.setObjectName("userCopyBtn")
                self._user_copy_btn.setIcon(_copy_icon())
                self._user_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self._user_copy_btn.setFixedSize(w, h)
                install_compact_tooltip(self._user_copy_btn, "Copy")
                self._user_copy_btn.clicked.connect(self._copy_content)
                layout.addWidget(self._user_copy_btn)

            self._set_user_actions_visible(False)
            self._user_footer.setVisible(True)

        if self._user_bubble_container is not None:
            self._user_bubble_container.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred,
            )

    def _copy_content(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._bubble_text, QClipboard.Mode.Clipboard)

    def set_checkpoint_id(self, checkpoint_id: str | None) -> None:
        self._checkpoint_id = checkpoint_id

    def set_message_id(self, message_id: str | None) -> None:
        self._message_id = message_id

    def contextMenuEvent(self, event) -> None:
        """Show VS Code-like context menu for message actions."""
        menu = create_isolated_context_menu(self)

        copy_action = menu.addAction("复制")
        copy_action.triggered.connect(self._copy_content)

        if self._allow_edit and self._editable:
            edit_action = menu.addAction("编辑并重发")
            edit_action.triggered.connect(self._request_edit)

        if self._checkpoint_id:
            rollback_action = menu.addAction("回滚到此消息之前")
            rollback_action.triggered.connect(
                lambda _=False, cp_id=self._checkpoint_id: self.rollback_requested.emit(cp_id, self)
            )

        menu.exec(event.globalPos())
        event.accept()

    def _setup_hover_handler(self) -> None:
        """Setup hover detection for user message buttons."""
        if not self._is_outbound_message() or self._user_footer is None:
            return
        self._user_bubble_container.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle hover events for user message bubble container."""
        if obj == self._edit_widget and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False
                self._save_edit()
                return True

        if (
            isinstance(obj, QLabel)
            and obj in self._raw_markdown_labels
            and event.type() == QEvent.Type.KeyPress
            and event.matches(QKeySequence.StandardKey.Copy)
        ):
            clipboard = QApplication.clipboard()
            if clipboard:
                raw = self._raw_markdown_labels[obj]
                selected = obj.selectedText()
                clipboard.setText(
                    _raw_markdown_for_selected_text(raw, selected),
                    QClipboard.Mode.Clipboard,
                )
            return True

        if (
            isinstance(obj, QLabel)
            and event.type() == QEvent.Type.ContextMenu
            and (
                obj in self._raw_markdown_labels
                or obj.objectName() in {"userMessageText", "userContextChipText"}
            )
        ):
            menu = create_isolated_context_menu(self)
            selected = obj.selectedText()

            copy_selected_action = None
            if selected:
                copy_selected_action = menu.addAction("复制所选")
            copy_all_action = menu.addAction("复制")
            edit_action = None
            if (
                obj.objectName() in {"userMessageText", "userContextChipText"}
                and self._allow_edit
                and self._editable
            ):
                edit_action = menu.addAction("编辑并重发")
            rollback_action = None
            if self._checkpoint_id:
                rollback_action = menu.addAction("回滚到此消息之前")
            action = menu.exec(event.globalPos())
            if not action:
                return True

            if action == rollback_action and self._checkpoint_id:
                self.rollback_requested.emit(self._checkpoint_id, self)
                return True

            clipboard = QApplication.clipboard()
            if clipboard is None:
                return True
            if action == copy_selected_action and selected:
                if obj in self._raw_markdown_labels:
                    raw = self._raw_markdown_labels[obj]
                    clipboard.setText(
                        _raw_markdown_for_selected_text(raw, selected),
                        QClipboard.Mode.Clipboard,
                    )
                else:
                    clipboard.setText(selected, QClipboard.Mode.Clipboard)
                return True

            if action == copy_all_action:
                if obj in self._raw_markdown_labels:
                    clipboard.setText(self._raw_markdown_labels[obj], QClipboard.Mode.Clipboard)
                elif isinstance(obj, _ElidedLabel):
                    clipboard.setText(obj.full_text, QClipboard.Mode.Clipboard)
                else:
                    clipboard.setText(obj.text(), QClipboard.Mode.Clipboard)
                return True

            if action == edit_action:
                self._request_edit()
                return True

        if not self._is_outbound_message():
            return super().eventFilter(obj, event)

        if obj == self._user_bubble_container:
            if event.type() == event.Type.Enter:
                if self._complete and self._user_footer:
                    self._set_user_actions_visible(True)
            elif event.type() == event.Type.Leave:
                if self._user_footer:
                    self._set_user_actions_visible(False)

        return super().eventFilter(obj, event)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self._is_outbound_message():
            if self._complete and self._user_footer:
                self._set_user_actions_visible(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._is_outbound_message():
            if self._user_footer:
                self._set_user_actions_visible(False)

    def _set_user_actions_visible(self, visible: bool) -> None:
        if not self._user_footer:
            return
        self._user_actions_visible = visible

        edit_enabled = self._editable and visible
        self._edit_btn.setText("✎" if self._editable else "")
        self._edit_btn.setEnabled(edit_enabled)
        self._edit_btn.setVisible(True)

        self._user_copy_btn.setEnabled(visible)
        self._user_copy_btn.setVisible(True)

        # Keep layout width stable: buttons always occupy space, only visual state changes.
        self._edit_btn.setFlat(not visible)
        self._user_copy_btn.setFlat(not visible)
        if visible:
            self._user_copy_btn.setIcon(_copy_icon())
            self._edit_btn.setStyleSheet("")
            self._user_copy_btn.setStyleSheet("")
        else:
            self._user_copy_btn.setIcon(QIcon())
            self._edit_btn.setStyleSheet("color: transparent;")
            self._user_copy_btn.setStyleSheet("color: transparent;")

    def _set_agent_actions_visible(self, visible: bool) -> None:
        if not hasattr(self, "_copy_btn"):
            return
        self._footer.setVisible(self._complete or visible)
        self._copy_btn.setEnabled(visible)
        self._copy_btn.setIcon(_copy_icon() if visible else QIcon())

    def _update_edit_widget_height(self) -> None:
        if not self._edit_widget:
            return
        metrics = self._edit_widget.fontMetrics()
        line_h = metrics.lineSpacing()
        doc_lines = max(1, self._edit_widget.document().blockCount())

        max_lines = 10
        visible_lines = min(max_lines, doc_lines)
        if doc_lines < max_lines:
            self._edit_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            self._edit_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        frame = self._edit_widget.frameWidth() * 2
        doc_margin = int(self._edit_widget.document().documentMargin() * 2)
        padding = 12
        target_h = (visible_lines * line_h) + frame + doc_margin + padding
        self._edit_widget.setFixedHeight(target_h)

    def resizeEvent(self, event) -> None:
        """Keep message content constrained to current panel width."""
        super().resizeEvent(event)
        self._apply_text_width_constraints()
        self._sync_summary_arrow_alignment()
        self._sync_bubble_arrow_alignment()
        self._sync_timeline_dot_alignment()
        self._update_user_bubble_width()
        self._update_left_bubble_width()

    def _update_user_bubble_width(self) -> None:
        if not self._is_outbound_message() or self._user_bubble_container is None:
            return
        if self._editing:
            width = max(80, self.width() - 32)
        else:
            width = self._target_user_bubble_width()
        self._user_bubble_container.setMinimumWidth(width)
        self._user_bubble_container.setMaximumWidth(width)
        self._sync_context_chip_width()

    def _update_left_bubble_width(self) -> None:
        if not (self._uses_bubble_layout() and self._bubble_align == "left"):
            return
        if self._user_bubble_widget is None:
            return
        width = max(80, self.width() - 56)
        self._user_bubble_widget.setMinimumWidth(width)
        self._user_bubble_widget.setMaximumWidth(width)
        if self._body_content_widget is not None:
            self._body_content_widget.setMaximumContentWidth(
                self._user_bubble_content_width_limit()
            )

    def _is_outbound_message(self) -> bool:
        """Right-side messages sent to an agent share the user bubble layout."""
        return self._uses_bubble_layout() and self._bubble_align == "right"

    def _uses_bubble_layout(self) -> bool:
        return self._display_mode == "bubble"

    def _uses_timeline(self) -> bool:
        if self._is_coordination:
            return False
        return self._display_mode in {"agent_markdown", "thought"} or self._bubble_on_timeline

    def _uses_summary_bubble(self) -> bool:
        return self._uses_bubble_layout() and bool(self._bubble_title) and not self._allow_edit

    def _bubble_text_strategy(self) -> tuple[str, str, bool]:
        if self._uses_summary_bubble():
            return (str(self._bubble_title or ""), self._bubble_text, False)
        return (self._bubble_text, self._bubble_text, True)

    def _apply_text_width_constraints(self) -> None:
        max_w = max(40, self._content_width_limit())
        for label in self._wrapping_labels:
            label.setMaximumWidth(max_w)
        if self._uses_bubble_layout():
            bubble_max_w = self._user_bubble_content_width_limit()
            if self._bubble_title_label is not None:
                self._bubble_title_label.setMaximumWidth(max(40, bubble_max_w - 24))
            if self._body_content_widget is not None:
                self._body_content_widget.setMaximumContentWidth(bubble_max_w)
        elif self._display_mode == "thought" and self._summary_text_label is not None:
            self._summary_text_label.setMaximumWidth(
                max(40, max_w - 24 - TIMELINE_TEXT_LEFT_GUTTER)
            )

    def _target_user_bubble_width(self) -> int:
        # Match the agent/tool timeline geometry: when the user bubble is
        # centered in the row, its left edge should align with the dot guide.
        outer_left_margin = 16
        guide_x = outer_left_margin + (TIMELINE_RAIL_WIDTH // 2)
        available = max(80, self.width() - 32)
        preferred = max(220, self.width() - (guide_x * 2))
        return min(available, preferred)

    def _content_width_limit(self) -> int:
        return self.width() - 56

    def _user_bubble_content_width_limit(self) -> int:
        bubble_width = self._target_user_bubble_width() if self._bubble_align == "right" else max(40, self.width() - 56)
        bubble = self._user_bubble_widget
        if bubble is not None and bubble.layout() is not None:
            margins = bubble.layout().contentsMargins()
            bubble_width -= margins.left() + margins.right()
        return max(40, bubble_width)

    def refresh_layout_for_width_change(self) -> None:
        """Synchronously recompute width-dependent sub-layouts."""
        self._apply_text_width_constraints()
        self._sync_bubble_arrow_alignment()
        self._sync_timeline_dot_alignment()
        self._update_user_bubble_width()
        self._update_left_bubble_width()

    def _sync_context_chip_width(self) -> None:
        if self._context_chip_widget is None:
            return
        bubble = self._user_bubble_widget
        bubble_width = self._user_bubble_container.width() if self._user_bubble_container is not None else 0
        if bubble_width <= 0 and bubble is not None:
            bubble_width = bubble.width()
        if bubble_width <= 0:
            return

        margins = bubble.layout().contentsMargins() if bubble is not None and bubble.layout() else None
        horizontal_padding = (margins.left() + margins.right()) if margins is not None else 20
        max_chip_width = max(80, bubble_width - horizontal_padding)
        self._context_chip_widget.setMaximumWidth(max_chip_width)
        self._context_chip_widget.updateGeometry()
        if isinstance(self._context_chip_label, _ElidedLabel):
            self._context_chip_label._update_elided_text()

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        content = self._bubble_text if self._uses_bubble_layout() else self._content
        return f"{role_text}: {content}"

    def is_expanded(self) -> bool:
        return self._expanded

    def context_chip_panel_width_hint(self) -> int:
        if self._context_chip_widget is None:
            return 0
        chip_width = min(
            self._context_chip_widget.sizeHint().width(),
            self._context_chip_widget.maximumWidth(),
        )
        bubble_padding = 24
        row_gutters = 40
        return int((chip_width + bubble_padding) / 0.75) + row_gutters

    def _build_expandable_content_widget(
        self,
        label: QLabel,
        *,
        fade_color: str,
        collapsed_text: str | None = None,
        expanded_text: str | None = None,
        clamp_collapsed: bool = True,
        overlay_host: QWidget | None = None,
        toggle_host: QWidget | None = None,
        toggle_host_margins: QMargins | None = None,
    ) -> _ExpandableContentWidget:
        widget = _ExpandableContentWidget(
            label,
            fade_color=fade_color,
            collapsed_text=collapsed_text,
            expanded_text=expanded_text,
            clamp_collapsed=clamp_collapsed,
            overlay_host=overlay_host,
            toggle_host=toggle_host,
            toggle_host_margins=toggle_host_margins,
            parent=self,
        )
        return widget
