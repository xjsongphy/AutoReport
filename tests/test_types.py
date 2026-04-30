"""Tests for interface type definitions."""

from datetime import datetime

from autoreport.interfaces.types import (
    AgentResponse,
    AgentStatus,
    AgentType,
    Checkpoint,
    ConfigChange,
    Error,
    MessageType,
    RestartRequest,
    StatusChange,
    ToolCall,
    ToolResult,
    UserMessage,
)


def test_message_type_enum_values():
    assert MessageType.USER_MESSAGE == "user_message"
    assert MessageType.AGENT_RESPONSE == "agent_response"
    assert MessageType.TOOL_CALL == "tool_call"
    assert MessageType.TOOL_RESULT == "tool_result"
    assert MessageType.STATUS_CHANGE == "status_change"
    assert MessageType.CONFIG_CHANGE == "config_change"
    assert MessageType.RESTART_REQUEST == "restart_request"
    assert MessageType.ERROR == "error"
    assert MessageType.CHECKPOINT == "checkpoint"


def test_agent_type_enum_values():
    assert AgentType.MAIN == "main"
    assert AgentType.DATA_ANALYSIS == "data_analysis"
    assert AgentType.PLOTTING == "plotting"
    assert AgentType.THEORY == "theory"
    assert AgentType.REPORT == "report"


def test_agent_status_enum_values():
    assert AgentStatus.IDLE == "idle"
    assert AgentStatus.THINKING == "thinking"
    assert AgentStatus.RUNNING_TOOL == "running_tool"
    assert AgentStatus.ERROR == "error"
    assert AgentStatus.DEBUG_MODE == "debug_mode"


def test_user_message_defaults():
    msg = UserMessage(content="Hello")
    assert msg.type == "user_message"
    assert msg.content == "Hello"
    assert msg.agent_type == "main"
    assert msg.source == "user"
    assert msg.message_id is None


def test_user_message_with_agent_type():
    msg = UserMessage(content="Analyze data", agent_type=AgentType.DATA_ANALYSIS)
    assert msg.agent_type == "data_analysis"


def test_user_message_from_main_agent():
    msg = UserMessage(content="Coordinate", source="main_agent")
    assert msg.source == "main_agent"


def test_agent_response():
    msg = AgentResponse(agent_type=AgentType.THEORY, content="Result")
    assert msg.type == "agent_response"
    assert msg.agent_type == "theory"
    assert msg.content == "Result"


def test_tool_call_message():
    msg = ToolCall(
        agent_type=AgentType.DATA_ANALYSIS,
        tool_name="read_file",
        arguments={"path": "data.csv"},
    )
    assert msg.type == "tool_call"
    assert msg.tool_name == "read_file"
    assert msg.arguments["path"] == "data.csv"


def test_tool_result_message():
    msg = ToolResult(
        agent_type=AgentType.DATA_ANALYSIS,
        tool_name="read_file",
        result={"content": "data"},
    )
    assert msg.type == "tool_result"
    assert msg.error is None


def test_tool_result_with_error():
    msg = ToolResult(
        agent_type=AgentType.REPORT,
        tool_name="exec",
        result=None,
        error="Command failed",
    )
    assert msg.error == "Command failed"


def test_status_change():
    msg = StatusChange(agent_type=AgentType.MAIN, status=AgentStatus.THINKING)
    assert msg.type == "status_change"
    assert msg.status == "thinking"
    assert msg.extra == {}


def test_config_change():
    msg = ConfigChange(
        config_type="provider",
        old_value="openai",
        new_value="anthropic",
    )
    assert msg.type == "config_change"
    assert msg.new_value == "anthropic"


def test_restart_request():
    msg = RestartRequest(reason="config_change")
    assert msg.type == "restart_request"
    assert msg.reason == "config_change"


def test_checkpoint_message():
    msg = Checkpoint(
        checkpoint_id="cp_12345678",
        description="Before analysis",
        file_states={"data/test.csv": "abc123"},
    )
    assert msg.type == "checkpoint"
    assert msg.file_states["data/test.csv"] == "abc123"


def test_error_message():
    msg = Error(source="agent", message="Something failed")
    assert msg.type == "error"
    assert msg.details == {}


def test_message_has_timestamp():
    msg = UserMessage(content="test")
    assert isinstance(msg.timestamp, datetime)


def test_enum_values_used_in_messages():
    """Verify use_enum_values config converts enums to strings."""
    msg = StatusChange(agent_type=AgentType.MAIN, status=AgentStatus.THINKING)
    assert isinstance(msg.agent_type, str)
    assert isinstance(msg.status, str)
