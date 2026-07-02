"""Tests for ToolCallGroup widget."""

import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QSizePolicy, QWidget

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


def test_send_to_agent_result_can_expand_detail(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.resize(520, 180)
    widget.show()
    qtbot.waitExposed(widget)

    widget.add_tool_call(
        "send_to_agent",
        {"agent_type": "plotting"},
        success=None,
        summary="Delegated To Plotting",
    )
    widget.complete_tool_call(
        "send_to_agent",
        result={"status": "delegated"},
        summary="Delegated To Plotting",
        detail="Plotting will continue in background",
        expandable=True,
    )

    assert widget.is_expanded() is False
    widget._header_btn.click()
    assert widget.is_expanded() is True
    assert widget._detail_host.isVisible() is True
    assert widget._detail_label is not None
    assert "Plotting will continue in background" in widget._detail_label.text()


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


def test_manage_tasks_summary_uses_status_controls(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call(
        "manage_tasks",
        {},
        success=True,
        duration_ms=10,
        summary="<b>Task</b>\nTodo\n● running task\n☑ finished task\n☐ pending task",
    )

    controls = [
        label
        for label in widget.findChildren(QLabel)
        if label.objectName() == "taskStatusControl"
    ]
    texts = [
        label.text()
        for label in widget.findChildren(QLabel)
        if label.objectName() == "taskTextLabel"
    ]

    assert [control.text() for control in controls] == ["*", "✓", ""]
    assert texts == ["running task", "finished task", "pending task"]


def test_manage_tasks_task_title_is_bold(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)

    widget.add_tool_call(
        "manage_tasks",
        {},
        success=True,
        duration_ms=10,
        summary="<b>Task</b>\nTodo\n☐ pending task",
    )

    section_labels = [
        label
        for label in widget.findChildren(QLabel)
        if label.objectName() == "taskSectionLabel"
    ]

    assert section_labels[0].text() == "Task"
    assert section_labels[0].font().bold()
    assert not section_labels[1].font().bold()


def test_manage_tasks_running_control_draws_centered_vector_star(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.resize(520, 140)
    widget.show()
    qtbot.waitExposed(widget)

    widget.add_tool_call(
        "manage_tasks",
        {},
        success=True,
        duration_ms=10,
        summary="<b>Task</b>\nTodo\n* running task",
    )
    qtbot.wait(20)

    control = next(
        label
        for label in widget.findChildren(QLabel)
        if label.objectName() == "taskStatusControl"
    )

    segments = control.running_segments()  # type: ignore[attr-defined]
    center = QRectF(control.rect()).center()

    assert len(segments) == 4
    for segment in segments:
        midpoint_x = (segment.p1().x() + segment.p2().x()) / 2.0
        midpoint_y = (segment.p1().y() + segment.p2().y()) / 2.0
        assert abs(midpoint_x - center.x()) <= 0.01
        assert abs(midpoint_y - center.y()) <= 0.01


def test_manage_tasks_completed_control_draws_simple_checkmark_with_narrower_width(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.resize(520, 140)
    widget.show()
    qtbot.waitExposed(widget)

    widget.add_tool_call(
        "manage_tasks",
        {},
        success=True,
        duration_ms=10,
        summary="<b>Task</b>\nTodo\n☑ finished task",
    )
    qtbot.wait(20)

    control = next(
        label
        for label in widget.findChildren(QLabel)
        if label.objectName() == "taskStatusControl"
    )

    segments = control.completed_segments()  # type: ignore[attr-defined]

    assert control.width() == 16
    assert control.height() == 16
    assert len(segments) == 2
    assert segments[0].p2() == segments[1].p1()


def test_manage_tasks_status_control_uses_scaled_spacing_and_vertical_alignment(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.resize(520, 140)
    widget.show()
    qtbot.waitExposed(widget)

    widget.add_tool_call(
        "manage_tasks",
        {},
        success=True,
        duration_ms=10,
        summary="<b>Task</b>\nTodo\n☑ aligned task",
    )
    qtbot.wait(20)

    row = next(
        child
        for child in widget.findChildren(QLabel)
        if child.objectName() == "taskTextLabel"
    ).parentWidget()
    assert row is not None

    control = row.findChild(QLabel, "taskStatusControl")
    label = row.findChild(QLabel, "taskTextLabel")
    layout = row.layout()

    assert control is not None
    assert label is not None
    assert layout is not None
    assert layout.spacing() == 7
    assert control.geometry().center().y() == label.geometry().center().y()


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


def test_exec_out_preview_has_fade_mask_and_value_host(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.resize(420, 220)
    widget.show()
    qtbot.waitExposed(widget)

    widget.add_tool_call(
        "exec",
        {"command": "printf many", "command_description": "many lines"},
        success=True,
        duration_ms=80,
        result={"stdout": "one\ntwo\nthree\nfour\nfive", "stderr": ""},
    )

    assert widget.findChild(QWidget, "execOutFadeMask") is not None
    assert widget.findChild(QWidget, "execDetailValueHost") is not None


def test_exec_out_preview_is_top_aligned_and_wrapped(qtbot):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.resize(320, 220)
    widget.show()
    qtbot.waitExposed(widget)

    widget.add_tool_call(
        "exec",
        {"command": "printf many", "command_description": "many lines"},
        success=True,
        duration_ms=80,
        result={"stdout": "one\ntwo\nthree\nfour\nfive", "stderr": ""},
    )

    out_labels = [
        lab for lab in widget.findChildren(QLabel)
        if lab.objectName() == "execDetailText" and "one" in lab.text()
    ]
    assert out_labels
    assert out_labels[0].wordWrap() is True
    assert out_labels[0].alignment() & Qt.AlignmentFlag.AlignTop


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


# ---------------------------------------------------------------------------
# Task-board parsing edge cases.
#
# The status parser drives a user-visible timeline via regexes over agent
# output (HTML + CJK status glyphs). These table-driven tests pin every
# marker class — including the previously-untested `failed` markers — plus the
# HTML-stripping / entity-unescaping path and the dedup key used to merge
# in-place status updates.
# ---------------------------------------------------------------------------

_STATUS_CASES = [
    # (line, expected_status) — every marker class, incl. failed (⚠ ✗ ✕).
    ("☑ done", "completed"),
    ("✓ done", "completed"),
    ("✔ done", "completed"),
    ("✅ done", "completed"),
    ("● working", "running"),
    ("⏳ working", "running"),
    ("* working", "running"),
    ("⚠ boom", "failed"),
    ("✗ boom", "failed"),
    ("✕ boom", "failed"),
    ("☐ later", "pending"),
    ("○ later", "pending"),
    ("plain text with no marker", "pending"),  # default fallback
    ("  ☑ leading whitespace", "completed"),     # leading ws tolerated
]


@pytest.mark.parametrize("line, expected", _STATUS_CASES)
def test_task_status_from_line_all_markers(qtbot, line, expected):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    assert widget._task_status_from_line(line) == expected


@pytest.mark.parametrize(
    "status, control",
    [
        ("running", "*"),
        ("completed", "✓"),
        ("failed", "!"),  # the "!" control for failed was previously untested
        ("pending", ""),
        ("unknown", ""),
    ],
)
def test_task_control_text_mapping(qtbot, status, control):
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    assert widget._task_control_text(status) == control


def test_plain_summary_text_strips_html_and_unescapes_entities():
    # <br> variants collapse to newlines, tags are removed, entities decoded.
    assert ToolCallGroup._plain_summary_text("a<br/>b<br>c<br />d") == "a\nb\nc\nd"
    assert ToolCallGroup._plain_summary_text("<b>bold</b> &amp; <i>it</i>") == "bold & it"
    assert ToolCallGroup._plain_summary_text("3 &lt; 4 &gt; 2") == "3 < 4 > 2"
    assert ToolCallGroup._plain_summary_text(None) == ""
    assert ToolCallGroup._plain_summary_text("win\r\nline") == "win\nline"


def test_task_content_key_strips_status_prefix_and_ignores_sections():
    # Same task text with DIFFERENT status markers must yield the SAME key
    # (so an in-place status update is recognized as the same task).
    running = ToolCallGroup._task_content_key_from_text("Task\nTodo\n● analyze data")
    done = ToolCallGroup._task_content_key_from_text("Task\nTodo\n☑ analyze data")
    failed = ToolCallGroup._task_content_key_from_text("Task\nTodo\n⚠ analyze data")
    assert running == done == failed == "analyze data"

    # Section labels (Task/Todo/Wait) and divider lines (—, -) are dropped.
    assert ToolCallGroup._task_content_key_from_text("Task\n—\n☐ x") == "x"

    # Duplicate task text is de-duplicated within one summary.
    assert ToolCallGroup._task_content_key_from_text("● y\n☑ y") == "y"


def test_task_content_key_distinguishes_different_tasks():
    a = ToolCallGroup._task_content_key_from_text("● analyze data")
    b = ToolCallGroup._task_content_key_from_text("● plot graph")
    assert a != b
    assert a == "analyze data"
    assert b == "plot graph"


def _manage_tasks_group(qtbot, summary: str) -> ToolCallGroup:
    widget = ToolCallGroup()
    qtbot.addWidget(widget)
    widget.add_tool_call("manage_tasks", {}, success=True, duration_ms=10, summary=summary)
    return widget


def test_has_status_change_detects_status_flip(qtbot):
    """Two manage_tasks groups with the same task but different status differ."""
    running = _manage_tasks_group(qtbot, "Task\n● analyze data")
    done = _manage_tasks_group(qtbot, "Task\n☑ analyze data")
    # Same content key → comparable; visual summary differs → change detected.
    assert running.task_content_key() == done.task_content_key()
    assert running.has_status_change_from(done) is True
    assert done.has_status_change_from(running) is True


def test_has_status_change_false_for_different_tasks(qtbot):
    a = _manage_tasks_group(qtbot, "Task\n● analyze data")
    b = _manage_tasks_group(qtbot, "Task\n● plot graph")
    # Different content keys → not comparable → no mergeable change.
    assert a.task_content_key() != b.task_content_key()
    assert a.has_status_change_from(b) is False


def test_has_status_change_false_when_identical(qtbot):
    a = _manage_tasks_group(qtbot, "Task\n● analyze data")
    b = _manage_tasks_group(qtbot, "Task\n● analyze data")
    assert a.has_status_change_from(b) is False


def test_replace_with_group_swaps_calls_and_summary(qtbot):
    target = _manage_tasks_group(qtbot, "Task\n● analyze data")
    new_state = _manage_tasks_group(qtbot, "Task\n☑ analyze data")

    target.replace_with_group(new_state)

    # The target now reflects the replacement's calls/summary.
    assert target.get_summary_text() == new_state.get_summary_text()
    assert "☑ analyze data" in target.get_summary_text()
    # And it is decoupled from the source (independent ToolCall instances).
    assert target._calls is not new_state._calls
