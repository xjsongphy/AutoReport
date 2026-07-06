"""Tests for refactored AgentPanel with MessagesArea and DebugPanel."""

from pathlib import Path
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLabel

from autoreport.gui.widgets.agent_panel import AgentPanel
from autoreport.gui.widgets.file_search_popup import FileMatch


@pytest.fixture
def agent_panel(qtbot):
    """Create an AgentPanel for testing."""
    panel = AgentPanel(
        panel_id="test_panel",
        title="Test Agent",
        workspace=Path("/tmp/test_workspace")
    )
    qtbot.addWidget(panel)
    return panel


def test_agent_panel_has_messages_area(agent_panel):
    """AgentPanel should have a MessagesArea widget."""
    from autoreport.gui.widgets.messages_area import MessagesArea

    messages_area = agent_panel._messages_area
    assert isinstance(messages_area, MessagesArea)
    assert messages_area.message_count() == 0


def test_agent_panel_has_debug_panel(agent_panel):
    """AgentPanel should have a DebugPanel widget."""
    from autoreport.gui.widgets.debug_panel import DebugPanel

    debug_panel = agent_panel._debug_panel
    assert isinstance(debug_panel, DebugPanel)
    assert debug_panel.isVisible() is False  # Hidden by default


def test_add_message_uses_message_row(agent_panel):
    """add_message should create MessageRow widgets."""
    agent_panel.add_message(
        role="user",
        content="Hello, agent!",
    )

    assert agent_panel._messages_area.message_count() == 1

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert rows[0]._role == "user"
    assert "Hello, agent!" in rows[0]._content


def test_add_message_with_coordination(agent_panel):
    """add_message with coordination should set is_coordination flag."""
    agent_panel.add_message(
        role="user",
        content="Calling data analysis agent...",
        source="main_agent",
        coordination=True
    )

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert rows[0]._is_coordination is True


def test_add_message_with_summary(agent_panel):
    agent_panel.add_message(
        role="agent",
        content="detail line 1\ndetail line 2",
        display_mode="bubble",
        bubble_title="Collapsed summary",
        bubble_align="left",
        bubble_on_timeline=True,
    )

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert not rows[0].is_expanded()


def test_set_queue_preview(agent_panel):
    agent_panel.set_queue_preview(["First queued", "Second queued"])
    assert not agent_panel._queue_preview.isHidden()
    assert "First queued" in agent_panel._queue_items.text()


def test_set_queue_preview_empty_hides(agent_panel):
    agent_panel.set_queue_preview(["Queued"])
    agent_panel.set_queue_preview([])
    assert not agent_panel._queue_preview.isVisible()


def test_file_context_lives_in_dock_bar_and_toggles(agent_panel):
    agent_panel.set_opened_file("sections/intro.tex")

    assert not agent_panel._context_separator.isHidden()
    assert not agent_panel._context_attachment_btn.isHidden()
    assert agent_panel._context_attachment_btn.text() == "intro.tex"
    assert agent_panel._context_enabled is True

    file_icon_key = agent_panel._context_attachment_btn.icon().cacheKey()
    agent_panel._context_attachment_btn.click()

    assert agent_panel._context_enabled is False
    assert agent_panel._context_attachment_btn.icon().cacheKey() != file_icon_key


def test_context_attachment_hidden_without_editor_context(agent_panel):
    assert agent_panel._context_separator.isHidden()
    assert agent_panel._context_attachment_btn.isHidden()

    agent_panel.set_opened_file("sections/intro.tex")
    agent_panel.clear_file_context()

    assert agent_panel._context_separator.isHidden()
    assert agent_panel._context_attachment_btn.isHidden()


def test_selection_context_label_uses_line_count(agent_panel):
    agent_panel.set_preview_context("sections/intro.tex", "a\nb", 3, 4)

    assert agent_panel._context_attachment_btn.text() == "2 lines selected"
    assert agent_panel._context_attachment_btn.toolTip() == ""
    assert agent_panel._context_attachment_btn._compact_tooltip_filter._text == "sections/intro.tex"


def test_context_attachment_uses_compact_tooltip(agent_panel):
    agent_panel.set_opened_file("Plots/Fig/fig6.pdf")

    btn = agent_panel._context_attachment_btn

    assert btn.toolTip() == ""
    assert hasattr(btn, "_compact_tooltip_filter")
    assert btn._compact_tooltip_filter._text == "Plots/Fig/fig6.pdf"


def test_composer_side_gap_matches_bottom_mask_height(agent_panel, qtbot):
    agent_panel.resize(420, 600)
    agent_panel.show()
    qtbot.wait(10)
    agent_panel._sync_composer_gap()

    side_gap = agent_panel._input_container.mapTo(agent_panel, agent_panel._input_container.rect().topLeft()).x()

    assert side_gap >= agent_panel._composer_horizontal_margin
    assert agent_panel._composer_bottom_gap.height() == side_gap


def test_set_agent_type_uses_badged_title(agent_panel):
    agent_panel.set_agent_type("theory")
    # Title shows agent name, icon is shown separately in _icon_label
    assert agent_panel._title_label.text() == "Theory Agent"
    assert agent_panel._icon_label.pixmap() is not None  # Icon is set


def test_add_tool_call_creates_group(agent_panel):
    """add_tool_call should create a ToolCallGroup."""
    agent_panel.add_tool_call("read", {"path": "test.py"})

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 1
    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 0


def test_empty_thinking_row_is_removed_when_finished(agent_panel):
    agent_panel.start_thinking()

    agent_panel.finish_thinking()

    assert agent_panel._messages_area.message_count() == 0
    assert agent_panel._thinking_row is None


