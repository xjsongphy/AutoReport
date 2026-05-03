"""Tests for ToolCallGroup widget."""

from autoreport.gui.widgets.tool_call_group import ToolCallGroup


def test_collapsed_shows_summary(qtbot):
    """Collapsed state should show summary of tool calls."""
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call("python_exec", {"file": "analysis.py"}, success=True, duration_ms=1200)
    widget.add_tool_call("read_file", {"path": "data.csv"}, success=True, duration_ms=100)

    # Initially collapsed
    assert not widget.is_expanded()
    summary = widget.get_summary_text()
    # Copilot-style: shows tool names grouped
    assert "python_exec" in summary
    assert "read_file" in summary
    assert "1.3s" in summary


def test_expand_collapse_works(qtbot):
    """Toggle button should expand/collapse details."""
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call("test_tool", {}, success=True, duration_ms=100)

    # Initially collapsed
    assert not widget.is_expanded()

    # Click to expand
    widget._header_btn.click()
    assert widget.is_expanded()

    # Click to collapse
    widget._header_btn.click()
    assert not widget.is_expanded()
