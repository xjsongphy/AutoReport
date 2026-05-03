"""Collapsible tool call group — VS Code Copilot Chat style.

Collapsed: single line with status icon, tool name, duration, expand arrow
Expanded: each tool call with result details
"""

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


@dataclass
class ToolCall:
    name: str
    arguments: dict
    success: bool
    duration_ms: int
    result: Any | None = None
    error: str | None = None


class ToolCallGroup(QWidget):
    """Collapsible group of tool calls — compact VS Code style."""

    expanded_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._calls: list[ToolCall] = []
        self._expanded = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 2, 16, 2)
        layout.setSpacing(0)

        self._header_btn = QPushButton()
        self._header_btn.setObjectName("toolCallHeader")
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._header_btn)

        self._details = QWidget()
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
        success: bool,
        duration_ms: int,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        self._calls.append(ToolCall(name, arguments, success, duration_ms, result, error))
        self._update_display()

    def _on_toggle(self) -> None:
        self._expanded = not self._expanded
        self._details.setVisible(self._expanded)
        self.expanded_changed.emit(self._expanded)
        self._update_display()

    def _update_display(self) -> None:
        if not self._calls:
            return

        ok = sum(1 for c in self._calls if c.success)
        fail = len(self._calls) - ok
        icon = "✓" if fail == 0 else "✗"
        arrow = "▾" if self._expanded else "▸"

        if len(self._calls) == 1:
            c = self._calls[0]
            self._header_btn.setText(f"  {icon} {c.name}  {c.duration_ms / 1000:.1f}s  {arrow}")
        else:
            total = sum(c.duration_ms for c in self._calls) / 1000
            self._header_btn.setText(
                f"  {icon} {len(self._calls)} tools  {total:.1f}s  {arrow}"
            )

        # Rebuild details
        for i in reversed(range(self._details_layout.count())):
            w = self._details_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        for call in self._calls:
            status = "✓" if call.success else "✗"
            dur = f"{call.duration_ms / 1000:.1f}s"
            parts = [f"  {status} {call.name} ({dur})"]
            if call.error:
                parts.append(f"  error: {call.error}")
            elif call.result is not None:
                parts.append(f"  → {str(call.result)[:200]}")

            detail = QLabel("\n".join(parts))
            detail.setObjectName("toolCallDetail")
            detail.setWordWrap(True)
            self._details_layout.addWidget(detail)

        self._details.setVisible(self._expanded)

    def is_expanded(self) -> bool:
        return self._expanded

    def get_summary_text(self) -> str:
        return self._header_btn.text()