def test_tool_call_after_empty_thinking_does_not_leave_phantom_thought(agent_panel):
    agent_panel.start_thinking()

    agent_panel.add_tool_call("read", {"path": "Processed"})

    assert agent_panel._messages_area.message_count() == 1
    assert agent_panel._messages_area.get_message_rows() == []
    assert len(agent_panel._messages_area.get_tool_groups()) == 1


def test_add_tool_result_adds_to_group(agent_panel):
    """add_tool_result should add to the current tool group."""
    # First add a tool call
    agent_panel.add_tool_call("read", {"path": "test.py"})

    # Then add the result
    agent_panel.add_tool_result("read", "file content", error=None)

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 1

    # Check that the tool group has the tool call
    # The group should have 1 tool call — summary uses display names
    summary = groups[0].get_summary_text()
    assert "Read" in summary


def test_add_tool_result_updates_pending_group_item(agent_panel):
    """Tool result should complete an existing pending tool call."""
    agent_panel.add_tool_call(
        "send_to_agent",
        {"agent_type": "theory"},
        summary="Send To Theory",
        expandable=False,
    )
    agent_panel.add_tool_result(
        "send_to_agent",
        {"status": "success"},
        summary="Theory replied: first line",
        detail="first line\nsecond line",
        expandable=True,
    )

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 1
    assert "Theory replied: first line" in groups[0].get_summary_text()


def test_send_to_agent_result_stays_in_tool_group_without_agent_bubble(agent_panel):
    before_rows = len(agent_panel._messages_area.get_message_rows())

    agent_panel.add_tool_call(
        "send_to_agent",
        {"agent_type": "plotting"},
        summary="Main to Sub",
        expandable=False,
    )
    agent_panel.add_tool_result(
        "send_to_agent",
        {"status": "delegated", "agent_type": "plotting", "message": "delegated"},
        summary="Main to Sub",
        detail="delegated",
        expandable=True,
    )

    after_rows = len(agent_panel._messages_area.get_message_rows())
    groups = agent_panel._messages_area.get_tool_groups()

    assert before_rows == after_rows
    assert len(groups) == 1
    assert groups[0].get_summary_text() == "Main to Sub"


def test_adjacent_manage_tasks_status_change_updates_in_place(agent_panel):
    created_summary = "<b>Task</b>\nTodo\n☐ DATA_ANALYSIS: Process all measurements\n\nWait\n☐ DATA_ANALYSIS: Process all measurements"
    started_summary = "<b>Task</b>\nTodo\n● DATA_ANALYSIS: Process all measurements\n\nWait\n● DATA_ANALYSIS: Process all measurements"

    agent_panel.add_tool_call(
        "manage_tasks",
        {
            "action": "add",
            "description": "Process calibration, C-V curves, Phi-V, 2ω, and noise data",
            "brief": "DATA_ANALYSIS: Process all measurements",
        },
    )
    agent_panel.add_tool_result("manage_tasks", created_summary, summary=created_summary)
    first_group = agent_panel._messages_area.get_tool_groups()[0]

    agent_panel.add_tool_call(
        "manage_tasks",
        {
            "action": "start",
            "task_id": "tk007",
            "brief": "DATA_ANALYSIS: Process all measurements",
        },
    )
    agent_panel.add_tool_result("manage_tasks", started_summary, summary=started_summary)

    groups = agent_panel._messages_area.get_tool_groups()
    assert groups == [first_group]
    assert "● DATA_ANALYSIS: Process all measurements" in groups[0].get_summary_text()
    assert "☐ DATA_ANALYSIS: Process all measurements" not in groups[0].get_summary_text()


def test_manage_tasks_status_change_does_not_merge_across_other_events(agent_panel):
    task_summary = "<b>Task</b>\nTodo\n☐ DATA_ANALYSIS: Process all measurements"

    agent_panel.add_tool_call(
        "manage_tasks",
        {"action": "add", "brief": "DATA_ANALYSIS: Process all measurements"},
    )
    agent_panel.add_tool_result("manage_tasks", task_summary, summary=task_summary)
    agent_panel.add_tool_call("read", {"path": "."})
    agent_panel.add_tool_result("read", "content")
    agent_panel.add_tool_call(
        "manage_tasks",
        {
            "action": "start",
            "task_id": "tk007",
            "brief": "DATA_ANALYSIS: Process all measurements",
        },
    )
    agent_panel.add_tool_result("manage_tasks", task_summary, summary=task_summary)

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 3
    assert [group.tool_names() for group in groups] == [["manage_tasks"], ["read"], ["manage_tasks"]]


def test_manage_tasks_different_task_content_does_not_merge(agent_panel):
    first_summary = "<b>Task</b>\nTodo\n☐ DATA_ANALYSIS: Process all measurements"
    second_summary = "<b>Task</b>\nTodo\n☐ PLOTTING: Generate all figures"

    agent_panel.add_tool_call(
        "manage_tasks",
        {"action": "add", "brief": "DATA_ANALYSIS: Process all measurements"},
    )
    agent_panel.add_tool_result("manage_tasks", first_summary, summary=first_summary)
    agent_panel.add_tool_call(
        "manage_tasks",
        {"action": "add", "brief": "PLOTTING: Generate all figures"},
    )
    agent_panel.add_tool_result("manage_tasks", second_summary, summary=second_summary)

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 2
    assert "DATA_ANALYSIS: Process all measurements" in groups[0].get_summary_text()
    assert "PLOTTING: Generate all figures" in groups[1].get_summary_text()


