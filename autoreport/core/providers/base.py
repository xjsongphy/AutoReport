"""LLM Provider base classes and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Message:
    """Chat message."""

    role: str  # "user", "assistant", "system"
    content: str


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
class LLMResponse:
    """Response from LLM."""

    content: str | None
    tool_calls: list[ToolCall]
    usage: dict[str, int] | None = None


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
            messages: List of chat messages.
            tools: Optional list of tool definitions for function calling.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Returns:
            LLM response with content and/or tool calls.
        """

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[Message],
        tool_results: list[ToolResult],
        tools: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send chat completion with tool results.

        Args:
            messages: List of chat messages (including tool calls).
            tool_results: Results from tool executions.
            tools: List of tool definitions.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Returns:
            LLM response.
        """
