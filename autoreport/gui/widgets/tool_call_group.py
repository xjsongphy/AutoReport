"""Collapsible tool call group matching the chat timeline tool-call style."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


@dataclass
class ToolCall:
    name: str
    arguments: dict
    success: bool | None
    duration_ms: int
    result: Any | None = None
    error: str | None = None
    summary: str | None = None
    detail: str | None = None
    expandable: bool = True
    elapsed_seconds: int = 0
    file_names: list[str] = field(default_factory=list)


class _ClickableHeaderLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):  # noqa: N802
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def click(self) -> None:
        self.clicked.emit()


class ToolCallGroup(QWidget):
    """Collapsible group of tool calls."""

    expanded_changed = pyqtSignal(bool)

    @staticmethod
    def _display_name(name: str) -> str:
        return name.replace("_", " ").replace("/", " ").title()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._calls: list[ToolCall] = []
        self._expanded = False
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick_running)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 4, 16, 4)
        layout.setSpacing(0)

        self._header_btn = _ClickableHeaderLabel()
        self._header_btn.setObjectName("toolCallHeader")
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._header_btn.setWordWrap(True)
        self._header_btn.setTextFormat(Qt.TextFormat.RichText)
        self._header_btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._header_btn.setMinimumWidth(0)
        self._header_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._header_btn)

        self._details = QWidget(self)
        self._details.setObjectName("toolCallDetails")
        self._details_layout = QVBoxLayout(self._details)
        self._details_layout.setContentsMargins(0, 2, 0, 0)
        self._details_layout.setSpacing(1)
        self._details.setVisible(False)
        layout.addWidget(self._details)

    def add_tool_call(
        self,
        name: str,
        arguments: dict,
        success: bool | None,
        duration_ms: int = 0,
        result: Any = None,
        error: str | None = None,
        summary: str | None = None,
        detail: str | None = None,
        expandable: bool = True,
    ) -> None:
        self._calls.append(ToolCall(
            name=name,
            arguments=arguments,
            success=success,
            duration_ms=duration_ms,
            result=result,
            error=error,
            summary=summary,
            detail=detail,
            expandable=expandable,
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
        detail: str | None = None,
        expandable: bool | None = None,
    ) -> None:
        for call in reversed(self._calls):
            if call.name == name and call.success is None:
                call.success = error is None
                call.duration_ms = duration_ms
                call.result = result if error is None else None
                call.error = error
                if summary is not None:
                    call.summary = summary
                if detail is not None:
                    call.detail = detail
                if expandable is not None:
                    call.expandable = expandable
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
            detail=detail,
            expandable=True if expandable is None else expandable,
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

    def _on_toggle(self) -> None:
        if not self._any_expandable():
            return
        self._expanded = not self._expanded
        self._details.setVisible(self._expanded)
        self.expanded_changed.emit(self._expanded)
        self._update_display()

    def _call_detail_text(self, call: ToolCall) -> str | None:
        if call.detail is not None:
            return call.detail
        if call.name == "bash":
            return "bash"
        if call.result is not None:
            return str(call.result)[:200]
        if call.success is not None:
            return self._header_text_for_call(call)
        return None

    def _is_expandable(self, call: ToolCall) -> bool:
        return call.expandable and bool(self._call_detail_text(call))

    def _any_expandable(self) -> bool:
        return any(self._is_expandable(call) for call in self._calls)

    def _status_dot(self, success: bool | None) -> str:
        if success is None:
            return "🔵"
        return "🟢" if success else "🔴"

    def _timer_text(self, call: ToolCall) -> str:
        if call.success is None:
            return f"{call.elapsed_seconds}s"
        return ""

    def _extract_file_names(self, arguments: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for key in ("path", "file_path", "output_path"):
            val = arguments.get(key)
            if isinstance(val, str) and val.strip():
                names.append(Path(val).name)
        multi = arguments.get("file_paths")
        if isinstance(multi, list):
            for p in multi:
                if isinstance(p, str) and p.strip():
                    names.append(Path(p).name)
        return names

    def _header_text_for_call(self, call: ToolCall) -> str:
        if call.summary:
            return call.summary
        if call.name == "read_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Read</b> {files}".strip()
        if call.name == "list_dir":
            files = " ".join(call.file_names) if call.file_names else "."
            return f"<b>List</b> {files}".strip()
        if call.name == "parse_pdf":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Parse</b> {files}".strip()
        if call.name == "write_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Write</b> {files}".strip()
        if call.name == "edit_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Edit</b> {files}".strip()
        if call.name == "delete_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Delete</b> {files}".strip()
        if call.name == "bash":
            desc = str(call.arguments.get("command_description") or "").strip()
            if desc:
                desc = desc[0].upper() + desc[1:]
            return f"<b>Bash</b> {desc}".strip()
        return f"<b>{self._display_name(call.name)}</b>"

    def _status_counts_text(self) -> str:
        ok = sum(1 for c in self._calls if c.success is True)
        fail = sum(1 for c in self._calls if c.success is False)
        running = sum(1 for c in self._calls if c.success is None)
        parts: list[str] = []
        if running:
            parts.append(f"{running} running")
        if ok:
            parts.append(f"{ok} ok")
        if fail:
            parts.append(f"{fail} error")
        return ", ".join(parts)

    def _clear_details(self) -> None:
        for i in reversed(range(self._details_layout.count())):
            widget = self._details_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def _build_copy_row(self, label: str, content: str) -> QFrame:
        row = QFrame()
        row.setObjectName("bashDetailRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.setSpacing(8)

        tag = QLabel(label)
        tag.setObjectName("bashDetailTag")
        row_layout.addWidget(tag, 0)

        text = QLabel(content)
        text.setObjectName("bashDetailText")
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setWordWrap(False)
        text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        text.setFixedHeight(20)
        row_layout.addWidget(text, 1)

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("bashCopyBtn")
        copy_btn.setVisible(False)
        copy_btn.clicked.connect(lambda _=False, t=content: self._copy_text(t))
        row_layout.addWidget(copy_btn, 0, Qt.AlignmentFlag.AlignRight)

        def _set_hover(visible: bool) -> None:
            copy_btn.setVisible(visible)

        row.enterEvent = lambda e: (_set_hover(True), QFrame.enterEvent(row, e))[1]  # type: ignore[method-assign]
        row.leaveEvent = lambda e: (_set_hover(False), QFrame.leaveEvent(row, e))[1]  # type: ignore[method-assign]

        return row

    def _copy_text(self, text: str) -> None:
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def _build_bash_detail(self, call: ToolCall) -> QWidget:
        card = QFrame()
        card.setObjectName("bashDetailCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        command = str(call.arguments.get("command") or "").strip()
        if not command and isinstance(call.result, dict):
            command = str(call.result.get("command") or "").strip()
        result_dict = call.result if isinstance(call.result, dict) else {}
        stdout = str(result_dict.get("stdout") or "").strip()
        stderr = str(result_dict.get("stderr") or "").strip()
        output = (stdout + ("\n" + stderr if stderr else "")).strip()
        if call.error:
            output = "Tool execution failed"

        in_row = self._build_copy_row("IN", command)
        out_row = self._build_copy_row("OUT", output)
        layout.addWidget(in_row)

        divider = QFrame()
        divider.setObjectName("bashDetailDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        layout.addWidget(out_row)
        card.setMaximumHeight(120)
        return card

    def _render_details(self) -> None:
        self._clear_details()
        for call in self._calls:
            detail_text = self._call_detail_text(call)
            if not detail_text:
                continue
            if call.name == "bash":
                self._details_layout.addWidget(self._build_bash_detail(call))
                continue
            detail = QLabel(detail_text)
            detail.setObjectName("toolCallDetail")
            detail.setWordWrap(True)
            detail.setTextFormat(Qt.TextFormat.AutoText)
            self._details_layout.addWidget(detail)

    def _update_display(self) -> None:
        if not self._calls:
            return

        if len(self._calls) == 1:
            call = self._calls[0]
            timer = self._timer_text(call)
            text = f"{self._status_dot(call.success)} {self._header_text_for_call(call)}"
            if timer:
                text += f" {timer}"
            self._header_btn.setText(text)
        else:
            running = any(c.success is None for c in self._calls)
            failed = any(c.success is False for c in self._calls)
            success = not running and not failed
            dot = self._status_dot(None if running else success)
            joined = " ".join(self._header_text_for_call(c) for c in self._calls)
            timer = ""
            if running:
                timer = f" {max((c.elapsed_seconds for c in self._calls if c.success is None), default=0)}s"
            self._header_btn.setText(f"{dot} {joined}{timer}")

        self._header_btn.setEnabled(self._any_expandable())
        self._render_details()
        self._details.setVisible(self._expanded and self._any_expandable())
        if any(c.success is None for c in self._calls):
            if not self._tick_timer.isActive():
                self._tick_timer.start()
        else:
            self._tick_timer.stop()

    def is_expanded(self) -> bool:
        return self._expanded

    def get_summary_text(self) -> str:
        return self._header_btn.text()
