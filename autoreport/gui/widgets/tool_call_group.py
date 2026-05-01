"""Collapsible tool call group — Cline code-block style with monospace and editor colors."""

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

# Cline/VSCode dark theme color tokens
C = {
    "code_bg": "#1e1e1e",
    "code_fg": "#cccccc",
    "border": "#3c3c3c",
    "muted": "#8b949e",
    "success": "#4ec9b0",
    "error": "#f14c4c",
    "hover": "#2a2d2e",
    "focus": "#007acc",
}


@dataclass
class ToolCall:
    """Data class for a single tool call."""

    name: str
    arguments: dict
    success: bool
    duration_ms: int
    result: Any | None = None
    error: str | None = None


class ToolCallGroup(QWidget):
    """Collapsible group of tool calls — Cline code-block pattern.

    Collapsed: "✓ read_file (0.3s)  ▶"
    Expanded:  Each tool with status, duration, result/error in monospace detail.
    """

    expanded_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._calls: list[ToolCall] = []
        self._expanded = False

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)  # px-4 + inner padding
        layout.setSpacing(0)

        # Outer frame matching Cline code-block
        self._frame = QFrame()
        self._frame.setObjectName("toolCallFrame")
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(10, 9, 10, 9)  # py-[9px] px-2.5
        frame_layout.setSpacing(4)

        # Header — clickable summary row
        self._header_btn = QPushButton()
        self._header_btn.setObjectName("toolCallHeader")
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.clicked.connect(self._on_toggle)
        frame_layout.addWidget(self._header_btn)

        # Details panel — hidden when collapsed
        self._details_container = QWidget()
        self._details_container.setObjectName("toolCallDetails")
        self._details_layout = QVBoxLayout(self._details_container)
        self._details_layout.setContentsMargins(0, 6, 0, 0)
        self._details_layout.setSpacing(3)
        frame_layout.addWidget(self._details_container)

        layout.addWidget(self._frame)

    def add_tool_call(
        self,
        name: str,
        arguments: dict,
        success: bool,
        duration_ms: int,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        call = ToolCall(
            name=name,
            arguments=arguments,
            success=success,
            duration_ms=duration_ms,
            result=result,
            error=error,
        )
        self._calls.append(call)
        self._update_display()

    def _on_toggle(self) -> None:
        self._expanded = not self._expanded
        self._details_container.setVisible(self._expanded)
        self.expanded_changed.emit(self._expanded)
        self._update_display()

    def _update_display(self) -> None:
        success_count = sum(1 for c in self._calls if c.success)
        fail_count = len(self._calls) - success_count
        total_duration = sum(c.duration_ms for c in self._calls) / 1000.0

        # Status icon
        icon = "✔" if fail_count == 0 else "✘"  # heavy check / ballot x
        arrow = "▼" if self._expanded else "▶"  # down / right triangle

        # Build header text
        if len(self._calls) == 1:
            c = self._calls[0]
            header_text = f"  {icon} {c.name} ({c.duration_ms / 1000:.1f}s)  {arrow}"
        elif len(self._calls) <= 3:
            names = ", ".join(c.name for c in self._calls)
            header_text = f"  {icon} {names} ({total_duration:.1f}s)  {arrow}"
        else:
            shown = ", ".join(c.name for c in self._calls[:3])
            header_text = f"  {icon} {shown} +{len(self._calls) - 3} more ({total_duration:.1f}s)  {arrow}"

        self._header_btn.setText(header_text)

        # Rebuild details
        for i in reversed(range(self._details_layout.count())):
            w = self._details_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        for call in self._calls:
            call_icon = "✔" if call.success else "✘"
            dur = f"{call.duration_ms / 1000:.1f}s"

            if call.error:
                detail_text = f"  {call_icon} {call.name} ({dur})\n    error: {call.error}"
            elif call.result is not None:
                result_str = str(call.result)[:120]
                detail_text = f"  {call_icon} {call.name} ({dur})\n    result: {result_str}"
            else:
                detail_text = f"  {call_icon} {call.name} ({dur})"

            detail = QLabel(detail_text)
            detail.setObjectName("toolCallDetail")
            detail.setWordWrap(True)
            self._details_layout.addWidget(detail)

        self._details_container.setVisible(self._expanded)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#toolCallFrame {{
                background-color: {C["code_bg"]};
                border: 1px solid {C["border"]};
                border-radius: 2px;
            }}
            QPushButton#toolCallHeader {{
                background-color: transparent;
                border: none;
                color: {C["code_fg"]};
                font-family: "Consolas", "Monaco", "Courier New", monospace;
                font-size: 12px;
                text-align: left;
                padding: 0px;
            }}
            QPushButton#toolCallHeader:hover {{
                color: {C["focus"]};
            }}
            QLabel#toolCallDetail {{
                color: {C["code_fg"]};
                font-family: "Consolas", "Monaco", "Courier New", monospace;
                font-size: 11px;
                padding: 4px 8px;
                border-radius: 2px;
                background-color: transparent;
            }}
        """)

    def is_expanded(self) -> bool:
        return self._expanded

    def get_summary_text(self) -> str:
        return self._header_btn.text()