def test_batch_tool_calls_render_as_separate_timeline_items(agent_panel):
    agent_panel.add_tool_call("write_file", {"path": "a.txt"})
    agent_panel.add_tool_call("write_file", {"path": "b.txt"})

    groups = agent_panel._messages_area.get_tool_groups()

    assert len(groups) == 2
    assert "a.txt" in groups[0].get_summary_text()
    assert "b.txt" in groups[1].get_summary_text()


def test_consecutive_same_task_manage_tasks_reuses_dot_in_real_time(agent_panel):
    """A same-task manage_tasks call following its own dot reuses that dot
    immediately (no second dot flicker), and the timeline stays as one group."""
    created_summary = "<b>Task</b>\nTodo\n☐ DATA_ANALYSIS: Process all measurements"
    started_summary = "<b>Task</b>\nTodo\n● DATA_ANALYSIS: Process all measurements"

    agent_panel.add_tool_call(
        "manage_tasks",
        {"action": "add", "brief": "DATA_ANALYSIS: Process all measurements"},
    )
    agent_panel.add_tool_result("manage_tasks", created_summary, summary=created_summary)
    first_group = agent_panel._messages_area.get_tool_groups()[0]

    # Second call targets the same task → must reuse the existing dot in place.
    agent_panel.add_tool_call(
        "manage_tasks",
        {"action": "start", "brief": "DATA_ANALYSIS: Process all measurements"},
    )

    groups = agent_panel._messages_area.get_tool_groups()
    assert groups == [first_group]
    # The reused dot is running again (success is None) while awaiting the result.
    assert first_group._calls[-1].success is None

    agent_panel.add_tool_result("manage_tasks", started_summary, summary=started_summary)
    groups = agent_panel._messages_area.get_tool_groups()
    assert groups == [first_group]
    assert "● DATA_ANALYSIS: Process all measurements" in first_group.get_summary_text()



def test_tool_call_before_agent_text_keeps_event_order(agent_panel):
    agent_panel.add_tool_call("read", {"path": "."})
    agent_panel.add_message(role="agent", content="Hello", streaming=True)

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert rows[0]._role == "agent"
    assert rows[0]._content == "Hello"
    assert agent_panel._messages_area.message_count() == 2


def test_agent_text_tool_text_keeps_separate_timeline_items(agent_panel):
    agent_panel.add_message(role="agent", content="First", streaming=True)
    agent_panel.add_tool_call("read", {"path": "."})
    agent_panel.add_message(role="agent", content="Second", streaming=True)

    rows = agent_panel._messages_area.get_message_rows()
    groups = agent_panel._messages_area.get_tool_groups()

    assert [row._content for row in rows] == ["First", "Second"]
    assert len(groups) == 1
    assert agent_panel._messages_area.message_count() == 3


def test_thinking_row_finishes_with_elapsed_summary(agent_panel):
    agent_panel.start_thinking()
    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert rows[0]._display_mode == "thought"
    assert rows[0]._bubble_title.startswith("Thinking for ")
    assert rows[0]._summary_text_label is not None

    agent_panel.append_thinking("raw **markdown** thought")
    assert rows[0]._bubble_text == "raw **markdown** thought"
    assert rows[0]._detail_label is not None

    agent_panel.finish_thinking()
    assert rows[0]._bubble_title.startswith("Thought for ")
    assert rows[0]._complete is True


def test_thinking_timer_updates_existing_row_in_place(agent_panel):
    agent_panel.start_thinking()
    row = agent_panel._messages_area.get_message_rows()[0]

    agent_panel._thinking_started_at -= 2
    agent_panel._update_thinking_timer()

    rows = agent_panel._messages_area.get_message_rows()
    assert rows == [row]
    assert row._bubble_title.startswith("Thinking for ")
    assert row._bubble_title != "Thinking for 1s"


def test_thinking_detail_updates_existing_detail_label(agent_panel):
    agent_panel.start_thinking()
    row = agent_panel._messages_area.get_message_rows()[0]
    agent_panel.append_thinking("first\nsecond\nthird\nfourth\nfifth\nsixth")
    row._summary_header.clicked.emit()
    assert row.is_expanded()
    assert row._detail_label is not None
    assert "first" in row._detail_label.text()

    agent_panel.append_thinking("first\nsecond\nthird\nfourth\nfifth\nsixth\nseventh")
    rows = agent_panel._messages_area.get_message_rows()
    assert rows == [row]
    assert row.is_expanded()
    assert row._detail_label is not None
    assert "seventh" in row._detail_label.text()


def test_thinking_stream_merge_handles_delta_snapshot_and_final(agent_panel):
    assert agent_panel._merge_thinking_chunk("", "hello ") == "hello "
    assert agent_panel._merge_thinking_chunk("hello ", "world") == "hello world"
    assert agent_panel._merge_thinking_chunk("hello world", "hello world") == "hello world"
    assert agent_panel._merge_thinking_chunk("hello wor", "world") == "hello world"

    agent_panel.start_thinking()
    agent_panel.append_thinking("hello ")
    agent_panel.append_thinking("world")
    agent_panel.append_thinking("hello world")
    row = agent_panel._messages_area.get_message_rows()[0]
    assert row._bubble_text == "hello world"


def test_summary_arrow_stays_next_to_text(qtbot):
    from autoreport.gui.widgets.message_row import MessageRow

    row = MessageRow(
        role="agent",
        content="detail",
        display_mode="thought",
        bubble_title="Thought for 1s",
        bubble_collapsible=True,
    )
    qtbot.addWidget(row)
    row.resize(600, 80)
    row.show()
    qtbot.waitExposed(row)

    text_right = row._summary_text_label.mapTo(row, row._summary_text_label.rect().topRight()).x()
    arrow_left = row._summary_arrow_widget.mapTo(row, row._summary_arrow_widget.rect().topLeft()).x()
    # The summary arrow sits immediately after the title text, separated only by
    # the content-host layout spacing (plus the arrow host's intrinsic layout).
    assert 0 <= arrow_left - text_right <= 12


