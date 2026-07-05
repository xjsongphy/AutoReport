"""LLM Provider base classes and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Tool call from LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Tool result to send back to LLM."""

    tool_call_id: str
    content: str


@dataclass
class Message:
    """Chat message with optional structured content for tool calls/results.

    Providers convert these to API-specific formats:
    - Anthropic: tool_calls → content blocks with type="tool_use",
                 tool_results → user message with type="tool_result" blocks
    - OpenAI-compat: tool_calls → assistant message with tool_calls field,
                     tool_results → separate "tool" role messages
    """

    role: str  # "user", "assistant", "system"
    content: str
    tool_calls: list[ToolCall] | None = None  # assistant messages with tool calls
    tool_call_id: str | None = None  # tool result messages (role="tool" for OpenAI)
    is_tool_result: bool = False  # marks this as a tool result message
    thinking: str | None = None  # DeepSeek extended thinking blocks
    cache_control: bool = False  # mark for prompt caching (Anthropic ephemeral cache)


@dataclass
class LLMResponse:
    """Response from LLM."""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] | None = None
    streaming: bool = False  # Whether this is a streaming chunk
    thinking: str | None = None  # DeepSeek extended thinking


@dataclass
class LLMStreamChunk:
    """Single chunk from streaming LLM response."""

    delta: str | None = None  # Text content delta (None if no new text)
    tool_calls: list[ToolCall] | None = None  # Final tool calls at end
    done: bool = False  # Whether stream is complete
    thinking: str | None = None  # DeepSeek extended thinking


class LLMProvider(ABC):
    """Base class for LLM providers."""

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        model: str | None = None,
    ):
        """Initialize provider.

        Args:
            api_key: API key for authentication.
            api_base: Optional custom API base URL.
            model: Default model to use.
        """
        self.api_key = api_key
        self.api_base = api_base
        self.model = model

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send chat completion request.

        Args:
            messages: List of chat messages (may contain tool calls/results).
            tools: Optional list of tool definitions for function calling.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Returns:
            LLM response with content and/or tool calls.
        """

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ):
        """Send streaming chat completion request.

        Yields LLMStreamChunk objects as text arrives.

        Args:
            messages: List of chat messages.
            tools: Optional list of tool definitions.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Yields:
            LLMStreamChunk with delta content for each chunk.
        """
        raise NotImplementedError(f"Streaming not implemented for {self.__class__.__name__}")
