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
    FILE_ROLLBACK_REQUEST = "file_rollback_request"

    # Backend → GUI
    AGENT_RESPONSE = "agent_response"
    AGENT_FEEDBACK = "agent_feedback"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATUS_CHANGE = "status_change"
    ERROR = "error"
    CHECKPOINT = "checkpoint"
    ROLLBACK_STATUS = "rollback_status"
    API_DEBUG = "api_debug"  # API call debugging information
    TASK_UPDATE = "task_update"
    QUEUE_UPDATE = "queue_update"


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


class TaskStatus(str, Enum):
    """Task lifecycle status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Message(BaseModel):
    """Base message for GUI-backend communication."""

    type: MessageType
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(use_enum_values=True)


class UserMessage(Message):
    """User message to agent.

    source distinguishes direct user input ("user") from
    main-agent coordination commands ("main_agent").  Debug
    mode filters out the latter.
    """

    type: MessageType = MessageType.USER_MESSAGE
    content: str
    agent_type: AgentType = AgentType.MAIN
    message_id: str | None = None
    source: str = "user"  # "user" | "system" | "main_agent" | "<agent_type>"


class AgentResponse(Message):
    """Agent response to user."""

    type: MessageType = MessageType.AGENT_RESPONSE
    agent_type: AgentType
    content: str
    message_id: str | None = None
    streaming: bool = False  # True for stream chunks, False for final completion
    thinking: str | None = None


class AgentFeedback(Message):
    """Sub-agent feedback to main agent for coordination.

    Sub-agents send this when they detect issues that require
    main agent intervention (e.g., other agent's output is wrong).
    """

    type: MessageType = MessageType.AGENT_FEEDBACK
    agent_type: AgentType
    content: str
    feedback_type: str = "missing_data"  # "missing_data", "quality", "query"


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
    """Checkpoint created for rollback — per-agent."""

    type: MessageType = MessageType.CHECKPOINT
    agent_type: str  # "main", "data_analysis", "plotting", "theory", "report"
    checkpoint_id: str
    description: str
    file_states: dict[str, str]  # path -> hash
    message_id: str | None = None  # The message that triggered this checkpoint


class FileRollbackRequest(Message):
    """GUI request to rollback files to a specific checkpoint.

    Sent when the user right-clicks a message in the chat and selects
    "Rollback files to this point".
    """

    type: MessageType = MessageType.FILE_ROLLBACK_REQUEST
    checkpoint_id: str
    agent_type: str  # "main", "data_analysis", "plotting", "theory", "report"
    message_id: str | None = None  # The message that triggered this rollback


class RollbackStatus(Message):
    """Backend → GUI: result of a file rollback operation."""

    type: MessageType = MessageType.ROLLBACK_STATUS
    checkpoint_id: str
    agent_type: str
    success: bool
    restored_files: int = 0
    error: str | None = None


class Error(Message):
    """Error message."""

    type: MessageType = MessageType.ERROR
    source: str  # "agent", "tool", "system"
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class TaskItem(BaseModel):
    """Single task record — dual view: waitlist for source_agent, todolist for target_agent."""

    task_id: str
    brief: str
    source_agent: AgentType
    target_agent: AgentType
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    blocking: bool = False
    session_id: str | None = None


class TaskUpdateMessage(Message):
    """Task lifecycle notification routed through the message bus."""

    type: MessageType = MessageType.TASK_UPDATE
    task_id: str
    action: str  # "created" | "started" | "completed" | "failed" | "cancelled"
    source_agent: AgentType
    target_agent: AgentType
    brief: str = ""
    previous_status: str | None = None


class QueueUpdateMessage(Message):
    """Queued follow-up messages waiting for the next agent turn."""

    type: MessageType = MessageType.QUEUE_UPDATE
    agent_type: AgentType
    queued_messages: list[str] = Field(default_factory=list)


class ApiDebugMessage(Message):
    """API debug information for monitoring LLM calls.

    Published by AgentLoop when making LLM API calls, allowing
    GUI components to display timing, token usage, and error information.
    """

    type: MessageType = MessageType.API_DEBUG
    timestamp: datetime = Field(default_factory=datetime.now)
    model: str  # Model name (e.g., "claude-sonnet-4-20250514")
    tokens_in: int  # Input tokens
    tokens_out: int  # Output tokens
    duration_ms: int  # Duration in milliseconds
    status: str  # "success" or "error"
    error: str | None = None  # Error message if status is "error"