def test_thought_summary_stays_single_line_when_width_is_sufficient(qtbot):
    from autoreport.gui.widgets.message_row import MessageRow

    row = MessageRow(
        role="agent",
        content="detail",
        display_mode="thought",
        bubble_title="Thought for 1s",
        bubble_collapsible=True,
    )
    qtbot.addWidget(row)
    row.resize(600, 80)
    row.show()
    qtbot.waitExposed(row)

    assert row._summary_text_label is not None
    line_height = row._summary_text_label.fontMetrics().lineSpacing()
    assert row._summary_text_label.height() <= line_height + 6


def test_thought_summary_label_keeps_visible_width(qtbot):
    from autoreport.gui.widgets.message_row import MessageRow

    row = MessageRow(
        role="agent",
        content="detail",
        display_mode="thought",
        bubble_title="Thought for 1s",
        bubble_collapsible=True,
    )
    qtbot.addWidget(row)
    row.resize(600, 80)
    row.show()
    qtbot.waitExposed(row)

    assert row._summary_text_label is not None
    assert row._summary_text_label.width() >= 80


def test_thought_detail_aligns_close_to_summary_start(qtbot):
    from autoreport.gui.widgets.message_row import MessageRow

    row = MessageRow(
        role="agent",
        content="detail line",
        display_mode="thought",
        bubble_title="Thought for 1s",
        bubble_collapsible=True,
    )
    qtbot.addWidget(row)
    row.resize(600, 120)
    row.show()
    qtbot.waitExposed(row)

    assert row._summary_header is not None
    assert row._detail_label is not None
    row._summary_header.clicked.emit()
    qtbot.wait(20)

    summary_left = row._summary_text_label.mapTo(row, row._summary_text_label.rect().topLeft()).x()
    detail_left = row._detail_label.mapTo(row, row._detail_label.rect().topLeft()).x()
    assert abs(detail_left - summary_left) <= 4


def test_set_debug_mode_shows_hides_panel(agent_panel):
    """Debug panel visibility should follow set_debug_mode()."""
    # Initially hidden
    assert agent_panel._debug_panel.isVisibleTo(agent_panel) is False

    # Toggle on via API (CLI-driven)
    agent_panel.set_debug_mode(True)
    # Check if the panel's visible property is set to True (even if not actually rendered)
    assert agent_panel._debug_panel.isVisible() is True or agent_panel._debug_panel.isVisibleTo(agent_panel) is True

    # Toggle off
    agent_panel.set_debug_mode(False)
    assert agent_panel._debug_panel.isVisible() is False


def test_add_error_creates_message(agent_panel):
    """add_error should create an error message row."""
    agent_panel.add_error("Tool", "Failed to execute")

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert "Tool" in rows[0]._content
    assert "Failed to execute" in rows[0]._content


def test_task_update_shows_summary_only(agent_panel):
    agent_panel.set_agent_type("plotting")
    agent_panel.handle_task_update(
        task_id="tk001",
        action="created",
        source="main",
        target="plotting",
        brief="plot summary",
    )

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert "plot summary" in rows[0]._content
    assert "tk001" not in rows[0]._content
    assert "📋 ○ 完成任务：" in rows[0]._content


def test_task_update_waitlist_format(agent_panel):
    agent_panel.set_agent_type("main")
    agent_panel.handle_task_update(
        task_id="tk001",
        action="created",
        source="main",
        target="theory",
        brief="derive formulas",
    )

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert "⏳ 等待Theory:" in rows[0]._content
    assert "Theory" in rows[0]._content
    assert "derive formulas" in rows[0]._content


def test_add_task_block_uses_task_tool_group_controls(agent_panel, qtbot):
    agent_panel.add_task_block(
        todolist=[{"brief": "Process data", "status": "pending"}],
        waitlist=[{"brief": "Plot figures", "status": "pending"}],
    )
    qtbot.wait(20)

    assert agent_panel._messages_area.get_message_rows() == []
    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 1

    controls = [
        label
        for label in groups[0].findChildren(QLabel)
        if label.objectName() == "taskStatusControl"
    ]
    texts = [
        label.text()
        for label in groups[0].findChildren(QLabel)
        if label.objectName() == "taskTextLabel"
    ]

    assert [control.text() for control in controls] == ["", ""]
    assert texts == ["Process data", "Plot figures"]


def test_task_block_can_precede_deferred_send_to_agent_group(agent_panel, qtbot):
    agent_panel.add_task_block(
        todolist=[],
        waitlist=[{"brief": "Derive formulas", "status": "pending"}],
    )
    agent_panel.add_tool_call(
        "send_to_agent",
        {"agent_type": "theory"},
        summary="Main to Theory",
        expandable=False,
    )
    agent_panel.add_tool_result(
        "send_to_agent",
        {"status": "delegated", "agent_type": "theory"},
        summary="Main to Theory",
        expandable=False,
    )
    qtbot.wait(20)

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 2
    assert groups[0].tool_names() == ["manage_tasks"]
    assert groups[1].tool_names() == ["send_to_agent"]


