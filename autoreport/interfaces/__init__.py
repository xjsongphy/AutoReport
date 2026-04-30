"""Interface layer for GUI-backend communication."""

from .types import (
    MessageType,
    AgentType,
    AgentStatus,
    Message,
    UserMessage,
    AgentResponse,
    ToolCall,
    ToolResult,
    StatusChange,
    ConfigChange,
    RestartRequest,
    Checkpoint,
    Error,
)
from .protocol import MessageChannel, BackendAPI, GUIAPI

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
