"""Collapsible tool call group matching the chat timeline tool-call style."""

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


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
        if call.error:
            return f"error: {call.error}"
        if call.result is not None:
            return str(call.result)[:200]
        if call.success is not None:
            return self._header_text_for_call(call)
        return None

    def _is_expandable(self, call: ToolCall) -> bool:
        return call.expandable and bool(self._call_detail_text(call))

    def _any_expandable(self) -> bool:
        return any(self._is_expandable(call) for call in self._calls)

    def _header_arrow(self) -> str:
        if not self._any_expandable():
            return "-"
        return "▾" if self._expanded else "▸"

    def _duration_text(self, duration_ms: int) -> str:
        if duration_ms <= 0:
            return "0s"
        return f"{round(duration_ms / 1000)}s"

    def _status_text_for_call(self, call: ToolCall) -> str:
        if call.success is None:
            return "running"
        return "ok" if call.success else "error"

    def _header_text_for_call(self, call: ToolCall) -> str:
        return call.summary or self._display_name(call.name)

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

    def _render_details(self) -> None:
        self._clear_details()
        for call in self._calls:
            detail_text = self._call_detail_text(call)
            if not detail_text:
                continue
            detail = QLabel(detail_text)
            detail.setObjectName("toolCallDetail")
            detail.setWordWrap(True)
            detail.setTextFormat(Qt.TextFormat.PlainText)
            self._details_layout.addWidget(detail)

    def _update_display(self) -> None:
        if not self._calls:
            return

        arrow = self._header_arrow()

        if len(self._calls) == 1:
            call = self._calls[0]
            parts = [arrow, self._header_text_for_call(call)]
            duration = self._duration_text(call.duration_ms)
            if duration:
                parts.append(duration)
            parts.append(self._status_text_for_call(call))
            self._header_btn.setText("  " + "  ".join(parts))
        else:
            from collections import Counter

            counts = Counter(call.name for call in self._calls)
            names = [
                f"{self._display_name(name)} ({count})" if count > 1 else self._display_name(name)
                for name, count in counts.items()
            ]
            parts = [arrow, ", ".join(names)]
            total_ms = sum(call.duration_ms for call in self._calls)
            parts.append(self._duration_text(total_ms))
            status = self._status_counts_text()
            if status:
                parts.append(status)
            self._header_btn.setText("  " + "  ".join(parts))

        self._header_btn.setEnabled(self._any_expandable())
        self._render_details()
        self._details.setVisible(self._expanded and self._any_expandable())

    def is_expanded(self) -> bool:
        return self._expanded

    def get_summary_text(self) -> str:
        return self._header_btn.text()