def test_task_block_between_send_to_agent_call_and_result_does_not_steal_result(
    agent_panel, qtbot
):
    agent_panel.add_tool_call(
        "send_to_agent",
        {"agent_type": "theory"},
        summary="Main to Theory",
        detail="delegate details",
        expandable=True,
    )
    agent_panel.add_task_block(
        todolist=[],
        waitlist=[{"brief": "Derive formulas", "status": "pending"}],
    )
    agent_panel.add_tool_result(
        "send_to_agent",
        {"status": "delegated", "agent_type": "theory"},
        summary="Main to Theory",
        detail="delegate details",
        expandable=True,
    )
    qtbot.wait(20)

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 2
    assert groups[0].tool_names() == ["send_to_agent"]
    assert groups[0].is_complete()
    assert groups[0]._header_arrow is not None
    assert not groups[0]._header_arrow.isHidden()
    assert groups[1].tool_names() == ["manage_tasks"]
    assert groups[1].is_complete()


def test_adjacent_task_block_snapshots_update_in_place(agent_panel):
    agent_panel.add_task_block(
        todolist=[{"brief": "Process data", "status": "pending"}],
        waitlist=[],
    )
    first_group = agent_panel._messages_area.get_tool_groups()[0]

    agent_panel.add_task_block(
        todolist=[{"brief": "Process data", "status": "completed"}],
        waitlist=[],
    )

    groups = agent_panel._messages_area.get_tool_groups()
    assert groups == [first_group]
    assert "☑ Process data" in groups[0].get_summary_text()
    assert "☐ Process data" not in groups[0].get_summary_text()


def test_task_block_after_explicit_manage_tasks_result_does_not_merge(agent_panel):
    explicit_summary = "<b>Task</b>\nWait\n○ Process data"

    agent_panel.add_tool_call(
        "manage_tasks",
        {"action": "complete", "task_id": "tk001", "brief": "Process data"},
    )
    agent_panel.add_tool_result("manage_tasks", explicit_summary, summary=explicit_summary)

    agent_panel.add_task_block(
        todolist=[{"brief": "Process data", "status": "completed"}],
        waitlist=[],
    )

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 2
    assert groups[0].tool_names() == ["manage_tasks"]
    assert groups[1].tool_names() == ["manage_tasks"]
    assert "Wait" in groups[0].get_summary_text()
    assert "Todo" in groups[1].get_summary_text()


def test_task_snapshot_absorbs_pending_manage_tasks_call(agent_panel, qtbot):
    agent_panel.add_tool_call(
        "manage_tasks",
        {"action": "start", "task_id": "tk001", "brief": "Process data"},
        summary="<b>Task</b>",
        expandable=False,
    )

    agent_panel.add_task_block(
        todolist=[{"brief": "Process data", "status": "in_progress"}],
        waitlist=[],
    )
    qtbot.wait(20)

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 1
    assert groups[0].tool_names() == ["manage_tasks"]
    assert groups[0].is_complete()
    assert groups[0].represents_task_snapshot()
    assert "● Process data" in groups[0].get_summary_text()


def test_add_checkpoint_creates_message(agent_panel):
    """add_checkpoint should create a checkpoint message row."""
    agent_panel.add_checkpoint("ckpt1", "Before tool execution")

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert "Before tool execution" in rows[0]._content


def test_pre_checkpoint_is_hidden(agent_panel):
    agent_panel.add_checkpoint("ckpt_pre", "pre:user")
    assert agent_panel._messages_area.message_count() == 0


def test_pre_checkpoint_attaches_to_latest_user_bubble(agent_panel):
    agent_panel.add_message(role="user", content="before rollback")
    row = agent_panel._messages_area.get_message_rows()[-1]

    agent_panel.add_checkpoint("ckpt_pre", "pre:user")

    assert row._checkpoint_id == "ckpt_pre"
    assert agent_panel._messages_area.message_count() == 1


def test_pre_checkpoint_attaches_to_matching_user_bubble_message_id(agent_panel):
    agent_panel.add_message(role="user", content="first", message_id="msg-1")
    first = agent_panel._messages_area.get_message_rows()[-1]
    agent_panel.add_message(role="user", content="second", message_id="msg-2")
    second = agent_panel._messages_area.get_message_rows()[-1]

    agent_panel.add_checkpoint("ckpt_first", "pre:user", message_id="msg-1")

    assert first._checkpoint_id == "ckpt_first"
    assert second._checkpoint_id is None


def test_pre_checkpoint_attaches_to_matching_reply_bubble_message_id(agent_panel):
    agent_panel.add_message(role="user", content="dispatch", message_id="dispatch-1")
    user_row = agent_panel._messages_area.get_message_rows()[-1]
    agent_panel.add_message(
        role="agent",
        content="reply",
        display_mode="bubble",
        bubble_title="Report replied",
        bubble_align="left",
        message_id="dispatch-1",
    )
    reply_row = agent_panel._messages_area.get_message_rows()[-1]

    agent_panel.add_checkpoint("ckpt_dispatch", "pre:main_agent", message_id="dispatch-1")

    assert user_row._checkpoint_id is None
    assert reply_row._checkpoint_id == "ckpt_dispatch"


def test_pre_checkpoint_pending_until_its_bubble_arrives(agent_panel):
    """A checkpoint whose bubble hasn't been created yet is queued, not dropped."""
    agent_panel.add_checkpoint("ckpt_late", "pre:user", message_id="msg-late")

    rows = agent_panel._messages_area.get_message_rows()
    assert all(getattr(r, "_checkpoint_id", None) is None for r in rows)

    agent_panel.add_message(role="user", content="hello", message_id="msg-late")
    row = agent_panel._messages_area.get_message_rows()[-1]
    assert getattr(row, "_message_id", None) == "msg-late"
    assert row._checkpoint_id == "ckpt_late"


