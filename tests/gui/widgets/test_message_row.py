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


def test_user_message_can_render_collapsed_summary(qtbot):
    widget = MessageRow(
        role="user",
        content="line 1\nline 2",
        summary="Message From Main: line 1",
        detail="line 1\nline 2",
    )
    qtbot.addWidget(widget)

    assert not widget.is_expanded()
    widget._summary_btn.click()
    assert widget.is_expanded()


def test_agent_message_can_render_collapsed_summary(qtbot):
    widget = MessageRow(
        role="agent",
        content="issue detail",
        summary="Theory reported quality: issue detail",
        detail="issue detail\nmore",
    )
    qtbot.addWidget(widget)

    assert not widget.is_expanded()
    widget._summary_btn.click()
    assert widget.is_expanded()


def test_user_bubble_width_stable_when_actions_toggle(qtbot):
    widget = MessageRow(role="user", content="Width stability check")
    qtbot.addWidget(widget)
    widget.resize(900, 200)
    widget.mark_complete()
    widget.show()
    qtbot.waitExposed(widget)

    before = widget._user_bubble_container.sizeHint().width()
    widget._set_user_actions_visible(True)
    qtbot.wait(10)
    after_show = widget._user_bubble_container.sizeHint().width()
    widget._set_user_actions_visible(False)
    qtbot.wait(10)
    after_hide = widget._user_bubble_container.sizeHint().width()

    assert before == after_show == after_hide
