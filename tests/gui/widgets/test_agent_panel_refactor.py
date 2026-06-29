"""Tests for refactored AgentPanel with MessagesArea and DebugPanel."""

from pathlib import Path
import pytest

from autoreport.gui.widgets.agent_panel import AgentPanel


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


def test_selection_context_label_uses_line_count(agent_panel):
    agent_panel.set_preview_context("sections/intro.tex", "a\nb", 3, 4)

    assert agent_panel._context_attachment_btn.text() == "2 lines selected"
    assert agent_panel._context_attachment_btn.toolTip() == "sections/intro.tex"


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
    assert rows[0]._bubble_title.startswith("Thought for ")
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
    assert row._bubble_title.startswith("Thought for ")
    assert row._bubble_title != "Thought for 1s"


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

    with qtbot.waitSignal(agent_panel.message_sent, timeout=1000) as blocker:
        agent_panel._on_message_edit_saved("new user", target_row)

    assert blocker.args[0].startswith("new user")
    assert agent_panel._messages_area.message_count() == 0


def test_edit_saved_resends_plain_text_with_latest_file_context(qtbot, agent_panel):
    wrapped = "Editor context: file\nCurrent file: old.tex\n\nold user"
    row = agent_panel.add_message(role="user", content=wrapped)
    target_row = agent_panel._messages_area.get_message_rows()[-1]
    agent_panel.set_opened_file("latest.tex")

    with qtbot.waitSignal(agent_panel.file_context_attached, timeout=1000) as context_blocker:
        with qtbot.waitSignal(agent_panel.message_sent, timeout=1000) as message_blocker:
            agent_panel._on_message_edit_saved("new user", target_row)

    assert message_blocker.args == ["new user"]
    assert context_blocker.args[0]["file"] == "latest.tex"


def test_hide_conv_buttons(agent_panel):
    """hide_conv_buttons should hide both history and new-conv buttons."""
    agent_panel.hide_conv_buttons(True)
    assert agent_panel._history_btn.isHidden()
    assert agent_panel._new_conv_btn.isHidden()

    agent_panel.hide_conv_buttons(False)
    assert not agent_panel._history_btn.isHidden()
    assert not agent_panel._new_conv_btn.isHidden()