def test_pre_checkpoint_matches_by_message_id_regardless_of_arrival_order(agent_panel):
    """Each bubble gets its own checkpoint even when checkpoints arrive out of order."""
    agent_panel.add_message(role="user", content="A", message_id="msg-A")
    agent_panel.add_message(role="user", content="B", message_id="msg-B")

    agent_panel.add_checkpoint("ckpt_B", "pre:user", message_id="msg-B")
    agent_panel.add_checkpoint("ckpt_A", "pre:user", message_id="msg-A")

    by_id = {
        getattr(r, "_message_id", None): r
        for r in agent_panel._messages_area.get_message_rows()
        if getattr(r, "_message_id", None)
    }
    assert by_id["msg-A"]._checkpoint_id == "ckpt_A"
    assert by_id["msg-B"]._checkpoint_id == "ckpt_B"


def test_left_reply_bubble_rollback_signal_reaches_panel(qtbot, agent_panel):
    agent_panel.add_message(
        role="agent",
        content="reply",
        display_mode="bubble",
        bubble_title="Report replied",
        bubble_align="left",
        message_id="dispatch-1",
    )
    reply_row = agent_panel._messages_area.get_message_rows()[-1]
    agent_panel.add_checkpoint("ckpt_dispatch", "pre:main_agent", message_id="dispatch-1")

    with qtbot.waitSignal(agent_panel.rollback_requested, timeout=1000) as blocker:
        reply_row.rollback_requested.emit("ckpt_dispatch", reply_row)

    assert blocker.args == ["ckpt_dispatch", reply_row]


def test_multiple_messages_and_tools(agent_panel):
    """Multiple messages and tool calls should be displayed correctly."""
    # Add user message
    agent_panel.add_message(role="user", content="Read the file")
    assert agent_panel._messages_area.message_count() == 1

    # Add tool call
    agent_panel.add_tool_call("read", {"path": "test.py"})
    assert agent_panel._messages_area.message_count() == 2

    # Add tool result
    agent_panel.add_tool_result("read", "content", None)
    assert agent_panel._messages_area.message_count() == 2

    # Add agent response
    agent_panel.add_message(role="agent", content="I've read the file")
    assert agent_panel._messages_area.message_count() == 3

    rows = agent_panel._messages_area.get_message_rows()
    groups = agent_panel._messages_area.get_tool_groups()

    assert len(rows) == 2  # user + agent response
    assert len(groups) == 1  # 1 tool group


def test_clear_messages(agent_panel):
    """clear should remove all messages."""
    agent_panel.add_message(role="user", content="Test")
    agent_panel.add_tool_call("test_tool", {})

    assert agent_panel._messages_area.message_count() == 2

    agent_panel._messages_area.clear()

    assert agent_panel._messages_area.message_count() == 0


# ---- Conversation history / new conversation buttons ----


def test_history_button_exists(agent_panel):
    """AgentPanel header should have a history button."""
    assert hasattr(agent_panel, "_history_btn")
    assert agent_panel._history_btn.objectName() == "headerAction"
    assert not agent_panel._history_btn.isHidden()


def test_new_conv_button_exists(agent_panel):
    """AgentPanel header should have a new conversation button."""
    assert hasattr(agent_panel, "_new_conv_btn")
    assert agent_panel._new_conv_btn.objectName() == "headerAction"
    assert not agent_panel._new_conv_btn.isHidden()


def test_history_requested_signal(qtbot, agent_panel):
    """Clicking history button should emit history_requested."""
    with qtbot.waitSignal(agent_panel.history_requested, timeout=1000):
        agent_panel._on_history()


def test_new_conversation_requested_signal(qtbot, agent_panel):
    """Clicking new conversation button should emit new_conversation_requested."""
    with qtbot.waitSignal(agent_panel.new_conversation_requested, timeout=1000):
        agent_panel._on_new_conversation()


def test_edit_saved_retracts_following_rows_and_sends_immediately(qtbot, agent_panel):
    agent_panel.add_message(role="user", content="old user")
    target_row = agent_panel._messages_area.get_message_rows()[-1]
    agent_panel.add_message(role="agent", content="old reply")
    agent_panel.add_tool_call("read", {"path": "a.txt"})

    assert agent_panel._messages_area.message_count() == 3

    with qtbot.waitSignal(agent_panel.message_edit_resend_requested, timeout=1000) as blocker:
        agent_panel._on_message_edit_saved("new user", target_row)

    assert blocker.args[0].startswith("new user")
    assert blocker.args[1] is target_row
    assert agent_panel._messages_area.message_count() == 0


def test_edit_saved_resends_plain_text_with_latest_file_context(qtbot, agent_panel):
    wrapped = "Editor context: file\nCurrent file: old.tex\n\nold user"
    row = agent_panel.add_message(role="user", content=wrapped)
    target_row = agent_panel._messages_area.get_message_rows()[-1]
    agent_panel.set_opened_file("latest.tex")

    with qtbot.waitSignal(agent_panel.message_edit_resend_requested, timeout=1000) as blocker:
        agent_panel._on_message_edit_saved("new user", target_row)

    assert blocker.args[0] == "new user"
    assert blocker.args[1] is target_row


def test_agent_selection_inserts_reference_without_property_error(agent_panel):
    agent_panel._input_field.setPlainText("@rep")
    agent_panel._input_field._popup_kind = "@"

    agent_panel._on_agent_selected("report")

    assert agent_panel._input_field.toPlainText() == "@Report Agent "


