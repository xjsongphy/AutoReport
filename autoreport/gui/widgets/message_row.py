"""Message cell — VS Code Copilot Chat style.

- User messages: right-aligned rounded bubble
- Agent messages: flat layout with avatar + markdown content + bottom copy
- Code blocks: monospace card with right-side copy icon (hover visible)
"""

import re
from pathlib import PurePath

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QClipboard, QColor, QIcon, QKeySequence, QPainter, QPalette, QPen

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
from .timeline import TimelineRail
from .ui_utils import create_isolated_context_menu, install_compact_tooltip, render_svg_icon

TIMELINE_EVENT_ROW_HEIGHT = 34

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


def _parse_code_blocks(content: str) -> list[tuple[str, str | None]]:
    """Split content into segments: (text, None) for text, (code, language) for code."""
    pattern = r"```(\w*)\n(.*?)```"
    parts: list[tuple[str, str | None]] = []
    last_end = 0
    for m in re.finditer(pattern, content, re.DOTALL):
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


def _copy_icon() -> QIcon:
    return render_svg_icon("copy", QColor(get_theme_colors()["muted"]), size=16)


def _display_filename(path_text: str) -> str:
    normalized = str(path_text or "").strip().rstrip("/\\")
    if not normalized:
        return ""
    try:
        return PurePath(normalized).name or normalized
    except Exception:
        return normalized


