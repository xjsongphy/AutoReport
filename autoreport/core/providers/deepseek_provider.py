"""DeepSeek provider (OpenAI-compatible)."""

from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse, Message, ToolCall, ToolResult


class DeepSeekProvider(LLMProvider):
    """DeepSeek provider (uses OpenAI-compatible API)."""

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        model: str = "deepseek-chat",
    ):
        """Initialize DeepSeek provider.

        Args:
            api_key: DeepSeek API key.
            api_base: Optional custom API base (defaults to DeepSeek's API).
            model: Model to use.
        """
        # DeepSeek uses OpenAI-compatible API
        if api_base is None:
            api_base = "https://api.deepseek.com"

        super().__init__(api_key, api_base, model)
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
        )

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send chat completion request."""
        # Convert messages
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        # Prepare request
        params: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            params["tools"] = self._convert_tools(tools)

        logger.debug("Sending DeepSeek request: model={}, messages={}", self.model, len(messages))

        try:
            response = await self.client.chat.completions.create(**params)

            # Extract response
            message = response.choices[0].message
            content = message.content
            tool_calls = []

            if message.tool_calls:
                for call in message.tool_calls:
                    tool_calls.append(ToolCall(
                        id=call.id,
                        name=call.function.name,
                        arguments=self._parse_arguments(call.function.arguments),
                    ))

            logger.debug(
                "DeepSeek response: content_length={}, tool_calls={}, prompt_tokens={}, completion_tokens={}",
                len(content) if content else 0,
                len(tool_calls),
                response.usage.prompt_tokens if response.usage else 0,
                response.usage.completion_tokens if response.usage else 0,
            )

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage={
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
            )

        except Exception as e:
            logger.error("DeepSeek API error: {}", e)
            raise

    async def chat_with_tools(
        self,
        messages: list[Message],
        tool_results: list[ToolResult],
        tools: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send chat completion with tool results.

        Note: This method is deprecated in favor of using chat() with properly
        maintained conversation history. It's kept for backward compatibility.
        """
        openai_messages = []

        for msg in messages:
            openai_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        # Add tool results at the end (assuming they come after the last assistant message)
        for result in tool_results:
            openai_messages.append({
                "role": "tool",
                "tool_call_id": result.tool_call_id,
                "content": result.content,
            })

        # Prepare request
        params: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": self._convert_tools(tools),
        }

        try:
            response = await self.client.chat.completions.create(**params)

            message = response.choices[0].message
            content = message.content
            tool_calls = []

            if message.tool_calls:
                for call in message.tool_calls:
                    tool_calls.append(ToolCall(
                        id=call.id,
                        name=call.function.name,
                        arguments=self._parse_arguments(call.function.arguments),
                    ))

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage={
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                },
            )

        except Exception as e:
            logger.error("DeepSeek API error with tools: {}", e)
            raise

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert tools to OpenAI format.

        Args:
            tools: Tool definitions in standard format.

        Returns:
            Tools in OpenAI format.
        """
        openai_tools = []

        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            })

        return openai_tools

    def _parse_arguments(self, arguments: str) -> dict:
        """Parse JSON arguments string.

        Args:
            arguments: JSON string.

        Returns:
            Parsed arguments dict.
        """
        import json
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool arguments: {}", arguments)
            return {}
