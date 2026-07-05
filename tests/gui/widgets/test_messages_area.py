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


def test_messages_area_uses_half_line_item_spacing(qtbot):
    widget = MessagesArea()
    qtbot.addWidget(widget)
    assert widget._layout.spacing() == 0


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


def test_only_latest_user_message_is_editable(qtbot):
    widget = MessagesArea()
    qtbot.addWidget(widget)

    first = widget.add_message_row(role="user", content="first", timestamp="12:00")
    second = widget.add_message_row(role="user", content="second", timestamp="12:01")

    assert first._editable is False
    assert second._editable is True


def test_agent_message_is_marked_complete_for_hover_actions(qtbot):
    widget = MessagesArea()
    qtbot.addWidget(widget)

    row = widget.add_message_row(role="agent", content="Agent msg", timestamp="12:00")
    assert row._complete is True


def test_follow_streaming_respects_user_scroll_state(qtbot):
    widget = MessagesArea()
    qtbot.addWidget(widget)
    widget.resize(320, 120)
    widget.show()
    qtbot.waitExposed(widget)

    for i in range(30):
        widget.add_message_row(role="agent", content=f"line {i}", timestamp="12:00")
    qtbot.wait(20)

    sb = widget.verticalScrollBar()
    sb.setValue(sb.maximum())
    widget.follow_streaming_if_enabled()
    qtbot.wait(20)
    assert sb.value() == sb.maximum()

    # User scrolls up: auto-follow should stop.
    sb.setValue(max(0, sb.maximum() - 50))
    widget.follow_streaming_if_enabled()
    qtbot.wait(20)
    assert sb.value() < sb.maximum()


def test_new_messages_keep_following_when_user_has_not_scrolled(qtbot):
    widget = MessagesArea()
    qtbot.addWidget(widget)
    widget.resize(320, 120)
    widget.show()
    qtbot.waitExposed(widget)

    for i in range(30):
        widget.add_message_row(role="agent", content=f"line {i}", timestamp="12:00")
    qtbot.wait(220)

    sb = widget.verticalScrollBar()
    assert sb.value() == sb.maximum()
    assert widget.auto_scroll_enabled() is True

    widget.add_message_row(role="user", content="latest", timestamp="12:01")
    qtbot.wait(220)

    assert sb.value() == sb.maximum()
    assert widget.auto_scroll_enabled() is True


def test_new_messages_do_not_move_view_after_user_scrolls_up(qtbot):
    widget = MessagesArea()
    qtbot.addWidget(widget)
    widget.resize(320, 120)
    widget.show()
    qtbot.waitExposed(widget)

    for i in range(30):
        widget.add_message_row(role="agent", content=f"line {i}", timestamp="12:00")
    qtbot.wait(220)

    sb = widget.verticalScrollBar()
    sb.setValue(max(0, sb.maximum() - 50))
    qtbot.wait(20)
    frozen_value = sb.value()

    widget.add_message_row(role="agent", content="later", timestamp="12:01")
    qtbot.wait(220)

    assert sb.value() == frozen_value
    assert widget.auto_scroll_enabled() is False


def test_timeline_chain_breaks_on_user_bubble_between_chainable_items(qtbot):
    widget = MessagesArea()
    qtbot.addWidget(widget)

    first_agent = widget.add_message_row(role="agent", content="a1", timestamp="12:00")
    tool = widget.add_tool_group()
    # Simulate other-agent message rendered as user bubble in current panel.
    widget.add_message_row(
        role="user",
        content="interruption",
        timestamp="12:01",
        render_as_user_bubble=True,
    )
    second_agent = widget.add_message_row(role="agent", content="a2", timestamp="12:02")

    assert first_agent._agent_chain_next is True
    assert tool._timeline_prev is True
    assert tool._timeline_next is False
    assert second_agent._agent_chain_prev is False
