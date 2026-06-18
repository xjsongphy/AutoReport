"""Tests for ToolCallGroup widget."""

from PyQt6.QtWidgets import QPushButton, QSizePolicy

from autoreport.gui.widgets.tool_call_group import ToolCallGroup


def test_collapsed_shows_summary(qtbot):
    """Collapsed state should show summary of tool calls."""
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call("bash", {"command": "echo ok", "command_description": "show output"}, success=True, duration_ms=1200)
    widget.add_tool_call("read", {"path": "data.csv"}, success=True, duration_ms=100)

    # Initially collapsed
    assert not widget.is_expanded()
    summary = widget.get_summary_text()
    # Copilot-style: shows tool names grouped (display names)
    assert "Bash" in summary
    assert "Read" in summary


def test_no_expand_behavior(qtbot):
    """Tool rows are summary-only and stay non-expandable."""
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call("test_tool", {}, success=True, duration_ms=100)
    assert not widget.is_expanded()
    widget._header_btn.click()
    assert not widget.is_expanded()


def test_pending_call_can_be_completed(qtbot):
    """Pending tool calls should update in place when a result arrives."""
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call(
        "send_to_agent",
        {"agent_type": "theory"},
        success=None,
        summary="Send To Theory",
    )
    widget.complete_tool_call(
        "send_to_agent",
        result={"status": "success"},
        summary="Theory replied: done",
    )

    assert "Theory replied: done" in widget.get_summary_text()


def test_multiple_tool_calls_render_on_separate_lines(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call("read", {"path": "a.txt"}, success=True, duration_ms=10)
    widget.add_tool_call("read", {"path": "b.txt"}, success=True, duration_ms=10)

    summary = widget.get_summary_text()
    assert "Read" in summary
    assert "a.txt" in summary
    assert "b.txt" in summary
    assert "<br/>" in summary


def test_exec_detail_text_shrinks_in_narrow_panel(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.resize(260, 180)
    widget.show()
    qtbot.waitExposed(widget)

    widget.add_tool_call(
        "exec",
        {
            "command": "python -c \"print('x'*500)\" --very-long-arg --very-long-arg --very-long-arg",
            "command_description": "long command",
        },
        success=True,
        duration_ms=80,
    )
    qtbot.wait(20)

    labels = widget.findChildren(type(widget._header_text))
    exec_labels = [lab for lab in labels if lab.objectName() == "execDetailText"]
    assert exec_labels
    for lab in exec_labels:
        assert lab.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
        assert lab.minimumWidth() == 0


def test_exec_out_preview_is_limited_to_three_lines(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.add_tool_call(
        "exec",
        {"command": "printf many", "command_description": "many lines"},
        success=True,
        duration_ms=80,
        result={"stdout": "one\ntwo\nthree\nfour\nfive", "stderr": ""},
    )

    labels = widget.findChildren(type(widget._header_text))
    out_labels = [lab for lab in labels if lab.objectName() == "execDetailText" and "one" in lab.text()]
    assert out_labels
    assert out_labels[0].text() == "one\ntwo\nthree"


def test_exec_copy_button_reserves_width_by_default(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.add_tool_call(
        "exec",
        {"command": "echo ok", "command_description": "show output"},
        success=True,
        duration_ms=10,
    )

    copy_buttons = [btn for btn in widget.findChildren(QPushButton) if btn.objectName() == "userCopyBtn"]
    assert copy_buttons
    for btn in copy_buttons:
        assert not btn.isEnabled()
        assert btn.minimumWidth() == 30
        assert btn.maximumWidth() == 30
