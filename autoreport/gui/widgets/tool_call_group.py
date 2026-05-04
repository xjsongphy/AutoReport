"""Collapsible tool call group — VS Code Copilot Chat style.

VS Code tool invocation part:
  border: 1px solid var(--vscode-widget-border)
  border-radius: var(--vscode-cornerRadius-medium)  (~6px)
  background: var(--vscode-editor-background)
  margin: 4px 0
  .output-title: padding 8px 12px, background editorWidget, border-bottom
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
    """Collapsible group of tool calls matching VS Code tool invocation part."""

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
        arrow = "▾" if self._expanded else "▸"

        if len(self._calls) == 1:
            c = self._calls[0]
            status = "✓" if c.success else "✗"
            self._header_btn.setText(f"  {arrow} {self._display_name(c.name)}  {c.duration_ms / 1000:.1f}s  {status}")
        else:
            from collections import Counter
            counts = Counter(c.name for c in self._calls)
            parts = [f"{self._display_name(name)} ({cnt})" if cnt > 1 else self._display_name(name) for name, cnt in counts.items()]
            tool_summary = " · ".join(parts)
            total = sum(c.duration_ms for c in self._calls) / 1000
            status = f"{ok}✓" if fail == 0 else f"{ok}✓ {fail}✗"
            self._header_btn.setText(f"  {arrow} {tool_summary}  {total:.1f}s  {status}")

        for i in reversed(range(self._details_layout.count())):
            w = self._details_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        for call in self._calls:
            status = "✓" if call.success else "✗"
            dur = f"{call.duration_ms / 1000:.1f}s"
            parts = [f"  {status} {self._display_name(call.name)} ({dur})"]
            if call.error:
                parts.append(f"    error: {call.error}")
            elif call.result is not None:
                parts.append(f"    → {str(call.result)[:200]}")

            detail = QLabel("\n".join(parts))
            detail.setObjectName("toolCallDetail")
            detail.setWordWrap(True)
            self._details_layout.addWidget(detail)

        self._details.setVisible(self._expanded)

    def is_expanded(self) -> bool:
        return self._expanded

    def get_summary_text(self) -> str:
        return self._header_btn.text()
