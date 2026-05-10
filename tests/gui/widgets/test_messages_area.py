"""Tests for MessagesArea widget."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from autoreport.gui.widgets.messages_area import MessagesArea
from autoreport.gui.widgets.message_row import MessageRow
from autoreport.gui.widgets.tool_call_group import ToolCallGroup


def test_messages_area_initial_state(qtbot):
    """MessagesArea should start empty and scrollable."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    assert widget.message_count() == 0
    assert widget.is_scrollable()


def test_add_message_row(qtbot):
    """Adding a MessageRow should increase message count."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    # Add a user message
    widget.add_message_row(
        role="user",
        content="Hello, agent!",
        timestamp="14:32"
    )

    assert widget.message_count() == 1

    # Add an agent message
    widget.add_message_row(
        role="agent",
        content="I can help you with that.",
        timestamp="14:33"
    )

    assert widget.message_count() == 2


def test_add_collapsed_message_row(qtbot):
    widget = MessagesArea()
    qtbot.addWidget(widget)

    widget.add_message_row(
        role="agent",
        content="detail line 1\ndetail line 2",
        summary="Collapsed summary",
        detail="detail line 1\ndetail line 2",
    )

    rows = widget.get_message_rows()
    assert len(rows) == 1
    assert not rows[0].is_expanded()


def test_add_tool_group(qtbot):
    """Adding a ToolCallGroup should increase message count."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    # Add a tool group
    widget.add_tool_group()
    # Get the last added widget
    tool_group = widget.findChild(ToolCallGroup)
    assert tool_group is not None

    # Add some tool calls to the group
    tool_group.add_tool_call(
        name="read_file",
        arguments={"path": "test.py"},
        success=True,
        duration_ms=150,
        result="file content"
    )

    assert widget.message_count() == 1


def test_auto_scroll_enabled_by_default(qtbot):
    """Auto-scroll should be enabled by default."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    assert widget.auto_scroll_enabled()


def test_scroll_state_can_be_manually_toggled(qtbot):
    """Auto-scroll state can be manually toggled for testing."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    # Initially enabled
    assert widget.auto_scroll_enabled()

    # Manually disable
    widget._auto_scroll_enabled = False
    assert not widget.auto_scroll_enabled()

    # Manually re-enable
    widget._auto_scroll_enabled = True
    assert widget.auto_scroll_enabled()


def test_scroll_to_bottom_method(qtbot):
    """scroll_to_bottom method should work without errors."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    # Add some messages
    for i in range(5):
        widget.add_message_row(
            role="agent",
            content=f"Message {i}",
            timestamp=f"12:{i:02d}"
        )

    # Should not raise any errors
    widget.scroll_to_bottom()


def test_clear_messages(qtbot):
    """Clear should remove all messages."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    # Add some messages
    for i in range(5):
        widget.add_message_row(
            role="user",
            content=f"Message {i}",
            timestamp="12:00"
        )

    assert widget.message_count() == 5

    # Clear all
    widget.clear()

    assert widget.message_count() == 0


def test_get_message_rows(qtbot):
    """Should return list of all MessageRow widgets."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    # Add mixed messages
    widget.add_message_row(role="user", content="User msg", timestamp="12:00")
    widget.add_tool_group()  # This is not a MessageRow
    widget.add_message_row(role="agent", content="Agent msg", timestamp="12:01")

    rows = widget.get_message_rows()
    assert len(rows) == 2  # Only MessageRow instances


def test_get_tool_groups(qtbot):
    """Should return list of all ToolCallGroup widgets."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    # Add mixed content
    widget.add_message_row(role="user", content="User msg", timestamp="12:00")
    widget.add_tool_group()
    widget.add_tool_group()
    widget.add_message_row(role="agent", content="Agent msg", timestamp="12:01")

    groups = widget.get_tool_groups()
    assert len(groups) == 2  # Only ToolCallGroup instances


def test_new_messages_added_when_auto_scroll_enabled(qtbot):
    """Messages should be added regardless of auto-scroll state."""
    widget = MessagesArea()
    qtbot.addWidget(widget)

    # Auto-scroll is enabled by default
    assert widget.auto_scroll_enabled()

    # Add messages
    widget.add_message_row(role="user", content="Msg 1", timestamp="12:00")
    assert widget.message_count() == 1

    # Disable auto-scroll
    widget._auto_scroll_enabled = False
    assert not widget.auto_scroll_enabled()

    # Messages should still be added
    widget.add_message_row(role="agent", content="Msg 2", timestamp="12:01")
    widget.add_message_row(role="user", content="Msg 3", timestamp="12:02")

    assert widget.message_count() == 3
    assert not widget.auto_scroll_enabled()

    # Re-enable auto-scroll
    widget._auto_scroll_enabled = True
    assert widget.auto_scroll_enabled()

    # Messages should still be added
    widget.add_message_row(role="agent", content="Msg 4", timestamp="12:03")
    assert widget.message_count() == 4