def _parse_editor_context_block(content: str) -> tuple[str | None, str | None, str]:
    """Extract leading editor context metadata from bubble text.

    Expected formats:
    - Editor context: selection\nFile: path\nSelected lines: a-b\n\nmessage
    - Editor context: file\nCurrent file: path\n\nmessage
    """
    if not content.startswith("Editor context: "):
        return None, None, content

    lines = content.splitlines()
    if len(lines) < 2:
        return None, None, content

    context_type = lines[0].split(":", 1)[1].strip().lower()
    body_start = None
    chip_text = None
    chip_tooltip = None

    if context_type == "selection" and len(lines) >= 3:
        file_match = re.match(r"^File:\s*(.+)$", lines[1])
        line_match = re.match(r"^Selected lines:\s*(.+)$", lines[2])
        if file_match and line_match:
            file_path = file_match.group(1).strip()
            chip_text = f"{_display_filename(file_path)}#{line_match.group(1).strip()}"
            chip_tooltip = f"{file_path}#{line_match.group(1).strip()}"
            body_start = 3
    elif context_type == "file" and len(lines) >= 2:
        file_match = re.match(r"^Current file:\s*(.+)$", lines[1])
        if file_match:
            file_path = file_match.group(1).strip()
            chip_text = _display_filename(file_path)
            chip_tooltip = file_path
            body_start = 2

    if chip_text is None or body_start is None:
        return None, None, content

    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    body = "\n".join(lines[body_start:]).strip()
    return chip_text, chip_tooltip, body


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
    return raw_markdown[start_raw:end_raw]


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

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str = "",
        is_coordination: bool = False,
        render_as_user_bubble: bool = False,
        agent_name: str = "Agent",
        summary: str | None = None,
        detail: str | None = None,
        expandable: bool = True,
        agent_chain_prev: bool = False,
        agent_chain_next: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._role = role
        self._content = content
        self._timestamp = timestamp
        self._is_coordination = is_coordination
        self._render_as_user_bubble = render_as_user_bubble
        self._agent_name = agent_name
        self._complete = False
        self._agent_content_layout: QVBoxLayout | None = None
        self._user_footer: QWidget | None = None
        self._editable = False
        self._user_bubble_container: QWidget | None = None
        self._summary = summary
        self._detail = detail
        self._expandable = expandable
        self._expanded = False
        self._wrapping_labels: list[QLabel] = []
        self._raw_markdown_labels: dict[QLabel, str] = {}
        self._agent_chain_prev = agent_chain_prev
        self._agent_chain_next = agent_chain_next
        self._timeline_rail: TimelineRail | None = None
        self._summary_btn: QPushButton | None = None
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
        self._context_chip_text, self._context_chip_tooltip, self._bubble_text = _parse_editor_context_block(content)
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

        if self._is_outbound_message():
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
                QSizePolicy.Policy.Fixed,
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
            bl.setContentsMargins(8, 8, 12, 8)
            bl.setSpacing(0)
            self._user_bubble_widget = bubble
            self._user_bubble_layout = bcl

            if self._summary is not None:
                bl.addWidget(self._build_summary_widget("user"))
                self._detail_widget = self._build_detail_widget("user")
                bl.addWidget(self._detail_widget)
                self._detail_widget.setVisible(False)
            else:
                self._populate_user_bubble_content(bl)

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

            rl.addWidget(self._user_bubble_container, 0, Qt.AlignmentFlag.AlignRight)
            rl.setAlignment(self._user_bubble_container, Qt.AlignmentFlag.AlignRight)
            self._outer_layout.addWidget(row)
        else:
            row = QWidget(outer)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)

            self._timeline_rail = TimelineRail(parent=row)
            rl.addWidget(self._timeline_rail, 0, Qt.AlignmentFlag.AlignLeft)

            self._agent_content_layout = QVBoxLayout()
            self._agent_content_layout.setContentsMargins(0, 0, 0, 0)
            self._agent_content_layout.setSpacing(0)
            rl.addLayout(self._agent_content_layout, 1)
            self._outer_layout.addWidget(row)
            self._rebuild_agent_content()
            self._update_agent_chain()

        layout.addWidget(outer)

    def _populate_user_bubble_content(self, layout: QVBoxLayout) -> None:
        if self._context_chip_text:
            layout.addWidget(self._build_context_chip(self._context_chip_text))
        text_content = self._content if self._context_chip_text is None else self._bubble_text
        if not text_content:
            return
        text = QLabel(text_content)
        text.setObjectName("userMessageText")
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        text.setMinimumWidth(0)
        text.installEventFilter(self)
        c = get_theme_colors()
        text.setStyleSheet(f"color: {c['editor_fg']}; background-color: transparent;")
        layout.addWidget(text)

    def _build_context_chip(self, chip_text: str) -> QWidget:
        chip = QWidget(self)
        chip.setObjectName("userContextChip")
        chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        chip_layout = QHBoxLayout(chip)
        chip_layout.setContentsMargins(10, 7, 10, 7)
        chip_layout.setSpacing(6)

        icon_label = QLabel(chip)
        icon_label.setObjectName("userContextChipIcon")
        icon = render_svg_icon("file", QColor(get_theme_colors()["muted"]), size=14)
        icon_label.setPixmap(icon.pixmap(14, 14))
        icon_label.setFixedSize(14, 14)
        chip_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        text_label = QLabel(chip_text, chip)
        text_label.setObjectName("userContextChipText")
        text_label.setTextFormat(Qt.TextFormat.PlainText)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_label.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        text_label.installEventFilter(self)
        text_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if self._context_chip_tooltip:
            text_label.setToolTip(self._context_chip_tooltip)
            chip.setToolTip(self._context_chip_tooltip)
        chip_layout.addWidget(text_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self._context_chip_widget = chip
        self._context_chip_label = text_label
        return chip

    def _clear_agent_content(self) -> None:
        self._wrapping_labels = []
        self._raw_markdown_labels = {}
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

        if self._summary is not None:
            self._agent_content_layout.addWidget(self._build_summary_widget("agent"))
            self._detail_widget = self._build_detail_widget("agent")
            self._agent_content_layout.addWidget(self._detail_widget)
            self._detail_widget.setVisible(self._expanded and self._has_detail())
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
        return bool(self._detail)

    def _build_summary_widget(self, summary_type: str) -> QWidget:
        widget = _SummaryHeader(self)
        if summary_type == "agent":
            # Keep timeline events on a fixed vertical pitch.
            widget.setMinimumHeight(TIMELINE_EVENT_ROW_HEIGHT)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._summary_header = widget

        if summary_type == "agent":
            widget.setObjectName("toolCallHeader")
        else:
            widget.setObjectName("msgSummaryHeader")

        self._summary_arrow_widget = _DisclosureArrow(self._expanded, widget)
        self._summary_arrow_widget.setVisible(self._expandable and self._has_detail())
        self._summary_arrow_host = QWidget(widget)
        self._summary_arrow_host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        ahl = QVBoxLayout(self._summary_arrow_host)
        ahl.setContentsMargins(0, 0, 0, 0)
        ahl.setSpacing(0)
        ahl.addWidget(self._summary_arrow_widget, 0, Qt.AlignmentFlag.AlignTop)
        left_margin = 4 if summary_type == "agent" else 0
        layout.setContentsMargins(left_margin, 4, 0, 6)

        self._summary_text_label = QLabel(self._summary or "", widget)
        self._summary_text_label.setObjectName("toolCallHeaderText")
        self._summary_text_label.setTextFormat(Qt.TextFormat.PlainText)
        self._summary_text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._summary_text_label.setWordWrap(True)
        self._summary_text_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._summary_text_label.setMinimumWidth(0)
        layout.addWidget(self._summary_text_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._summary_arrow_host, 0, Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)
        self._sync_summary_arrow_alignment()
        self._sync_timeline_dot_alignment()

        widget.setCursor(
            Qt.CursorShape.PointingHandCursor
            if (self._expandable and self._has_detail())
            else Qt.CursorShape.ArrowCursor
        )
        widget.clicked.connect(self._toggle_summary)
        return widget

    def _build_detail_widget(self, detail_type: str) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        # Keep expanded content aligned with timeline content start.
        left_margin = 4 if detail_type == "agent" else 20
        layout.setContentsMargins(left_margin, 2, 0, 0)
        layout.setSpacing(0)

        if detail_type == "agent":
            label = self._build_agent_markdown_label(self._detail or "")
            self._detail_label = label
        else:
            label = QLabel(self._detail or "")
            label.setObjectName("userMessageText")
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            label.setMinimumWidth(0)
            c = get_theme_colors()
            label.setStyleSheet(f"color: {c['editor_fg']}; background-color: transparent;")
        layout.addWidget(label)
        return widget

    def _toggle_summary(self) -> None:
        if not (self._expandable and self._has_detail()):
            return
        self._expanded = not self._expanded
        if self._detail_widget:
            self._detail_widget.setVisible(self._expanded)
        self._refresh_summary_header()

    def set_summary_text(self, summary: str) -> None:
        self._summary = summary
        self._refresh_summary_header()

    def set_detail_text(self, detail: str) -> None:
        self._detail = detail
        if self._detail_label is not None:
            self._detail_label.setText(render_markdown(detail or ""))
            self._raw_markdown_labels[self._detail_label] = detail or ""
            self._apply_text_width_constraints()
        elif self._agent_content_layout is not None:
            expanded = self._expanded
            self._rebuild_agent_content()
            self._expanded = expanded
        if self._detail_widget:
            self._detail_widget.setVisible(self._expanded and self._has_detail())
        self._refresh_summary_header()

    def _refresh_summary_header(self) -> None:
        can_expand = self._expandable and self._has_detail()
        if self._summary_text_label is not None:
            self._summary_text_label.setText(self._summary or "")
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

    def _sync_summary_arrow_alignment(self) -> None:
        """Align disclosure arrow center to the first summary text line center."""
        if (
            self._summary_arrow_host is None
            or self._summary_text_label is None
            or self._summary_arrow_widget is None
        ):
            return
        metrics = self._summary_text_label.fontMetrics()
        line_height = max(1, metrics.height())
        arrow_height = max(1, self._summary_arrow_widget.height())
        top_offset = max(0, (line_height - arrow_height) // 2)
        host_layout = self._summary_arrow_host.layout()
        if isinstance(host_layout, QVBoxLayout):
            host_layout.setContentsMargins(0, top_offset, 0, 0)

    @staticmethod
    def _first_line_center_y(top_offset: int, line_height: int) -> float:
        return float(top_offset + (max(1, line_height) / 2.0))

    def _sync_timeline_dot_alignment(self) -> None:
        """Align timeline dot center to the first visible text line center."""
        if self._timeline_rail is None:
            return
        # Summary rows (e.g. Thought): align to summary first line.
        if self._summary_text_label is not None and self._summary_header is not None:
            metrics = self._summary_text_label.fontMetrics()
            line_height = metrics.height()
            margins = self._summary_header.layout().contentsMargins() if self._summary_header.layout() else None
            top = margins.top() if margins is not None else 0
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
        if self._summary_text_label is not None:
            if color:
                self._summary_text_label.setStyleSheet(
                    f"color: {color}; background-color: transparent;"
                )
            else:
                self._summary_text_label.setStyleSheet("")
        if self._detail_label is not None:
            if color:
                self._detail_label.setStyleSheet(
                    f"color: {color}; background-color: transparent;"
                )
            else:
                self._detail_label.setStyleSheet("")

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
        if self._role != "user":
            return
        self._editable = editable
        if self._complete and self._user_footer:
            self._set_user_actions_visible(False)

    def _request_edit(self) -> None:
        """Enter edit mode for this user message."""
        if self._role == "user" and self._editable:
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

        edit_content = self._detail if self._summary is not None else self._content

        edit_bubble = QWidget(self._user_bubble_container)
        edit_bubble.setObjectName("userEditBubble")
        edit_bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        ebl = QVBoxLayout(edit_bubble)
        ebl.setContentsMargins(8, 8, 12, 8)
        ebl.setSpacing(0)

        edit = QPlainTextEdit(edit_content or "")
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
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            self._user_bubble_container.setMinimumWidth(0)
            self._user_bubble_container.setMaximumWidth(16777215)
            self._user_bubble_container.setFixedWidth(max(80, self.width() - 32))
        self._update_edit_widget_height()
        self._edit_widget.setFocus()
        self._edit_widget.textChanged.connect(self._update_edit_widget_height)

    def _save_edit(self) -> None:
        """Save the edited content and emit signal."""
        if not self._editing or not self._edit_widget:
            return

        new_content = self._edit_widget.toPlainText()
        self._content = new_content  # Update stored content
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
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Preferred,
            )

    def _copy_content(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._content, QClipboard.Mode.Clipboard)

    def set_checkpoint_id(self, checkpoint_id: str | None) -> None:
        self._checkpoint_id = checkpoint_id

    def contextMenuEvent(self, event) -> None:
        """Show VS Code-like context menu for message actions."""
        menu = create_isolated_context_menu(self)

        copy_action = menu.addAction("复制")
        copy_action.triggered.connect(self._copy_content)

        if self._role == "user" and self._editable:
            edit_action = menu.addAction("编辑并重发")
            edit_action.triggered.connect(self._request_edit)

        if self._is_outbound_message() and self._checkpoint_id:
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
            action = menu.exec(event.globalPos())
            if not action:
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
                else:
                    clipboard.setText(obj.text(), QClipboard.Mode.Clipboard)
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
        self._sync_timeline_dot_alignment()
        if self._is_outbound_message() and self._user_bubble_container is not None:
            if self._editing:
                width = max(80, self.width() - 32)
            else:
                width = max(80, int(self.width() * 0.75))
            self._user_bubble_container.setFixedWidth(width)

    def _is_outbound_message(self) -> bool:
        """Right-side messages sent to an agent share the user bubble layout."""
        return self._role == "user" or self._render_as_user_bubble

    def _apply_text_width_constraints(self) -> None:
        max_w = max(40, self._content_width_limit())
        for label in self._wrapping_labels:
            label.setMaximumWidth(max_w)

    def _content_width_limit(self) -> int:
        return self.width() - 56

    def get_display_text(self) -> str:
        role_text = "You" if self._role == "user" else "Agent"
        return f"{role_text}: {self._content}"

    def is_expanded(self) -> bool:
        return self._expanded

    def context_chip_panel_width_hint(self) -> int:
        if self._context_chip_widget is None:
            return 0
        chip_width = self._context_chip_widget.sizeHint().width()
        bubble_padding = 24
        row_gutters = 40
        return int((chip_width + bubble_padding) / 0.75) + row_gutters
