"""Tool call group matching the chat timeline tool-call style."""

import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme import get_theme_colors
from .timeline import TimelineRail
from .ui_utils import install_compact_tooltip, render_svg_icon

TIMELINE_EVENT_ROW_HEIGHT = 34
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TASK_STATUS_PREFIX_RE = re.compile(r"^[\s☐☑●○✓✗✕✔✅⚠⏳📋\-—:：]+")
_TASK_SECTION_LABELS = {"task", "todo", "wait", "—", "-"}
_TASK_COMPLETED_MARKERS = ("☑", "✓", "✔", "✅")
_TASK_RUNNING_MARKERS = ("●", "⏳", "*")
_TASK_FAILED_MARKERS = ("⚠", "✗", "✕")
_TASK_PENDING_MARKERS = ("☐", "○")


def _timeline_bottom_padding(widget: QWidget) -> int:
    return max(8, int(round(widget.fontMetrics().lineSpacing() * 0.5)))

def _copy_icon_dark():
    # Keep copy icon visually consistent with user bubble actions.
    return render_svg_icon("copy", QColor(get_theme_colors()["muted"]), size=16)


@dataclass
class ToolCall:
    name: str
    arguments: dict
    success: bool | None
    duration_ms: int
    result: Any | None = None
    error: str | None = None
    summary: str | None = None
    elapsed_seconds: int = 0
    file_names: list[str] = field(default_factory=list)


class _ClickableHeaderWidget(QWidget):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):  # noqa: N802
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def click(self) -> None:
        self.clicked.emit()


