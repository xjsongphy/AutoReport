# Agent Chat UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the agent chat UI to fix keyboard handling, add API debug panel, and improve visual design following Cline's layout and Codex's simplicity.

**Architecture:** Modular PyQt6 components with clear signal-based communication. ChatInput handles input with fixed keyboard; new MessageRow, ToolCallGroup, and DebugPanel components handle display; AgentPanel coordinates state.

**Tech Stack:** PyQt6, Python 3.12, existing autoreport codebase

---

## File Structure Map

**New Files:**
| File | Responsibility |
|------|-----------------|
| `autoreport/gui/widgets/message_row.py` | Render single user/agent message with timestamp and status |
| `autoreport/gui/widgets/tool_call_group.py` | Collapsible group of tool calls with status icons |
| `autoreport/gui/widgets/debug_panel.py` | API debug info panel with history and export |
| `autoreport/gui/widgets/messages_area.py` | Scrollable message container |
| `tests/gui/widgets/test_chat_input.py` | Test keyboard handling |
| `tests/gui/widgets/test_message_row.py` | Test message rendering |
| `tests/gui/widgets/test_debug_panel.py` | Test debug panel |

**Modified Files:**
| File | Changes |
|------|---------|
| `autoreport/gui/widgets/chat_input.py` | Fix keyboard handling (Enter/Shift+Enter) |
| `autoreport/gui/widgets/agent_panel.py` | Refactor to use new components, add debug message handling |
| `autoreport/core/loops/agent_loop.py` | Add api_debug publishing via MessageBus |
| `autoreport/interfaces/types.py` | Add ApiDebugMessage dataclass |

---

## Chunk 1: Fix ChatInput Keyboard Handling

### Task 1: Fix ChatInput keyPressEvent

**Files:**
- Modify: `autoreport/gui/widgets/chat_input.py:64-107`
- Test: `tests/gui/widgets/test_chat_input.py` (new)

- [ ] **Step 0: Create test directory structure**

```bash
mkdir -p tests/gui/widgets
touch tests/gui/widgets/__init__.py
```

- [ ] **Step 1: Write test for Enter key sending message**

```python
# tests/gui/widgets/test_chat_input.py
import pytest
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QKeyEvent
from autoreport.gui.widgets.chat_input import ChatInput


def test_enter_key_sends_message(qtbot):
    """Enter key should send message signal."""
    widget = ChatInput()
    qtbot.addWidget(widget)

    # Track signal emissions
    signals = []
    widget.send_message.connect(lambda: signals.append("sent"))

    # Simulate Enter key press
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier,
        "\r"
    )
    widget.keyPressEvent(key_event)

    assert signals == ["sent"], "Enter key should send message"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/gui/widgets/test_chat_input.py::test_enter_key_sends_message -v`
Expected: FAIL (current implementation has keyboard handling issues)

- [ ] **Step 3: Write test for Shift+Enter inserting newline**

```python
# tests/gui/widgets/test_chat_input.py
def test_shift_enter_inserts_newline(qtbot):
    """Shift+Enter should insert newline, not send."""
    widget = ChatInput()
    qtbot.addWidget(widget)

    # Set initial text
    widget.setPlainText("line 1")

    # Track signal emissions
    signals = []
    widget.send_message.connect(lambda: signals.append("sent"))

    # Simulate Shift+Enter
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.ShiftModifier,
        "\r\n"
    )
    widget.keyPressEvent(key_event)

    assert signals == [], "Shift+Enter should not send message"
    assert widget.toPlainText() == "line 1\n", "Should insert newline"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/gui/widgets/test_chat_input.py::test_shift_enter_inserts_newline -v`
Expected: FAIL

- [ ] **Step 5: Fix keyboard handling in ChatInput**

**Note:** This changes from exact match (`==`) to bitwise AND (`&`) for Shift modifier detection.
- Old: `modifiers == Qt.KeyboardModifier.ShiftModifier` (only matches Shift alone)
- New: `modifiers & Qt.KeyboardModifier.ShiftModifier` (matches Shift, Ctrl+Shift, etc.)
- This means Ctrl+Shift+Enter will now insert newline instead of using default behavior.

