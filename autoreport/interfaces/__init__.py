"""Interface layer for GUI-backend communication."""

from .protocol import GUIAPI, BackendAPI, MessageChannel
from .types import (
    AgentResponse,
    AgentStatus,
    AgentType,
    Checkpoint,
    ConfigChange,
    Error,
    Message,
    MessageType,
    RestartRequest,
    StatusChange,
    ToolCallMessage,
    ToolResult,
    UserMessage,
)

__all__ = [
    "MessageType",
    "AgentType",
    "AgentStatus",
    "Message",
    "UserMessage",
    "AgentResponse",
    "ToolCallMessage",
    "ToolResult",
    "StatusChange",
    "ConfigChange",
    "RestartRequest",
    "Checkpoint",
    "Error",
    "MessageChannel",
    "BackendAPI",
    "GUIAPI",
]
