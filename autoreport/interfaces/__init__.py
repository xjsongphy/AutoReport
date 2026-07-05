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
    ToolCall,
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
    "ToolCall",
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
