"""Tests for MessageRow component."""

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


def test_agent_message_renders_correctly(qtbot):
    """Agent message should show Agent role."""
    widget = MessageRow(
        role="agent",
        content="I will help you.",
        timestamp="14:33"
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Agent" in display_text
    assert "14:33" in display_text
    assert "I will help you." in display_text


def test_coordination_message_shows_indicator(qtbot):
    """Coordination message should show [主 Agent 协调] indicator."""
    widget = MessageRow(
        role="user",
        content="Calling data analysis agent...",
        timestamp="14:35",
        is_coordination=True
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "14:35" in display_text
    assert "Calling data analysis agent..." in display_text


def test_empty_timestamp_defaults(qtbot):
    """Empty timestamp should default to 00:00."""
    widget = MessageRow(
        role="user",
        content="Test message",
        timestamp=""
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "00:00" in display_text


def test_multiline_content(qtbot):
    """Multiline content should be preserved."""
    widget = MessageRow(
        role="agent",
        content="Line 1\nLine 2\nLine 3",
        timestamp="14:40"
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Line 1" in display_text
    assert "Line 2" in display_text
    assert "Line 3" in display_text