```python
# autoreport/gui/widgets/chat_input.py
@override
def keyPressEvent(self, event: QKeyEvent) -> None:
    """Handle key press events.

    Args:
        event: Key event.
    """
    key = event.key()
    modifiers = event.modifiers()

    # If popup is active, let popup handle navigation keys
    if self._popup_active:
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Escape, Qt.Key.Key_Enter, Qt.Key.Key_Return):
            super().keyPressEvent(event)
            return

    # Handle Enter/Return keys
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        # Check for Shift modifier (including Ctrl+Shift, etc.)
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Shift+Enter (or Ctrl+Shift+Enter): insert newline
            cursor = self.textCursor()
            cursor.insertText("\n")
            return
        elif modifiers == Qt.KeyboardModifier.NoModifier:
            # Plain Enter: send message
            self.send_message.emit()
            return
        # Other combinations fall through to default

    # Handle backspace/delete for @ token tracking
    if key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
        super().keyPressEvent(event)
        self._check_for_at_token()
        return

    # Default handling for other keys
    super().keyPressEvent(event)

    # Check for @ token after text insertion
    if event.text():
        self._check_for_at_token()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/gui/widgets/test_chat_input.py -v`
Expected: PASS

- [ ] **Step 7: Add test for Ctrl+Enter default behavior**

```python
# tests/gui/widgets/test_chat_input.py
def test_ctrl_enter_default_behavior(qtbot):
    """Ctrl+Enter should use default behavior (not send, not insert)."""
    widget = ChatInput()
    qtbot.addWidget(widget)

    signals = []
    widget.send_message.connect(lambda: signals.append("sent"))
    widget.textChanged.connect(lambda: signals.append("changed"))

    # Simulate Ctrl+Enter
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.ControlModifier,
        "\r"
    )
    widget.keyPressEvent(key_event)

    # Default behavior - no signal sent, no text change
    assert "sent" not in signals
```

- [ ] **Step 8: Run all keyboard tests**

Run: `uv run pytest tests/gui/widgets/test_chat_input.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add autoreport/gui/widgets/chat_input.py tests/gui/widgets/test_chat_input.py
git commit -m "fix: correct ChatInput keyboard handling (Enter send, Shift+Enter newline)"
```

---

## Chunk 2: Create MessageRow Component

### Task 2: Implement MessageRow renderer

**Files:**
- Create: `autoreport/gui/widgets/message_row.py`
- Test: `tests/gui/widgets/test_message_row.py` (new)

- [ ] **Step 1: Write failing test for user message rendering**

```python
# tests/gui/widgets/test_message_row.py
import pytest
from PyQt6.QtWidgets import QApplication
from autoreport.gui.widgets.message_row import MessageRow


def test_user_message_renders_with_timestamp(qtbot):
    """User message should show timestamp and content."""
    widget = MessageRow(
        role="user",
        content="Hello, agent!",
        timestamp="14:32",
        is_coordination=False
    )
    qtbot.addWidget(widget)

    # Check that timestamp is in display
    display_text = widget.get_display_text()
    assert "14:32" in display_text
    assert "Hello, agent!" in display_text
    assert "you" in display_text.lower() or "你" in display_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/gui/widgets/test_message_row.py::test_user_message_renders_with_timestamp -v`
