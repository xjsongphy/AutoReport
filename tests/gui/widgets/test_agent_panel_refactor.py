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


def test_add_tool_call_creates_group(agent_panel):
    """add_tool_call should create a ToolCallGroup."""
    agent_panel.add_tool_call("read_file", {"path": "test.py"})

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 1


def test_add_tool_result_adds_to_group(agent_panel):
    """add_tool_result should add to the current tool group."""
    # First add a tool call
    agent_panel.add_tool_call("read_file", {"path": "test.py"})

    # Then add the result
    agent_panel.add_tool_result("read_file", "file content", error=None)

    groups = agent_panel._messages_area.get_tool_groups()
    assert len(groups) == 1

    # Check that the tool group has the tool call
    # The group should have 1 tool call
    summary = groups[0].get_summary_text()
    assert "read_file" in summary


def test_debug_toggle_shows_hides_panel(agent_panel):
    """Debug button toggle should show/hide debug panel."""
    # Initially hidden
    assert agent_panel._debug_panel.isVisibleTo(agent_panel) is False
    assert agent_panel._debug_button.isChecked() is False

    # Toggle on by clicking the button
    agent_panel._debug_button.setChecked(True)  # Manually set checked state
    agent_panel._on_debug_toggled()  # Call the toggle handler directly
    # Check if the panel's visible property is set to True (even if not actually rendered)
    assert agent_panel._debug_panel.isVisible() is True or agent_panel._debug_panel.isVisibleTo(agent_panel) is True

    # Toggle off
    agent_panel._debug_button.setChecked(False)
    agent_panel._on_debug_toggled()
    assert agent_panel._debug_panel.isVisible() is False


def test_add_error_creates_message(agent_panel):
    """add_error should create an error message row."""
    agent_panel.add_error("Tool", "Failed to execute")

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert "Tool" in rows[0]._content
    assert "Failed to execute" in rows[0]._content


def test_add_checkpoint_creates_message(agent_panel):
    """add_checkpoint should create a checkpoint message row."""
    agent_panel.add_checkpoint("ckpt1", "Before tool execution")

    rows = agent_panel._messages_area.get_message_rows()
    assert len(rows) == 1
    assert "Before tool execution" in rows[0]._content


def test_multiple_messages_and_tools(agent_panel):
    """Multiple messages and tool calls should be displayed correctly."""
    # Add user message
    agent_panel.add_message(role="user", content="Read the file")
    assert agent_panel._messages_area.message_count() == 1

    # Add tool call
    agent_panel.add_tool_call("read_file", {"path": "test.py"})
    assert agent_panel._messages_area.message_count() == 2

    # Add tool result
    agent_panel.add_tool_result("read_file", "content", None)
    assert agent_panel._messages_area.message_count() == 2  # Still 2 (tool group is 1 item)

    # Add agent response
    agent_panel.add_message(role="agent", content="I've read the file")
    assert agent_panel._messages_area.message_count() == 3

    rows = agent_panel._messages_area.get_message_rows()
    groups = agent_panel._messages_area.get_tool_groups()

    assert len(rows) == 2  # user + agent messages
    assert len(groups) == 1  # 1 tool group


def test_clear_messages(agent_panel):
    """clear should remove all messages."""
    agent_panel.add_message(role="user", content="Test")
    agent_panel.add_tool_call("test_tool", {})

    assert agent_panel._messages_area.message_count() == 2

    agent_panel._messages_area.clear()

    assert agent_panel._messages_area.message_count() == 0
