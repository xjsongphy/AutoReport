"""Interface type definitions for GUI-backend communication."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageType(str, Enum):
    """Message types between GUI and backend."""

    # GUI → Backend
    USER_MESSAGE = "user_message"
    CONFIG_CHANGE = "config_change"
    PROJECT_SELECT = "project_select"
    RESTART_REQUEST = "restart_request"

    # Backend → GUI
    AGENT_RESPONSE = "agent_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATUS_CHANGE = "status_change"
    ERROR = "error"
    CHECKPOINT = "checkpoint"


class AgentType(str, Enum):
    """Agent types."""

    MAIN = "main"
    DATA_ANALYSIS = "data_analysis"
    PLOTTING = "plotting"
    THEORY = "theory"
    REPORT = "report"


class AgentStatus(str, Enum):
    """Agent status."""

    IDLE = "idle"
    THINKING = "thinking"
    RUNNING_TOOL = "running_tool"
    ERROR = "error"
    DEBUG_MODE = "debug_mode"


class Message(BaseModel):
    """Base message for GUI-backend communication."""

    type: MessageType
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(use_enum_values=True)


class UserMessage(Message):
    """User message to agent."""

    type: MessageType = MessageType.USER_MESSAGE
    content: str
    agent_type: AgentType = AgentType.MAIN
    message_id: str | None = None


class AgentResponse(Message):
    """Agent response to user."""

    type: MessageType = MessageType.AGENT_RESPONSE
    agent_type: AgentType
    content: str
    message_id: str | None = None


class ToolCall(Message):
    """Tool being executed by agent."""

    type: MessageType = MessageType.TOOL_CALL
    agent_type: AgentType
    tool_name: str
    arguments: dict[str, Any]


class ToolResult(Message):
    """Result of tool execution."""

    type: MessageType = MessageType.TOOL_RESULT
    agent_type: AgentType
    tool_name: str
    result: Any
    error: str | None = None


class StatusChange(Message):
    """Agent status change."""

    type: MessageType = MessageType.STATUS_CHANGE
    agent_type: AgentType
    status: AgentStatus
    extra: dict[str, Any] = Field(default_factory=dict)


class ConfigChange(Message):
    """Configuration change notification."""

    type: MessageType = MessageType.CONFIG_CHANGE
    config_type: str  # "provider", "model", etc.
    old_value: Any
    new_value: Any


class RestartRequest(Message):
    """Request to restart agent system."""

    type: MessageType = MessageType.RESTART_REQUEST
    reason: str  # "config_change", "user_request"


class Checkpoint(Message):
    """Checkpoint created for rollback."""

    type: MessageType = MessageType.CHECKPOINT
    checkpoint_id: str
    description: str
    file_states: dict[str, str]  # path -> hash or snapshot


class Error(Message):
    """Error message."""

    type: MessageType = MessageType.ERROR
    source: str  # "agent", "tool", "system"
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