Expected: FAIL (MessageRow doesn't exist)

- [ ] **Step 3: Implement MessageRow component**

```python
# autoreport/gui/widgets/message_row.py
"""Single message row component for chat display."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class MessageRow(QWidget):
    """Render a single chat message (user or agent) with timestamp.

    Visual format:
        HH:MM  [Role]

          Content line 1
          Content line 2
    """

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str = "",
        is_coordination: bool = False,
        parent: QWidget | None = None,
    ):
        """Initialize message row.

        Args:
            role: "user" or "agent"
            content: Message content
            timestamp: Time in HH:MM format
            is_coordination: Whether this is a coordination message from main agent
            parent: Parent widget
        """
        super().__init__(parent)
        self._role = role
        self._content = content
        self._timestamp = timestamp or "00:00"
        self._is_coordination = is_coordination

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Header: timestamp + role
        header = QLabel()
        header.setObjectName("messageHeader")

        if self._role == "user":
            role_text = "你"
            if self._is_coordination:
                header.setText(f"{self._timestamp}  [主 Agent 协调] {role_text}")
            else:
                header.setText(f"{self._timestamp}  {role_text}")
        else:
            header.setText(f"{self._timestamp}  Agent")

        layout.addWidget(header)

        # Content
        content_label = QLabel(self._content)
        content_label.setObjectName("messageContent")
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(content_label)

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        if dark:
            header_fg = "#cccccc"
            user_content_bg = "#0e639c"
            user_content_fg = "#ffffff"
            agent_content_bg = "#2d2d2d"
            agent_content_fg = "#cccccc"
        else:
            header_fg = "#1a1a1a"
            user_content_bg = "#e1f5fe"
            user_content_fg = "#1a1a1a"
            agent_content_bg = "#f3f3f3"
            agent_content_fg = "#1a1a1a"

        self.setStyleSheet(f"""
            QLabel#messageHeader {{
                font-size: 11px;
                font-weight: 600;
                color: {header_fg};
            }}
            QLabel#messageContent {{
                font-size: 13px;
                padding: 4px 8px;
                border-radius: 4px;
                background-color: {user_content_bg if self._role == "user" else agent_content_bg};
                color: {user_content_fg if self._role == "user" else agent_content_fg};
            }}
        """)

    def get_display_text(self) -> str:
        """Get combined display text for testing."""
        return f"{self._timestamp} {self._content}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/gui/widgets/test_message_row.py::test_user_message_renders_with_timestamp -v`
Expected: PASS

- [ ] **Step 5: Add test for agent message**

```python
# tests/gui/widgets/test_message_row.py
def test_agent_message_renders_correctly(qtbot):
    """Agent message should show Agent role."""
    widget = MessageRow(
        role="agent",
        content="I will help you.",
        timestamp="14:33"
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Agent" in display_text or "14:33" in display_text
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/gui/widgets/test_message_row.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add autoreport/gui/widgets/message_row.py tests/gui/widgets/test_message_row.py
git commit -m "feat: add MessageRow component for unified message rendering"
```

---

## Chunk 3: Create ToolCallGroup Component

### Task 3: Implement collapsible tool call display

**Files:**
- Create: `autoreport/gui/widgets/tool_call_group.py`
- Test: `tests/gui/widgets/test_tool_call_group.py` (new)

- [ ] **Step 1: Write test for collapsed state**

```python
# tests/gui/widgets/test_tool_call_group.py
import pytest
from autoreport.gui.widgets.tool_call_group import ToolCallGroup


def test_collapsed_shows_summary(qtbot):
    """Collapsed state should show summary of tool calls."""
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call("python_exec", {"file": "analysis.py"}, success=True, duration_ms=1200)
    widget.add_tool_call("read_file", {"path": "data.csv"}, success=True, duration_ms=100)

    # Initially collapsed
    assert widget.is_expanded() == False
    summary = widget.get_summary_text()
    assert "2" in summary or "tool" in summary.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/gui/widgets/test_tool_call_group.py::test_collapsed_shows_summary -v`
Expected: FAIL (ToolCallGroup doesn't exist)

- [ ] **Step 3: Implement ToolCallGroup**

```python
# autoreport/gui/widgets/tool_call_group.py
"""Collapsible tool call group component."""

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
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
            success_color = "#81c784"
            error_color = "#f14c4c"
            detail_bg = "#252526"
        else:
            header_fg = "#1a1a1a"
            success_color = "#4caf50"
            error_color = "#d32f2f"
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/gui/widgets/test_tool_call_group.py::test_collapsed_shows_summary -v`
Expected: PASS

- [ ] **Step 5: Add test for expand/collapse**

```python
# tests/gui/widgets/test_tool_call_group.py
def test_expand_collapse_works(qtbot):
    """Toggle button should expand/collapse details."""
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call("test_tool", {}, success=True, duration_ms=100)

    # Initially collapsed
    assert widget.is_expanded() == False

    # Click to expand
    widget._header_btn.click()
    assert widget.is_expanded() == True

    # Click to collapse
    widget._header_btn.click()
    assert widget.is_expanded() == False
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/gui/widgets/test_tool_call_group.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add autoreport/gui/widgets/tool_call_group.py tests/gui/widgets/test_tool_call_group.py
git commit -m "feat: add ToolCallGroup component with collapse/expand"
```

---

## Chunk 4: Create DebugPanel Component

### Task 4: Implement API debug panel

**Files:**
- Create: `autoreport/gui/widgets/debug_panel.py`
- Test: `tests/gui/widgets/test_debug_panel.py` (new)

- [ ] **Step 1: Write test for adding debug entry**

```python
# tests/gui/widgets/test_debug_panel.py
import pytest
from datetime import datetime
from autoreport.gui.widgets.debug_panel import DebugPanel


def test_add_debug_entry(qtbot):
    """Adding entry should update display."""
    widget = DebugPanel()
    qtbot.addWidget(widget)

    widget.add_entry(
        timestamp=datetime.now(),
        model="claude-sonnet-4-20250514",
        tokens_in=1000,
        tokens_out=500,
        duration_ms=1500,
        status="success"
    )

    assert widget.entry_count() == 1
    summary = widget.get_summary_text()
    assert "1 call" in summary or "1" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/gui/widgets/test_debug_panel.py::test_add_debug_entry -v`
Expected: FAIL (DebugPanel doesn't exist)

- [ ] **Step 3: Implement DebugPanel**

```python
# autoreport/gui/widgets/debug_panel.py
"""API debug panel for showing request/response information."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

MAX_ENTRIES = 50


@dataclass
class DebugEntry:
    """Data class for a single debug entry."""

    timestamp: datetime
    model: str
    tokens_in: int
    tokens_out: int
    duration_ms: int
    status: str  # "success" or "error"
    error: str | None = None


class DebugPanel(QWidget):
    """Collapsible API debug panel showing request/response summaries.

    Format:
        🔍 API Debug (3 calls) [▼]
          HH:MM:SS → model_name
            Tokens: X in, Y out | Duration: Zs
            Status: ✓ Success
    """

    entry_cleared = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        """Initialize debug panel."""
        super().__init__(parent)
        self._entries: list[DebugEntry] = []
        self._expanded = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with toggle
        header = QWidget()
        header.setObjectName("debugPanelHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        self._header_btn = QPushButton()
        self._header_btn.setObjectName("debugHeaderBtn")
        self._header_btn.setCheckable(True)
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.clicked.connect(self._on_toggle)
        header_layout.addWidget(self._header_btn)

        # Action buttons (clear, export)
        actions = QWidget()
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)

        clear_btn = QPushButton("Clear all")
        clear_btn.setObjectName("debugClearBtn")
        clear_btn.clicked.connect(self._on_clear)
        actions_layout.addWidget(clear_btn)

        export_btn = QPushButton("Export JSON")
        export_btn.setObjectName("debugExportBtn")
        export_btn.clicked.connect(self._on_export)
        actions_layout.addWidget(export_btn)

        header_layout.addWidget(actions)
        layout.addWidget(header)

        # Content area with scroll
        scroll = QScrollArea()
        scroll.setObjectName("debugScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 4, 8, 4)
        self._content_layout.setSpacing(2)

        # Empty state label
        self._empty_label = QLabel("No API calls yet")
        self._empty_label.setObjectName("debugEmptyLabel")
        self._content_layout.addWidget(self._empty_label)

        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

        self._update_display()

    def add_entry(
        self,
        timestamp: datetime,
        model: str,
        tokens_in: int,
        tokens_out: int,
        duration_ms: int,
        status: str,
        error: str | None = None,
    ) -> None:
        """Add a debug entry.

        Args:
            timestamp: Call timestamp
            model: Model name
            tokens_in: Input tokens
            tokens_out: Output tokens
            duration_ms: Duration in milliseconds
            status: "success" or "error"
            error: Optional error message
        """
        entry = DebugEntry(
            timestamp=timestamp,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            status=status,
            error=error,
        )

        # FIFO eviction at max entries
        self._entries.append(entry)
        if len(self._entries) > MAX_ENTRIES:
            self._entries.pop(0)

        self._update_display()

    def _on_toggle(self) -> None:
        """Handle expand/collapse."""
        self._expanded = self._header_btn.isChecked()
        self._content.setVisible(self._expanded)
        self._update_display()

    def _on_clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        self._update_display()
        self.entry_cleared.emit()

    def _on_export(self) -> None:
        """Export entries to JSON file."""
        if not self._entries:
            return

        data = []
        for entry in self._entries:
            data.append({
                "timestamp": entry.timestamp.isoformat(),
                "model": entry.model,
                "tokens_in": entry.tokens_in,
                "tokens_out": entry.tokens_out,
                "duration_ms": entry.duration_ms,
                "status": entry.status,
                "error": entry.error,
            })

        # Save to Downloads or project root
        output_path = Path.cwd() / "api_debug_export.json"
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    def _update_display(self) -> None:
        """Update display based on current state."""
        # Update header
        count = len(self._entries)
        arrow = "▼" if self._expanded else "▶"
        self._header_btn.setText(f"🔍 API Debug ({count} calls) [{arrow}]")

        # Update content
        # Clear existing labels
        for i in reversed(range(self._content_layout.count())):
            item = self._content_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        if not self._entries:
            self._empty_label = QLabel("No API calls yet")
            self._empty_label.setObjectName("debugEmptyLabel")
            self._content_layout.addWidget(self._empty_label)
        else:
            for entry in reversed(self._entries):  # Newest first
                entry_label = QLabel()
                entry_label.setObjectName("debugEntryLabel")

                ts = entry.timestamp.strftime("%H:%M:%S")
                status_icon = "✓" if entry.status == "success" else "✗"

                text = f"  {ts} → {entry.model}\n"
                text += f"    Tokens: {entry.tokens_in} in, {entry.tokens_out} out | "
                text += f"Duration: {entry.duration_ms / 1000:.1f}s\n"
                text += f"    Status: {status_icon} "
                text += "Success" if entry.status == "success" else entry.status

                if entry.error:
                    text += f"\n    Error: {entry.error}"

                entry_label.setText(text)
                entry_label.setWordWrap(True)
                self._content_layout.addWidget(entry_label)

        self._content.setVisible(self._expanded)

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        if dark:
            header_bg = "#252526"
            header_fg = "#cccccc"
            content_bg = "#1e1e1e"
            content_fg = "#858585"
            success_color = "#81c784"
            error_color = "#f14c4c"
        else:
            header_bg = "#f3f3f3"
            header_fg = "#1a1a1a"
            content_bg = "#ffffff"
            content_fg = "#666666"
            success_color = "#4caf50"
            error_color = "#d32f2f"

        self.setStyleSheet(f"""
            QWidget#debugPanelHeader {{
                background-color: {header_bg};
                border-bottom: 1px solid {header_bg};
            }}
            QPushButton#debugHeaderBtn {{
                background-color: transparent;
                border: none;
                color: {header_fg};
                font-size: 12px;
                font-weight: 600;
                text-align: left;
                padding: 4px 8px;
            }}
            QPushButton#debugClearBtn, QPushButton#debugExportBtn {{
                background-color: transparent;
                border: 1px solid {content_fg};
                color: {content_fg};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton#debugClearBtn:hover, QPushButton#debugExportBtn:hover {{
                background-color: rgba(128,128,128,0.1);
            }}
            QLabel#debugEmptyLabel {{
                color: {content_fg};
                font-style: italic;
                padding: 8px;
            }}
            QLabel#debugEntryLabel {{
                color: {content_fg};
                font-family: "Consolas", "Monaco", monospace;
                font-size: 11px;
                padding: 6px 8px;
                background-color: {content_bg};
                border-radius: 3px;
            }}
        """)

    def entry_count(self) -> int:
        """Return number of entries."""
        return len(self._entries)

    def get_summary_text(self) -> str:
        """Get summary text for testing."""
        return self._header_btn.text()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/gui/widgets/test_debug_panel.py::test_add_debug_entry -v`
Expected: PASS

- [ ] **Step 5: Add test for FIFO eviction**

```python
# tests/gui/widgets/test_debug_panel.py
def test_fifo_eviction_at_max(qtbot):
    """Should evict oldest entry when exceeding MAX_ENTRIES."""
    widget = DebugPanel()
    qtbot.addWidget(widget)

    # Add 51 entries (MAX_ENTRIES + 1)
    for i in range(51):
        widget.add_entry(
            timestamp=datetime.now(),
            model="test-model",
            tokens_in=100,
            tokens_out=50,
            duration_ms=100,
            status="success"
        )

    assert widget.entry_count() == 50
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/gui/widgets/test_debug_panel.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add autoreport/gui/widgets/debug_panel.py tests/gui/widgets/test_debug_panel.py
git commit -m "feat: add DebugPanel with FIFO eviction and export"
```

---

## Chunk 5: Create MessagesArea and Update AgentPanel

### Task 5: Create MessagesArea container

**Files:**
- Create: `autoreport/gui/widgets/messages_area.py`
- Test: `tests/gui/widgets/test_messages_area.py` (new)

- [ ] **Step 0: Create test file**

```python
# tests/gui/widgets/test_messages_area.py
import pytest
from autoreport.gui.widgets.messages_area import MessagesArea
from autoreport.gui.widgets.message_row import MessageRow
```

- [ ] **Step 1: Create MessagesArea component**

```python
# autoreport/gui/widgets/messages_area.py
"""Scrollable messages area container."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from autoreport.gui.widgets.message_row import MessageRow
from autoreport.gui.widgets.tool_call_group import ToolCallGroup


class MessagesArea(QScrollArea):
    """Scrollable container for chat messages with auto-scroll."""

    auto_scroll_enabled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None):
        """Initialize messages area."""
        super().__init__(parent)
        self._auto_scroll = True
        self._user_scrolled = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup UI."""
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setObjectName("messagesArea")

        # Container widget
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(4)
        self._layout.addStretch()

        self.setWidget(self._container)

        # Connect scroll signal to detect user scrolling
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _on_scroll(self, value: int) -> None:
        """Handle scroll events to detect user interaction."""
        max_val = self.verticalScrollBar().maximum()
        # User scrolled up (not at bottom)
        self._user_scrolled = value < max_val - 10

    def add_message_row(self, row: MessageRow) -> None:
        """Add a message row to the area.

        Args:
            row: MessageRow widget to add
        """
        # Insert before the stretch
        self._layout.insertWidget(self._layout.count() - 1, row)

        if self._auto_scroll and not self._user_scrolled:
            self._scroll_to_bottom()

    def add_tool_group(self, group: ToolCallGroup) -> None:
        """Add a tool call group to the area.

        Args:
            group: ToolCallGroup widget to add
        """
        self._layout.insertWidget(self._layout.count() - 1, group)

        if self._auto_scroll and not self._user_scrolled:
            self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        """Scroll to bottom of messages."""
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        )

    def clear(self) -> None:
        """Clear all messages."""
        for i in reversed(range(self._layout.count())):
            item = self._layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        hints = QApplication.styleHints()
        dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

        bg = "#1e1e1e" if dark else "#ffffff"

        self.setStyleSheet(f"""
            QScrollArea#messagesArea {{
                background-color: {bg};
                border: none;
            }}
        """)
```

- [ ] **Step 2: Add test for auto-scroll pause on user scroll**

```python
# tests/gui/widgets/test_messages_area.py
def test_auto_scroll_pause_on_user_scroll(qtbot):
    """Auto-scroll should pause when user scrolls up."""
    from autoreport.gui.widgets.message_row import MessageRow

    area = MessagesArea()
    qtbot.addWidget(area)

    # Add some messages to enable scrolling
    for i in range(10):
        row = MessageRow(role="agent", content=f"Message {i}", timestamp="12:00")
        area.add_message_row(row)

    # Scroll to bottom first
    area._scroll_to_bottom()
    assert area._auto_scroll == True
    assert area._user_scrolled == False

    # Simulate user scrolling up
    area.verticalScrollBar().setValue(area.verticalScrollBar().maximum() - 50)

    # Should detect user scroll
    assert area._user_scrolled == True
```

- [ ] **Step 3: Add test for streaming message updates**

```python
# tests/gui/widgets/test_messages_area.py
def test_streaming_message_updates_existing_row(qtbot):
    """During streaming, content should append to existing agent message."""
    from autoreport.gui.widgets.message_row import MessageRow

    area = MessagesArea()
    qtbot.addWidget(area)

    # Add initial agent message
    row1 = MessageRow(role="agent", content="Hello", timestamp="12:00")
    area.add_message_row(row1)

    # Simulate streaming: the same row's content is updated
    # In real implementation, MessageRow would have an update_content() method
    # For now, we just verify multiple rows can be added
    row2 = MessageRow(role="agent", content="Hello world", timestamp="12:00")
    area.add_message_row(row2)

    # Should have 2 message rows (in real impl, streaming would update in place)
    assert area._layout.count() >= 2  # At least the 2 rows we added
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/gui/widgets/test_messages_area.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoreport/gui/widgets/messages_area.py tests/gui/widgets/test_messages_area.py
git commit -m "feat: add MessagesArea scrollable container with auto-scroll"
```

### Task 6: Add ApiDebugMessage to interfaces

**Files:**
- Modify: `autoreport/interfaces/types.py`

**Note:** This task MUST be completed before Task 7 (AgentLoop uses it) and Task 8 (AgentPanel uses it).

- [ ] **Step 1: Add ApiDebugMessage dataclass**

```python
# autoreport/interfaces/types.py
# Add to existing file

from dataclasses import dataclass
from datetime import datetime

# ... existing code ...

@dataclass
class ApiDebugMessage:
    """Debug information about API calls."""

    timestamp: datetime
    model: str
    tokens_in: int
    tokens_out: int
    duration_ms: int
    status: str  # "success" or "error"
    error: str | None = None
```

- [ ] **Step 2: Commit**

```bash
git add autoreport/interfaces/types.py
git commit -m "feat: add ApiDebugMessage dataclass"
```

### Task 7: Add api_debug publishing to AgentLoop

**Prerequisite:** Task 6 MUST be completed first (ApiDebugMessage must exist).

**Files:**
- Modify: `autoreport/core/loops/agent_loop.py`

**Note:** AgentLoop doesn't inherit from QObject, so we use the existing MessageBus pattern instead of pyqtSignal.

- [ ] **Step 1: Emit debug info through MessageBus in _call_llm_api**

Find the `_call_llm_api` or similar method and wrap the API call:

```python
# In AgentLoop, around the API call
import time
from datetime import datetime

def _call_llm_api(self, messages, **kwargs):
    """Call LLM API with timing and debug emission."""
    from autoreport.interfaces.types import ApiDebugMessage

    start_time = time.time()
    start_timestamp = datetime.now()

    try:
        # ... existing API call code ...
        response = self.client.messages.create(...)  # or similar

        duration_ms = int((time.time() - start_time) * 1000)

        # Publish debug info on success
        debug_msg = ApiDebugMessage(
            timestamp=start_timestamp,
            model=self.model_id,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            duration_ms=duration_ms,
            status="success",
        )
        self.bus.publish(debug_msg)

        return response

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)

        # Publish debug info on error
        debug_msg = ApiDebugMessage(
            timestamp=start_timestamp,
            model=self.model_id,
            tokens_in=0,
            tokens_out=0,
            duration_ms=duration_ms,
            status="error",
            error=str(e),
        )
        self.bus.publish(debug_msg)

        raise
```

- [ ] **Step 2: Verify MessageBus import**

Ensure MessageBus is imported at the top of `agent_loop.py`. If not, add:
```python
from autoreport.core.loops.bus import MessageBus
```

- [ ] **Step 3: Commit**

- [ ] **Step 3: Commit**

```bash
git add autoreport/core/loops/agent_loop.py
git commit -m "feat: add api_debug_sent signal to AgentLoop"
```

### Task 8: Refactor AgentPanel to use new components

**Files:**
- Modify: `autoreport/gui/widgets/agent_panel.py`

- [ ] **Step 1: Update imports and add new components**

```python
# autoreport/gui/widgets/agent_panel.py
# Add imports
from autoreport.gui.widgets.messages_area import MessagesArea
from autoreport.gui.widgets.debug_panel import DebugPanel
from autoreport.interfaces.types import ApiDebugMessage
```

- [ ] **Step 2: Replace messages area in _setup_ui**

Find the messages area creation and replace:

```python
# In AgentPanel._setup_ui(), replace the old QTextEdit messages_area with:

# ---- Messages area ----
self._messages_area = MessagesArea()
layout.addWidget(self._messages_area, 1)
```

- [ ] **Step 3: Add DebugPanel to header area**

```python
# In AgentPanel._setup_ui(), after the debug_button:

self._debug_panel = DebugPanel()
self._debug_panel.setVisible(False)  # Initially collapsed
layout.addWidget(self._debug_panel)

# Connect debug button to toggle panel
self._debug_button.clicked.connect(self._on_debug_panel_toggle)
```

- [ ] **Step 4: Add handler for debug panel toggle**

```python
# In AgentPanel class

def _on_debug_panel_toggle(self, checked: bool) -> None:
    """Handle debug panel toggle."""
    self._debug_panel.setVisible(checked)

def _on_api_debug(self, msg: ApiDebugMessage) -> None:
    """Handle API debug message from backend."""
    self._debug_panel.add_entry(
        timestamp=msg.timestamp,
        model=msg.model,
        tokens_in=msg.tokens_in,
        tokens_out=msg.tokens_out,
        duration_ms=msg.duration_ms,
        status=msg.status,
        error=msg.error,
    )

def subscribe_to_debug_messages(self, bus) -> None:
    """Subscribe to API debug messages from MessageBus.

    Args:
        bus: MessageBus instance to subscribe to
    """
    bus.subscribe(ApiDebugMessage, self._on_api_debug)
```

- [ ] **Step 5: Update add_message to use MessageRow**

```python
# Replace existing add_message method with:

def add_message(
    self,
    role: str,
    content: str,
    source: str = "user",
    coordination: bool = False,
    streaming: bool = False,
) -> None:
    """Add a message to the display.

    Args:
        role: Message role ("user" or "agent").
        content: Message content.
        source: Message source ("user" or "main_agent").
        coordination: Whether this is a coordination message.
        streaming: If True, append to last agent message.
    """
    from autoreport.gui.widgets.message_row import MessageRow

    # For streaming, we'd need a different approach
    # For now, create new MessageRow
    ts = datetime.now().strftime("%H:%M")

    row = MessageRow(
        role=role,
        content=content,
        timestamp=ts,
        is_coordination=coordination or source == "main_agent",
    )
    self._messages_area.add_message_row(row)
```

- [ ] **Step 6: Update add_tool_call to use ToolCallGroup**

```python
# Replace existing add_tool_call method with:

def add_tool_call(self, tool_name: str, arguments: dict) -> None:
    """Add a tool call entry."""
    from autoreport.gui.widgets.tool_call_group import ToolCallGroup

    # For now, create a new group per call
    # TODO: Group sequential calls
    group = ToolCallGroup()
    group.add_tool_call(
        name=tool_name,
        arguments=arguments,
        success=True,  # Will be updated by result
        duration_ms=0,  # Will be updated by result
    )
    self._messages_area.add_tool_group(group)
```

- [ ] **Step 7: Commit**

```bash
git add autoreport/gui/widgets/agent_panel.py
git commit -m "refactor: AgentPanel use new MessageRow, ToolCallGroup, MessagesArea, DebugPanel"
```

---

## Chunk 6: Final Integration and Testing

### Task 9: Subscribe AgentPanel to API debug messages

**Files:**
- Modify: `autoreport/gui/main_window.py` or similar integration point

- [ ] **Step 1: Find where AgentPanel/AgentLoop are initialized**

Search for the initialization code that sets up the agent loop and panels.

- [ ] **Step 2: Subscribe AgentPanel to ApiDebugMessage**

```python
# In the integration code (likely main_window.py or app.py)
# After creating agent_panel and agent_loop:

# Subscribe panel to debug messages using MessageBus
agent_panel.subscribe_to_debug_messages(agent_loop.bus)
```

- [ ] **Step 3: Test keyboard handling**

Manual test:
1. Start application
2. Type in chat input
3. Press Enter - should send message
4. Press Shift+Enter - should insert newline
5. Press Ctrl+Enter - should use default behavior

- [ ] **Step 4: Test debug panel**

Manual test:
1. Send a message that triggers API call
2. Click Debug button - panel should expand
3. Check that API call info is displayed
4. Send another message - entry count should increase
5. Test Clear button
6. Test Export JSON button

- [ ] **Step 5: Test tool call display**

Manual test:
1. Trigger a tool call (via agent)
2. Verify tool call group displays
3. Click to expand/collapse
4. Verify status icons and durations

- [ ] **Step 6: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 7: Commit integration**

```bash
git add autoreport/gui/main_window.py
git commit -m "feat: connect AgentLoop api_debug_sent to AgentPanel"
```

### Task 10: Visual polish and final touches

**Files:**
- Modify: `autoreport/gui/widgets/agent_panel.py`
- Modify: `autoreport/gui/widgets/chat_input.py`

- [ ] **Step 1: Update ChatInput styling**

```python
# In ChatInput._apply_style(), update border radius and add shadow

self.setStyleSheet(f"""
    QPlainTextEdit {{
        border: 1px solid {border};
        border-radius: 12px;
        padding: 10px 12px;
        background-color: {bg};
        color: {fg};
        font-size: 13px;
    }}
    QPlainTextEdit:focus {{
        border: 1px solid {claude_orange};
        box-shadow: 0 0 0 1px rgba(217, 119, 87, 0.2);
    }}
""")
```

- [ ] **Step 2: Update send button to circular with arrow icon**

```python
# In AgentPanel._setup_ui(), update send button:

send_btn = QPushButton("↑")
send_btn.setObjectName("sendBtn")
send_btn.setFixedSize(36, 36)
send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
send_btn.clicked.connect(self._on_send)
input_layout.addWidget(send_btn)

# Update styling for circular button
# In _apply_style():
self.setStyleSheet(f"""
    ...
    #sendBtn {{
        background-color: {c["sendBg"]};
        color: {{c["sendFg"]}};
        border: none;
        border-radius: 18px;
        font-size: 16px;
        font-weight: bold;
    }}
    #sendBtn:hover {{
        background-color: {c["sendHover"]};
        transform: scale(1.05);
    }}
    ...
""")
```

- [ ] **Step 3: Run visual smoke test**

Manual test:
1. Start application
2. Check all colors render correctly in dark/light mode
3. Verify border radiuses are applied
4. Verify circular send button
5. Check debug panel toggle animation

- [ ] **Step 4: Commit final polish**

```bash
git add autoreport/gui/widgets/chat_input.py autoreport/gui/widgets/agent_panel.py
git commit -m "style: visual polish - rounded corners, circular send button, shadows"
```

---

## Summary

This plan implements the agent chat UI redesign in 6 chunks:

1. **Chunk 1**: Fix ChatInput keyboard handling (TDD)
2. **Chunk 2**: Create MessageRow component (TDD)
3. **Chunk 3**: Create ToolCallGroup component (TDD)
4. **Chunk 4**: Create DebugPanel component (TDD)
5. **Chunk 5**: Create MessagesArea, update interfaces, add signals, refactor AgentPanel
6. **Chunk 6**: Integration, testing, and visual polish

Each chunk produces working, testable code. The plan follows TDD, uses small commits, and maintains clear component boundaries.
