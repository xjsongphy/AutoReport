"""Tests for MessageRow component — Cline-style flat timeline."""

import pytest
from PyQt6.QtWidgets import QApplication
from autoreport.gui.widgets.message_row import MessageRow


def test_user_message_renders_badge_style(qtbot):
    """User message uses badge-background bubble, no timestamp header."""
    widget = MessageRow(
        role="user",
        content="Hello, agent!",
        timestamp="14:32",
        is_coordination=False
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "You" in display_text
    assert "Hello, agent!" in display_text


def test_agent_message_renders_inline(qtbot):
    """Agent message is inline text with no background."""
    widget = MessageRow(
        role="agent",
        content="I will help you.",
        timestamp="14:33"
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Agent" in display_text
    assert "I will help you." in display_text


def test_coordination_message_shows_prefix(qtbot):
    """Coordination message shows mute source label."""
    widget = MessageRow(
        role="user",
        content="Calling data analysis agent...",
        timestamp="14:35",
        is_coordination=True
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Calling data analysis agent..." in display_text


def test_empty_timestamp_is_handled(qtbot):
    """Empty timestamp should not cause errors."""
    widget = MessageRow(
        role="user",
        content="Test message",
        timestamp=""
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Test message" in display_text


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
