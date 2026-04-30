"""Anthropic Claude provider."""

from typing import Any

from anthropic import AsyncAnthropic
from loguru import logger

from .base import LLMProvider, LLMResponse, Message, ToolCall, ToolResult


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        model: str = "claude-sonnet-4.5",
    ):
        """Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key.
            api_base: Optional custom API base (not typically used).
            model: Model to use.
        """
        super().__init__(api_key, api_base, model)
        self.client = AsyncAnthropic(api_key=api_key, base_url=api_base)

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send chat completion request."""
        # Convert messages to Anthropic format
        anthropic_messages = []
        system_message = None

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                anthropic_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # Prepare request parameters
        params: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if system_message:
            params["system"] = system_message

        if tools:
            # Convert tools to Anthropic format
            params["tools"] = self._convert_tools(tools)

        logger.debug("Sending Anthropic request: model={}, messages={}", self.model, len(messages))

        try:
            response = await self.client.messages.create(**params)

            # Extract content and tool calls
            content = None
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content = block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    ))

            logger.debug(
                "Anthropic response: content_length={}, tool_calls={}, input_tokens={}, output_tokens={}",
                len(content) if content else 0,
                len(tool_calls),
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                },
            )

        except Exception as e:
            logger.error("Anthropic API error: {}", e)
            raise

    async def chat_with_tools(
        self,
        messages: list[Message],
        tool_results: list[ToolResult],
        tools: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send chat completion with tool results."""
        # Convert messages and add tool results
        anthropic_messages = []
        system_message = None

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                # Add message
                content = [{"type": "text", "text": msg.content}]
                anthropic_messages.append({
                    "role": msg.role,
                    "content": content,
                })

        # Add tool results
        for msg in anthropic_messages:
            if msg["role"] == "assistant":
                # Find tool calls in this message
                # This is a simplified version - real implementation would track tool calls
                for result in tool_results:
                    msg["content"].append({
                        "type": "tool_result",
                        "tool_use_id": result.tool_call_id,
                        "content": result.content,
                    })

        # Prepare request
        params: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": self._convert_tools(tools),
        }

        if system_message:
            params["system"] = system_message

        try:
            response = await self.client.messages.create(**params)

            # Extract response
            content = None
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content = block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    ))

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )

        except Exception as e:
            logger.error("Anthropic API error with tools: {}", e)
            raise

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert tools to Anthropic format.

        Args:
            tools: Tool definitions in standard format.

        Returns:
            Tools in Anthropic format.
        """
        anthropic_tools = []

        for tool in tools:
            anthropic_tools.append({
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            })

        return anthropic_tools
