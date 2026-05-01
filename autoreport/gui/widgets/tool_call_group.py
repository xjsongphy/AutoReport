"""Collapsible tool call group component."""

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


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
    """Collapsible group of tool calls with status display.

    Collapsed: "✓ 3 tools executed (2.3s) [▶]"
    Expanded: Each tool with details
    """

    expanded_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None):
        """Initialize tool call group."""
        super().__init__(parent)
        self._calls: list[ToolCall] = []
        self._expanded = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        # Header/summary (always visible)
        self._header_btn = QPushButton()
        self._header_btn.setObjectName("toolCallHeader")
        self._header_btn.setCheckable(True)
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._header_btn)

        # Details container (hidden when collapsed)
        self._details_container = QWidget()
        self._details_layout = QVBoxLayout(self._details_container)
        self._details_layout.setContentsMargins(12, 4, 4, 4)
        self._details_layout.setSpacing(2)
        layout.addWidget(self._details_container)

        self._apply_style()
        self._update_display()

    def add_tool_call(
        self,
        name: str,
        arguments: dict,
        success: bool,
        duration_ms: int,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        """Add a tool call to the group.

        Args:
            name: Tool name
            arguments: Tool arguments
            success: Whether tool call succeeded
            duration_ms: Execution duration in milliseconds
            result: Optional result
            error: Optional error message
        """
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
        """Handle expand/collapse toggle."""
        self._expanded = self._header_btn.isChecked()
        self._details_container.setVisible(self._expanded)
        self.expanded_changed.emit(self._expanded)
        self._update_display()

    def _update_display(self) -> None:
        """Update display based on current state."""
        # Update header
        success_count = sum(1 for c in self._calls if c.success)
        total_duration = sum(c.duration_ms for c in self._calls) / 1000.0

        icon = "✓" if success_count == len(self._calls) else "✗"
        arrow = "▼" if self._expanded else "▶"

        if len(self._calls) <= 3:
            # Show all tool names in collapsed state
            names = ", ".join(c.name for c in self._calls)
            header_text = f"  {icon} {names} ({total_duration:.1f}s) [{arrow}]"
        else:
            # Truncate with "+N more"
            first_names = ", ".join(c.name for c in self._calls[:3])
            header_text = f"  {icon} {first_names} +{len(self._calls) - 3} more ({total_duration:.1f}s) [{arrow}]"

        self._header_btn.setText(header_text)

        # Update details
        # Clear existing labels
        for i in reversed(range(self._details_layout.count())):
            self._details_layout.itemAt(i).widget().setParent(None)

        # Add detail labels for each call
        for call in self._calls:
            detail = QLabel()
            detail.setObjectName("toolCallDetail")

            call_icon = "✓" if call.success else "✗"
            detail_text = f"    {call_icon} {call.name} ({call.duration_ms / 1000:.1f}s)"

            if call.error:
                detail_text += f"\n      error: {call.error}"
            elif call.result:
                # Show abbreviated result
                result_str = str(call.result)[:50]
                detail_text += f"\n      result: {result_str}"

            detail.setText(detail_text)
            detail.setWordWrap(True)
            self._details_layout.addWidget(detail)

        self._details_container.setVisible(self._expanded)

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        if dark:
            header_fg = "#cccccc"
            detail_bg = "#252526"
        else:
            header_fg = "#1a1a1a"
            detail_bg = "#f5f5f5"

        self.setStyleSheet(f"""
            QPushButton#toolCallHeader {{
                background-color: transparent;
                border: none;
                color: {header_fg};
                font-family: "Consolas", "Monaco", monospace;
                font-size: 12px;
                text-align: left;
                padding: 2px 4px;
            }}
            QLabel#toolCallDetail {{
                background-color: {detail_bg};
                color: {header_fg};
                font-family: "Consolas", "Monaco", monospace;
                font-size: 11px;
                padding: 4px 8px;
                border-radius: 3px;
            }}
        """)

    def is_expanded(self) -> bool:
        """Return whether group is expanded."""
        return self._expanded

    def get_summary_text(self) -> str:
        """Get summary text for testing."""
        return self._header_btn.text()