def test_file_reference_popup_is_attached_above_composer(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel.set_agent_type("theory")

    agent_panel._on_file_reference_requested("", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))
    qtbot.wait(20)

    popup = agent_panel._file_search_popup
    anchor = agent_panel._input_container.mapToGlobal(agent_panel._input_container.rect().topLeft())
    assert popup.isVisible()
    assert popup.geometry().bottom() <= anchor.y()
    assert popup.geometry().left() == anchor.x()
    assert popup.width() == agent_panel._input_container.width()
    assert popup.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is True
    assert popup.autoFillBackground() is False
    assert popup.mask().isEmpty() is False
    assert popup._frame.styleSheet()

    class _Future:
        def result(self):
            return [FileMatch(Path(f"Data/file_{i}.txt"), score=10) for i in range(8)]

    ticket = agent_panel._file_search_ticket + 1
    agent_panel._file_search_ticket = ticket
    agent_panel._apply_file_search_result(ticket, _Future())
    qtbot.wait(20)

    assert popup.geometry().bottom() <= anchor.y()
    assert popup.width() == agent_panel._input_container.width()
    popup.hide()


def test_file_reference_popup_displays_relative_file_paths(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel.set_agent_type("theory")

    agent_panel._on_file_reference_requested("Tex", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))

    class _Future:
        def result(self):
            return [FileMatch(agent_panel._workspace / "Tex" / "sections" / "sec-results.tex", score=10)]

    ticket = agent_panel._file_search_ticket + 1
    agent_panel._file_search_ticket = ticket
    agent_panel._apply_file_search_result(ticket, _Future())
    qtbot.wait(20)

    popup = agent_panel._file_search_popup
    file_items = [
        popup._list_widget.item(row)
        for row in range(popup._list_widget.count())
        if popup._list_widget.item(row).data(Qt.ItemDataRole.UserRole)[0] == "file"
    ]

    assert len(file_items) == 1
    assert file_items[0].text() == "Tex/sections/sec-results.tex"
    assert str(agent_panel._workspace) not in file_items[0].text()


def test_file_reference_popup_does_not_show_files_heading(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel.set_agent_type("theory")

    agent_panel._on_file_reference_requested("Tex", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))

    class _Future:
        def result(self):
            return [FileMatch(Path("Tex/main.tex"), score=10)]

    ticket = agent_panel._file_search_ticket + 1
    agent_panel._file_search_ticket = ticket
    agent_panel._apply_file_search_result(ticket, _Future())
    qtbot.wait(20)

    popup = agent_panel._file_search_popup
    texts = [popup._list_widget.item(row).text() for row in range(popup._list_widget.count())]

    assert not any("files" in text for text in texts)
    assert any("Tex/main.tex" in text for text in texts)


def test_file_reference_popup_file_rows_have_stable_height(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel.set_agent_type("theory")

    agent_panel._on_file_reference_requested("Tex", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))

    class _Future:
        def result(self):
            return [
                FileMatch(agent_panel._workspace / "Tex" / "main.pdf", score=10),
                FileMatch(agent_panel._workspace / "Tex" / "main.out", score=10),
            ]

    ticket = agent_panel._file_search_ticket + 1
    agent_panel._file_search_ticket = ticket
    agent_panel._apply_file_search_result(ticket, _Future())
    qtbot.wait(20)

    popup = agent_panel._file_search_popup
    file_rows = [
        row
        for row in range(popup._list_widget.count())
        if popup._list_widget.item(row).data(Qt.ItemDataRole.UserRole)[0] == "file"
    ]

    assert len(file_rows) == 2
    assert all(popup._list_widget.sizeHintForRow(row) >= 30 for row in file_rows)
    first = popup._list_widget.visualItemRect(popup._list_widget.item(file_rows[0]))
    second = popup._list_widget.visualItemRect(popup._list_widget.item(file_rows[1]))
    assert first.bottom() < second.top()


def test_file_reference_popup_mouse_click_selects_file(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel.set_agent_type("theory")
    agent_panel._input_field.setPlainText("@mai")
    agent_panel._input_field._popup_kind = "@"
    cursor = agent_panel._input_field.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    agent_panel._input_field.setTextCursor(cursor)

    agent_panel._on_file_reference_requested("mai", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))

    class _Future:
        def result(self):
            return [FileMatch(Path("Tex/main.tex"), score=10)]

    ticket = agent_panel._file_search_ticket + 1
    agent_panel._file_search_ticket = ticket
    agent_panel._apply_file_search_result(ticket, _Future())
    qtbot.wait(20)

    popup = agent_panel._file_search_popup
    file_row = next(
        row
        for row in range(popup._list_widget.count())
        if popup._list_widget.item(row).data(Qt.ItemDataRole.UserRole)[0] == "file"
    )
    rect = popup._list_widget.visualItemRect(popup._list_widget.item(file_row))
    qtbot.mouseClick(
        popup._list_widget.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )

    assert agent_panel._input_field.toPlainText() == "[@main.tex](project://Tex/main.tex)"
    assert not popup.isVisible()


def test_file_reference_popup_applies_async_file_search_results(qtbot, tmp_path):
    (tmp_path / "Tex").mkdir()
    (tmp_path / "Tex" / "main.tex").write_text("latex")
    panel = AgentPanel(
        panel_id="test_panel",
        title="Test Agent",
        workspace=tmp_path,
    )
    qtbot.addWidget(panel)
    panel.resize(520, 640)
    panel.show()
    qtbot.waitExposed(panel)

    panel._input_field.setPlainText("@Tex/")
    cursor = panel._input_field.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    panel._input_field.setTextCursor(cursor)
    panel._on_file_reference_requested("Tex/", panel._input_field.mapToGlobal(panel._input_field.rect().topLeft()))

    qtbot.waitUntil(
        lambda: any(
            panel._file_search_popup._list_widget.item(row).data(Qt.ItemDataRole.UserRole)[0] == "file"
            for row in range(panel._file_search_popup._list_widget.count())
        ),
        timeout=2000,
    )

    file_items = [
        panel._file_search_popup._list_widget.item(row).data(Qt.ItemDataRole.UserRole)[1]
        for row in range(panel._file_search_popup._list_widget.count())
        if panel._file_search_popup._list_widget.item(row).data(Qt.ItemDataRole.UserRole)[0] == "file"
    ]
    assert any(match.path.name == "main.tex" for match in file_items)


