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
        summary="Collapsed summary",
        detail="detail line 1\ndetail line 2",
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


def test_set_agent_type_uses_badged_title(agent_panel):
    agent_panel.set_agent_type("theory")
    # Title shows agent name, icon is shown separately in _icon_label
    assert agent_panel._title_label.text() == "Theory Agent"
    assert agent_panel._icon_label.pixmap() is not None  # Icon is set


def test_add_tool_call_creates_group(agent_panel):
    """add_tool_call should create a ToolCallGroup."""
    agent_panel.add_tool_call("read_file", {"path": "test.py"})

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 1
    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert rows[0]._role == "agent"


def test_add_tool_result_adds_to_group(agent_panel):
    """add_tool_result should add to the current tool group."""
    # First add a tool call
    agent_panel.add_tool_call("read_file", {"path": "test.py"})

    # Then add the result
    agent_panel.add_tool_result("read_file", "file content", error=None)

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 1

    # Check that the tool group has the tool call
    # The group should have 1 tool call — summary uses display names
    summary = groups[0].get_summary_text()
    assert "Read File" in summary


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


def test_tool_call_before_agent_text_reuses_agent_anchor(agent_panel):
    agent_panel.add_tool_call("list_dir", {"path": "."})
    agent_panel.add_message(role="agent", content="Hello", streaming=True)

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert rows[0]._role == "agent"
    assert rows[0]._content == "Hello"


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
    assert "TODO" in rows[0]._content
    assert "Main" in rows[0]._content


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
    assert "WAIT" in rows[0]._content
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


def test_multiple_messages_and_tools(agent_panel):
    """Multiple messages and tool calls should be displayed correctly."""
    # Add user message
    agent_panel.add_message(role="user", content="Read the file")
    assert agent_panel._messages_area.message_count() == 1

    # Add tool call
    agent_panel.add_tool_call("read_file", {"path": "test.py"})
    assert agent_panel._messages_area.message_count() == 3

    # Add tool result
    agent_panel.add_tool_result("read_file", "content", None)
    assert agent_panel._messages_area.message_count() == 3  # Still 3 (anchor + tool group + user)

    # Add agent response
    agent_panel.add_message(role="agent", content="I've read the file")
    assert agent_panel._messages_area.message_count() == 3

    rows = agent_panel._messages_area.get_message_rows()
    groups = agent_panel._messages_area.get_tool_groups()

    assert len(rows) == 2  # user + anchored agent message
    assert len(groups) == 1  # 1 tool group


def test_clear_messages(agent_panel):
    """clear should remove all messages."""
    agent_panel.add_message(role="user", content="Test")
    agent_panel.add_tool_call("test_tool", {})

    assert agent_panel._messages_area.message_count() == 3

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
    agent_panel.add_tool_call("read_file", {"path": "a.txt"})

    assert agent_panel._messages_area.message_count() == 3

    with qtbot.waitSignal(agent_panel.message_sent, timeout=1000) as blocker:
        agent_panel._on_message_edit_saved("new user", target_row)

    assert blocker.args[0].startswith("new user")
    assert agent_panel._messages_area.message_count() == 0


def test_hide_conv_buttons(agent_panel):
    """hide_conv_buttons should hide both history and new-conv buttons."""
    agent_panel.hide_conv_buttons(True)
    assert agent_panel._history_btn.isHidden()
    assert agent_panel._new_conv_btn.isHidden()

    agent_panel.hide_conv_buttons(False)
    assert not agent_panel._history_btn.isHidden()
    assert not agent_panel._new_conv_btn.isHidden()
