"""Anthropic Claude provider."""

from typing import Any

from anthropic import AsyncAnthropic
from loguru import logger

from .base import LLMProvider, LLMResponse, Message, ToolCall


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        super().__init__(api_key, api_base, model)
        self.client = AsyncAnthropic(api_key=api_key, base_url=api_base)

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict]]:
        """Convert internal messages to Anthropic API format.

        Handles three special message types:
        1. Assistant messages with tool_calls → content blocks with type="tool_use"
        2. Tool result messages (is_tool_result=True) → grouped into a user message
           with type="tool_result" blocks
        3. Regular messages → simple role/content dicts

        Per Anthropic API spec:
        - tool_use blocks go in assistant messages
        - tool_result blocks go in user messages (keyed by tool_use_id)
        """
        system_message = None
        anthropic_messages: list[dict] = []
        pending_tool_results: list[dict] = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                continue

            # Flush pending tool results before adding a new non-tool message
            if pending_tool_results and not msg.is_tool_result:
                anthropic_messages.append({
                    "role": "user",
                    "content": pending_tool_results,
                })
                pending_tool_results = []

            # Assistant message with tool calls → structured content blocks
            if msg.role == "assistant" and msg.tool_calls:
                content_blocks: list[dict] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content_blocks,
                })
                continue

            # Tool result → collect into pending list (grouped as one user message)
            if msg.is_tool_result:
                pending_tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content,
                })
                continue

            # Regular text message
            anthropic_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        # Flush any remaining tool results
        if pending_tool_results:
            anthropic_messages.append({
                "role": "user",
                "content": pending_tool_results,
            })

        return system_message, anthropic_messages

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send chat completion request."""
        system_message, anthropic_messages = self._convert_messages(messages)

        params: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if system_message:
            params["system"] = system_message

        if tools:
            params["tools"] = self._convert_tools(tools)

        logger.debug("Sending Anthropic request: model={}, messages={}", self.model, len(messages))

        response = await self.client.messages.create(**params)

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

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert tools to Anthropic format."""
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            }
            for tool in tools
        ]