def test_file_reference_popup_forwards_editing_keys_to_input(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel._input_field.setPlainText("@abc")
    cursor = agent_panel._input_field.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    agent_panel._input_field.setTextCursor(cursor)

    agent_panel._on_file_reference_requested("abc", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))
    qtbot.wait(20)

    backspace = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Backspace,
        Qt.KeyboardModifier.NoModifier,
    )
    agent_panel._file_search_popup.keyPressEvent(backspace)

    assert agent_panel._input_field.toPlainText() == "@ab"

    letter = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_D,
        Qt.KeyboardModifier.NoModifier,
        "d",
    )
    agent_panel._file_search_popup.keyPressEvent(letter)

    assert agent_panel._input_field.toPlainText() == "@abd"


def test_file_reference_popup_list_forwards_editing_keys_to_input(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel._input_field.setPlainText("@abc")
    cursor = agent_panel._input_field.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    agent_panel._input_field.setTextCursor(cursor)

    agent_panel._on_file_reference_requested("abc", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))
    qtbot.wait(20)

    backspace = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Backspace,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(agent_panel._file_search_popup._list_widget, backspace)

    assert agent_panel._input_field.toPlainText() == "@ab"


def test_file_reference_popup_lists_other_agents_with_main_first(agent_panel):
    agent_panel.set_agent_type("theory")
    popup = agent_panel._file_search_popup
    popup.set_current_agent("theory")
    popup.set_query("", waiting=True)

    agent_types = [
        popup._list_widget.item(row).data(Qt.ItemDataRole.UserRole)[1]
        for row in range(popup._list_widget.count())
        if popup._list_widget.item(row).data(Qt.ItemDataRole.UserRole)[0] == "agent"
    ]

    assert agent_types == ["main", "data_analysis", "plotting", "report"]


def test_command_popup_is_attached_above_composer_and_keyboard_selects(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel._input_field.setPlainText("/he")
    cursor = agent_panel._input_field.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    agent_panel._input_field.setTextCursor(cursor)

    agent_panel._on_command_palette_requested("he", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))
    qtbot.wait(20)

    anchor = agent_panel._input_container.mapToGlobal(agent_panel._input_container.rect().topLeft())
    assert agent_panel._cmd_popup.isVisible()
    assert agent_panel._cmd_popup.geometry().bottom() <= anchor.y()
    assert agent_panel._cmd_popup.geometry().left() == anchor.x()
    assert agent_panel._cmd_popup.width() == agent_panel._input_container.width()

    executed: list[str] = []
    agent_panel._execute_slash_command = lambda cmd, original_text: executed.append(cmd)
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Tab,
        Qt.KeyboardModifier.NoModifier,
        "\t",
    )
    agent_panel._input_field.keyPressEvent(key_event)

    assert executed == []
    assert agent_panel._input_field.toPlainText() == "/help "
    assert not agent_panel._cmd_popup.isVisible()


def test_command_popup_only_lists_slash_commands(agent_panel, qtbot):
    agent_panel._on_command_palette_requested("", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))
    qtbot.wait(20)

    assert agent_panel._cmd_popup.count() > 0
    for row in range(agent_panel._cmd_popup.count()):
        assert agent_panel._cmd_popup.item(row).data(Qt.ItemDataRole.UserRole).startswith("/")


def test_command_popup_mouse_click_completes_selected_command(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel._input_field.setPlainText("/he")
    cursor = agent_panel._input_field.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    agent_panel._input_field.setTextCursor(cursor)

    agent_panel._on_command_palette_requested("he", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))
    qtbot.wait(20)

    executed: list[str] = []
    agent_panel._execute_slash_command = lambda cmd, original_text: executed.append(cmd)
    item = agent_panel._cmd_popup.item(0)
    rect = agent_panel._cmd_popup.visualItemRect(item)
    qtbot.mouseClick(
        agent_panel._cmd_popup.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )

    assert executed == []
    assert agent_panel._input_field.toPlainText() == "/help "
    assert not agent_panel._cmd_popup.isVisible()


def test_command_popup_forwards_editing_keys_to_input(agent_panel, qtbot):
    agent_panel.resize(520, 640)
    agent_panel.show()
    qtbot.waitExposed(agent_panel)
    agent_panel._input_field.setPlainText("/he")
    cursor = agent_panel._input_field.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    agent_panel._input_field.setTextCursor(cursor)

    agent_panel._on_command_palette_requested("he", agent_panel._input_field.mapToGlobal(agent_panel._input_field.rect().topLeft()))
    qtbot.wait(20)

    backspace = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Backspace,
        Qt.KeyboardModifier.NoModifier,
    )
    agent_panel._cmd_popup.keyPressEvent(backspace)

    assert agent_panel._input_field.toPlainText() == "/h"


def test_hide_conv_buttons(agent_panel):
    """hide_conv_buttons should hide both history and new-conv buttons."""
    agent_panel.hide_conv_buttons(True)
    assert agent_panel._history_btn.isHidden()
    assert agent_panel._new_conv_btn.isHidden()

    agent_panel.hide_conv_buttons(False)
    assert not agent_panel._history_btn.isHidden()
    assert not agent_panel._new_conv_btn.isHidden()
