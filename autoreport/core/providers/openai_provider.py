"""OpenAI-compatible provider.

Handles all providers using the OpenAI Chat Completions API format:
OpenAI, DeepSeek, Google, OpenRouter, Groq, and custom endpoints.
"""

import json
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse, LLMStreamChunk, Message, LLMToolCall
from .defaults import DEFAULT_API_BASES


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI-compatible APIs."""

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        model: str = "gpt-4o",
        provider_type: str = "openai",
    ):
        super().__init__(api_key, api_base, model)
        self.provider_type = provider_type
        if api_base is None:
            api_base = DEFAULT_API_BASES.get(provider_type)
        self.client = AsyncOpenAI(api_key=api_key, base_url=api_base)

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal messages to OpenAI Chat Completions format.

        Handles three special message types:
        1. Assistant messages with tool_calls → message with tool_calls field
        2. Tool result messages (is_tool_result=True) → "tool" role messages
        3. Regular messages → simple role/content dicts
        """
        openai_messages: list[dict] = []

        for msg in messages:
            # Assistant message with tool calls
            if msg.role == "assistant" and msg.tool_calls:
                tool_calls_api = []
                for tc in msg.tool_calls:
                    tool_calls_api.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    })
                openai_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": tool_calls_api,
                })
                continue

            # Tool result message
            if msg.is_tool_result:
                # Guard: find the most recent assistant(tool_calls) by walking
                # backwards in the already-converted messages.  Multiple tool
                # results can follow a single assistant(tool_calls), so we
                # cannot just check openai_messages[-1] — it will be another
                # tool message for all but the first result.
                parent_assistant = None
                for m in reversed(openai_messages):
                    if m.get("role") == "assistant" and "tool_calls" in m:
                        parent_assistant = m
                        break

                if parent_assistant is None:
                    logger.warning(
                        "Dropping orphan tool result (tool_call_id=%s): "
                        "no preceding assistant message with tool_calls. "
                        "This usually means the conversation was trimmed at a "
                        "tool-call boundary.",
                        msg.tool_call_id,
                    )
                    continue

                # Verify this tool result belongs to the parent assistant
                matching = any(
                    tc["id"] == msg.tool_call_id
                    for tc in parent_assistant.get("tool_calls", [])
                )
                if not matching:
                    logger.warning(
                        "Dropping orphan tool result (tool_call_id=%s): "
                        "does not match any tool_call_id in the preceding "
                        "assistant message.  Likely trimmed.",
                        msg.tool_call_id,
                    )
                    continue

                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })
                continue

            # Regular message
            openai_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        return openai_messages

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send chat completion request."""
        openai_messages = self._convert_messages(messages)

        params: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            params["tools"] = self._convert_tools(tools)
            params["tool_choice"] = "auto"

        logger.debug("Sending {} request: model={}, messages={}", self.provider_type, self.model, len(messages))

        response = await self.client.chat.completions.create(**params)

        message = response.choices[0].message
        content = message.content
        tool_calls = []

        if message.tool_calls:
            for call in message.tool_calls:
                tool_calls.append(LLMToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=self._parse_arguments(call.function.arguments),
                ))

        logger.debug(
            "{} response: content_length={}, tool_calls={}, prompt_tokens={}, completion_tokens={}",
            self.provider_type,
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

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert tools to OpenAI function calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]

    # ------------------------------------------------------------------
    # Streaming chat
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ):
        """Send streaming chat completion request.

        Yields LLMStreamChunk objects as text arrives.
        """
        openai_messages = self._convert_messages(messages)

        params: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if tools:
            params["tools"] = self._convert_tools(tools)
            params["tool_choice"] = "auto"

        logger.debug(
            "Sending {} streaming request: model={}, messages={}",
            self.provider_type, self.model, len(messages),
        )

        # For tool calls, accumulate the arguments string fragments across chunks
        # and only parse JSON at the end.
        accumulated_tool_calls: dict[int, dict[str, Any]] = {}  # index -> {id, name, args_buffer}

        try:
            response = await self.client.chat.completions.create(**params)

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None

                # Text delta
                if delta and delta.content:
                    yield LLMStreamChunk(delta=delta.content)

                # Tool call deltas (OpenAI streams tool calls incrementally)
                if delta and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in accumulated_tool_calls:
                            accumulated_tool_calls[idx] = {
                                "id": "",
                                "name": "",
                                "args_buffer": "",
                            }
                        entry = accumulated_tool_calls[idx]
                        if tc_delta.id:
                            entry["id"] += tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                entry["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                entry["args_buffer"] += tc_delta.function.arguments

                # Check if stream is done
                if chunk.choices and chunk.choices[0].finish_reason is not None:
                    # Build final tool calls from accumulated data
                    final_tool_calls = None
                    if accumulated_tool_calls:
                        final_tool_calls = []
                        for idx in sorted(accumulated_tool_calls.keys()):
                            entry = accumulated_tool_calls[idx]
                            if entry["id"]:
                                args = {}
                                if entry["args_buffer"]:
                                    try:
                                        args = json.loads(entry["args_buffer"])
                                    except json.JSONDecodeError:
                                        logger.warning(
                                            "Failed to parse streamed tool args: {}",
                                            entry["args_buffer"][:200],
                                        )
                                final_tool_calls.append(LLMToolCall(
                                    id=entry["id"],
                                    name=entry["name"],
                                    arguments=args,
                                ))
                    yield LLMStreamChunk(
                        delta=None,
                        done=True,
                        tool_calls=final_tool_calls,
                    )
                    return

        except Exception as e:
            logger.error("{} streaming error: {}", self.provider_type, e)
            raise

    def _parse_arguments(self, arguments: str) -> dict:
        """Parse JSON arguments string."""
        try:
            result = json.loads(arguments)
            if isinstance(result, dict):
                return result
            logger.warning("Tool arguments parsed to non-dict type {}: {}", type(result).__name__, arguments)
            return {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool arguments: {}", arguments)
            return {}