class ToolCallGroup(QWidget):
    """Tool calls in a compact summary row."""

    @staticmethod
    def _display_name(name: str) -> str:
        return name.replace("_", " ").replace("/", " ").title()

    @staticmethod
    def _normalize_summary_html(summary: str) -> str:
        """Preserve explicit newlines inside rich-text headers."""
        return str(summary or "").replace("\r\n", "\n").replace("\n", "<br/>")

    @staticmethod
    def _plain_summary_text(summary: str) -> str:
        text = str(summary or "").replace("\r\n", "\n")
        text = text.replace("<br/>", "\n").replace("<br>", "\n").replace("<br />", "\n")
        text = _HTML_TAG_RE.sub("", text)
        return html.unescape(text)

    @staticmethod
    def _task_content_key_from_text(summary: str) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for raw_line in ToolCallGroup._plain_summary_text(summary).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.lower() in _TASK_SECTION_LABELS:
                continue
            line = _TASK_STATUS_PREFIX_RE.sub("", line).strip()
            if line and line not in seen:
                seen.add(line)
                lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _task_content_key_from_arguments(arguments: dict[str, Any]) -> str:
        for key in ("brief", "description"):
            value = str(arguments.get(key) or "").strip()
            if value:
                return value
        task_id = str(arguments.get("task_id") or "").strip()
        return task_id

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._calls: list[ToolCall] = []
        self._timeline_prev = False
        self._timeline_next = False
        self._timeline_rail: TimelineRail | None = None
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick_running)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self._timeline_rail = TimelineRail(parent=self)
        layout.addWidget(self._timeline_rail, 0, Qt.AlignmentFlag.AlignLeft)

        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 0, 0, _timeline_bottom_padding(self))
        content_layout.setSpacing(0)
        layout.addWidget(content, 1)

        self._header_btn = _ClickableHeaderWidget()
        self._header_btn.setObjectName("toolCallHeader")
        self._header_btn.setMinimumHeight(TIMELINE_EVENT_ROW_HEIGHT)
        self._header_btn.clicked.connect(lambda: None)
        header_layout = QHBoxLayout(self._header_btn)
        header_layout.setContentsMargins(0, 4, 0, 6)
        header_layout.setSpacing(0)

        self._header_text = QLabel()
        self._header_text.setObjectName("toolCallHeaderText")
        self._header_text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._header_text.setWordWrap(True)
        self._header_text.setTextFormat(Qt.TextFormat.RichText)
        self._header_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._header_text.setMinimumWidth(0)
        header_layout.addWidget(self._header_text, 1, Qt.AlignmentFlag.AlignTop)

        self._task_board_host = QWidget(self._header_btn)
        self._task_board_host.setObjectName("taskBoardHost")
        self._task_board_layout = QVBoxLayout(self._task_board_host)
        self._task_board_layout.setContentsMargins(0, 0, 0, 0)
        self._task_board_layout.setSpacing(2)
        self._task_board_host.setVisible(False)
        header_layout.addWidget(self._task_board_host, 1, Qt.AlignmentFlag.AlignTop)
        content_layout.addWidget(self._header_btn)

        self._detail_host = QWidget(self)
        self._detail_layout = QVBoxLayout(self._detail_host)
        self._detail_layout.setContentsMargins(0, 2, 0, 0)
        self._detail_layout.setSpacing(0)
        content_layout.addWidget(self._detail_host)
        self._update_timeline_chain()

    def set_timeline_chain(self, prev_link: bool, next_link: bool) -> None:
        self._timeline_prev = prev_link
        self._timeline_next = next_link
        self._update_timeline_chain()

    def _update_timeline_chain(self) -> None:
        if self._timeline_rail is not None:
            self._timeline_rail.set_chain(self._timeline_prev, self._timeline_next)

    def add_tool_call(
        self,
        name: str,
        arguments: dict,
        success: bool | None,
        duration_ms: int = 0,
        result: Any = None,
        error: str | None = None,
        summary: str | None = None,
    ) -> None:
        self._calls.append(ToolCall(
            name=name,
            arguments=arguments,
            success=success,
            duration_ms=duration_ms,
            result=result,
            error=error,
            summary=summary,
            elapsed_seconds=0,
            file_names=self._extract_file_names(arguments),
        ))
        self._update_display()

    def complete_tool_call(
        self,
        name: str,
        result: Any = None,
        error: str | None = None,
        duration_ms: int = 100,
        summary: str | None = None,
    ) -> None:
        for call in reversed(self._calls):
            if call.name == name and call.success is None:
                call.success = error is None
                call.duration_ms = duration_ms
                call.result = result if error is None else None
                call.error = error
                if summary is not None:
                    call.summary = summary
                self._update_display()
                return

        self.add_tool_call(
            name=name,
            arguments={},
            success=error is None,
            duration_ms=duration_ms,
            result=result if error is None else None,
            error=error,
            summary=summary,
        )

    def can_merge_with_last(self, name: str) -> bool:
        if not self._calls:
            return False
        return self._calls[-1].name == name

    def _tick_running(self) -> None:
        dirty = False
        for call in self._calls:
            if call.success is None:
                call.elapsed_seconds += 1
                dirty = True
        if dirty:
            self._update_display()
        else:
            self._tick_timer.stop()

    def _status_dot_color(self, success: bool | None) -> str:
        c = get_theme_colors()
        if success is None:
            return c["status_running"]
        return c["status_success"] if success else c["status_error"]

    def _timer_text(self, call: ToolCall) -> str:
        return ""

    def _extract_file_names(self, arguments: dict[str, Any]) -> list[str]:
        names: list[str] = []

        def _display_token(path_text: str) -> str:
            token = str(path_text or "").strip()
            if not token:
                return ""
            if token in {".", "./"}:
                return "."
            normalized = token.rstrip("/\\")
            if not normalized:
                return "."
            leaf = Path(normalized).name
            return leaf or normalized

        for key in ("path", "file_path", "output_path"):
            val = arguments.get(key)
            if isinstance(val, str) and val.strip():
                display = _display_token(val)
                if display:
                    names.append(display)
        multi = arguments.get("file_paths")
        if isinstance(multi, list):
            for p in multi:
                if isinstance(p, str) and p.strip():
                    display = _display_token(p)
                    if display:
                        names.append(display)
        return names

    def _header_text_for_call(self, call: ToolCall) -> str:
        if call.summary:
            return self._normalize_summary_html(call.summary)
        sep = "&nbsp;&nbsp;"
        if call.name == "read":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Read</b>{sep}{files}".strip()
        if call.name == "parse_pdf":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Parse</b>{sep}{files}".strip()
        if call.name == "write_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Write</b>{sep}{files}".strip()
        if call.name == "edit_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Edit</b>{sep}{files}".strip()
        if call.name == "delete_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Delete</b>{sep}{files}".strip()
        if call.name == "exec":
            desc = str(call.arguments.get("command_description") or "").strip()
            if desc:
                desc = desc[0].upper() + desc[1:]
            return f"<b>Exec</b>{sep}{desc}".strip()
        return f"<b>{self._display_name(call.name)}</b>"

    def _task_status_from_line(self, line: str) -> str:
        stripped = line.strip()
        if stripped.startswith(_TASK_COMPLETED_MARKERS):
            return "completed"
        if stripped.startswith(_TASK_RUNNING_MARKERS):
            return "running"
        if stripped.startswith(_TASK_FAILED_MARKERS):
            return "failed"
        if stripped.startswith(_TASK_PENDING_MARKERS):
            return "pending"
        return "pending"

    def _task_control_text(self, status: str) -> str:
        if status == "running":
            return "*"
        if status == "completed":
            return "✓"
        if status == "failed":
            return "!"
        return ""

    def _clear_task_board(self) -> None:
        while self._task_board_layout.count():
            item = self._task_board_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _task_rows_from_summary(self, summary: str) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for raw_line in self._plain_summary_text(summary).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.lower() in {"task"}:
                rows.append(("section", "", line))
                continue
            if line.lower() in {"todo", "wait"}:
                rows.append(("section", "", line))
                continue
            if line in {"—", "-"}:
                rows.append(("empty", "", line))
                continue
            status = self._task_status_from_line(line)
            text = _TASK_STATUS_PREFIX_RE.sub("", line).strip()
            if text:
                rows.append(("task", status, text))
        return rows

    def _add_task_section_label(self, text: str) -> None:
        label = QLabel(text, self._task_board_host)
        label.setObjectName("taskSectionLabel")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if text.strip().lower() == "task":
            font = label.font()
            font.setBold(True)
            label.setFont(font)
        self._task_board_layout.addWidget(label)

    def _add_task_row(self, status: str, text: str) -> None:
        c = get_theme_colors()
        row = QWidget(self._task_board_host)
        row.setObjectName("taskRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        control = QLabel(self._task_control_text(status), row)
        control.setObjectName("taskStatusControl")
        control.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control.setFixedSize(18, 18)
        control.setTextFormat(Qt.TextFormat.PlainText)
        control.setProperty("taskStatus", status)
        color = {
            "running": c["status_running"],
            "completed": c["status_success"],
            "failed": c["status_error"],
        }.get(status, c["muted"])
        control.setStyleSheet(f"""
            QLabel#taskStatusControl {{
                border: 1px solid {color};
                border-radius: 5px;
                color: {color};
                font-weight: 700;
                background: transparent;
            }}
        """)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignTop)

        label = QLabel(text, row)
        label.setObjectName("taskTextLabel")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setMinimumWidth(0)
        layout.addWidget(label, 1)
        self._task_board_layout.addWidget(row)

    def _render_task_board(self, summary: str) -> None:
        self._clear_task_board()
        for row_type, status, text in self._task_rows_from_summary(summary):
            if row_type == "task":
                self._add_task_row(status, text)
            else:
                self._add_task_section_label(text)

    def _clear_detail(self) -> None:
        while self._detail_layout.count():
            item = self._detail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _exec_card(self, call: ToolCall) -> QWidget:
        card = QFrame(self)
        card.setObjectName("execDetailCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 10)
        card_layout.setSpacing(4)

        def _row(tag: str, text: str, display_text: str | None = None) -> QWidget:
            shown = text if display_text is None else display_text
            row = QFrame(card)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            label = QLabel(tag, row)
            label.setObjectName("execDetailTag")
            label.setFixedWidth(24)
            row_layout.addWidget(label)
            value = QLabel(shown, row)
            value.setObjectName("execDetailText")
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(False)
            # Allow long command/output text to shrink with panel width instead of
            # forcing the whole row wider than the agent panel.
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            value.setMinimumWidth(0)
            value.setFixedHeight(18)
            row_layout.addWidget(value, 1)
            copy_btn = QPushButton(row)
            copy_btn.setObjectName("userCopyBtn")
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.setFixedSize(30, 24)
            install_compact_tooltip(copy_btn, "Copy")
            # Keep button width reserved so IN/OUT text width is stable before hover.
            copy_btn.setVisible(True)
            copy_btn.setEnabled(False)
            copy_btn.setFlat(True)
            copy_btn.setIcon(QIcon())
            copy_btn.clicked.connect(lambda _=False, t=text: QApplication.clipboard().setText(t))
            row_layout.addWidget(copy_btn, 0, Qt.AlignmentFlag.AlignRight)

            def _enter(_):
                copy_btn.setEnabled(True)
                copy_btn.setFlat(False)
                copy_btn.setIcon(_copy_icon_dark())

            def _leave(_):
                copy_btn.setEnabled(False)
                copy_btn.setFlat(True)
                copy_btn.setIcon(QIcon())

            row.enterEvent = _enter  # type: ignore[method-assign]
            row.leaveEvent = _leave  # type: ignore[method-assign]
            return row

        cmd = str(call.arguments.get("command") or "").strip()
        if not cmd and isinstance(call.result, dict):
            cmd = str(call.result.get("command") or "").strip()
        out = ""
        if isinstance(call.result, dict):
            stdout = str(call.result.get("stdout") or "").strip()
            stderr = str(call.result.get("stderr") or "").strip()
            out = stdout + (f"\n{stderr}" if stderr else "")
        if call.error:
            out = "Tool execution failed"

        card_layout.addWidget(_row("IN", cmd))
        divider = QFrame(card)
        divider.setObjectName("execDetailDivider")
        divider.setFixedHeight(1)
        card_layout.addWidget(divider)
        out_preview = "\n".join(out.splitlines()[:3])
        card_layout.addWidget(_row("OUT", out, out_preview))
        card.setMaximumHeight(110)
        return card

    def _render_exec_detail(self) -> None:
        self._clear_detail()
        exec_calls = [c for c in self._calls if c.name == "exec"]
        if not exec_calls:
            self._detail_host.setVisible(False)
            return
        self._detail_layout.addWidget(self._exec_card(exec_calls[-1]))
        self._detail_host.setVisible(True)

    def _update_display(self) -> None:
        if not self._calls:
            return

        running = any(c.success is None for c in self._calls)
        failed = any(c.success is False for c in self._calls)
        success = not running and not failed
        lines = [self._header_text_for_call(call) for call in self._calls]
        self._header_text.setText("<br/>".join(lines))
        show_task_board = len(self._calls) == 1 and self._calls[0].name == "manage_tasks" and bool(self._calls[0].summary)
        self._header_text.setVisible(not show_task_board)
        self._task_board_host.setVisible(show_task_board)
        if show_task_board:
            self._render_task_board(self._calls[0].summary or "")
        else:
            self._clear_task_board()

        if len(self._calls) == 1:
            dot_color = self._status_dot_color(self._calls[0].success)
        else:
            dot_color = self._status_dot_color(None if running else success)

        if self._timeline_rail is not None:
            self._timeline_rail.set_dot_color(dot_color)
        self._render_exec_detail()

        if any(c.success is None for c in self._calls):
            if not self._tick_timer.isActive():
                self._tick_timer.start()
        else:
            self._tick_timer.stop()

    def is_expanded(self) -> bool:
        return False

    def get_summary_text(self) -> str:
        return self._header_text.text()

    def tool_names(self) -> list[str]:
        return [call.name for call in self._calls]

    def is_complete(self) -> bool:
        return bool(self._calls) and all(call.success is not None for call in self._calls)

    def visual_summary_key(self) -> str:
        text = self.get_summary_text()
        return "\n".join(
            line.strip()
            for line in text.replace("\r\n", "\n").replace("<br/>", "\n").splitlines()
            if line.strip()
        )

    def task_content_key(self) -> str:
        if self.tool_names() != ["manage_tasks"]:
            return ""
        summary_key = self._task_content_key_from_text(self.get_summary_text())
        if summary_key:
            return summary_key
        return self._task_content_key_from_arguments(self._calls[-1].arguments)

    def has_status_change_from(self, other: "ToolCallGroup") -> bool:
        current_key = self.task_content_key()
        other_key = other.task_content_key()
        if not current_key or current_key != other_key:
            return False
        return self.visual_summary_key() != other.visual_summary_key()

    def replace_with_group(self, other: "ToolCallGroup") -> None:
        self._calls = [
            ToolCall(
                name=call.name,
                arguments=dict(call.arguments),
                success=call.success,
                duration_ms=call.duration_ms,
                result=call.result,
                error=call.error,
                summary=call.summary,
                elapsed_seconds=call.elapsed_seconds,
                file_names=list(call.file_names),
            )
            for call in other._calls
        ]
        self._update_display()
