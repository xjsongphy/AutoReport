"""Anthropic Claude provider."""

import asyncio
from typing import Any

from anthropic import AsyncAnthropic
from loguru import logger

from .base import LLMProvider, LLMResponse, Message, ToolCall


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider.

    Also works with Anthropic-compatible endpoints (DeepSeek, MiniMax, etc.)
    by setting ``api_base`` to the compatible URL.
    """

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        super().__init__(api_key, api_base, model)
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=api_base,
            max_retries=0,  # Centralize retry logic in agent loop
            auth_token=api_key,  # Prevent ANTHROPIC_AUTH_TOKEN env var override
        )

    # ------------------------------------------------------------------
    # Message conversion
    # ------------------------------------------------------------------

    def _convert_messages(
        self, messages: list[Message],
    ) -> tuple[str | None, list[dict]]:
        """Convert internal messages to Anthropic API format.

        Handles three special message types:
        1. Assistant messages with tool_calls -> content blocks with type="tool_use"
        2. Tool result messages (is_tool_result=True) -> grouped into a user message
           with type="tool_result" blocks
        3. Regular messages -> simple role/content dicts

        Per Anthropic API spec:
        - tool_use blocks go in assistant messages
        - tool_result blocks go in user messages (keyed by tool_use_id)
        - Consecutive same-role messages must be merged
        - Conversation cannot end with an assistant turn
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

            # Assistant message with tool calls -> structured content blocks
            if msg.role == "assistant" and msg.tool_calls:
                content_blocks: list[dict] = []
                if msg.thinking:
                    content_blocks.append({"type": "thinking", "thinking": msg.thinking})
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

            # Tool result -> collect into pending list (grouped as one user message)
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

        # Merge consecutive same-role messages (Anthropic requirement)
        merged = self._merge_consecutive(anthropic_messages)

        # Strip empty trailing assistant turns (prefill).
        # Keep assistant turns that have actual content or tool_use blocks.
        while merged and merged[-1].get("role") == "assistant":
            content = merged[-1].get("content")
            if content:
                break
            merged.pop()

        return system_message, merged

    @staticmethod
    def _merge_consecutive(msgs: list[dict]) -> list[dict]:
        """Merge consecutive same-role messages for Anthropic API.

        Anthropic requires alternating user/assistant turns. Consecutive
        same-role messages must be collapsed into one.
        """
        merged: list[dict] = []
        for msg in msgs:
            if (
                merged
                and merged[-1].get("role") == msg.get("role")
            ):
                prev_c = merged[-1]["content"]
                cur_c = msg["content"]
                # Normalize both to lists for concatenation
                if isinstance(prev_c, str):
                    prev_c = [{"type": "text", "text": prev_c}]
                if isinstance(cur_c, str):
                    cur_c = [{"type": "text", "text": cur_c}]
                if isinstance(cur_c, list):
                    prev_c.extend(cur_c)
                merged[-1]["content"] = prev_c
            else:
                merged.append(msg)
        return merged

    # ------------------------------------------------------------------
    # Non-streaming chat
    # ------------------------------------------------------------------

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
        thinking = None

        for block in response.content:
            if block.type == "text":
                content = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))
            elif block.type == "thinking":
                thinking = block.thinking

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
            thinking=thinking,
        )

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
        from .base import LLMStreamChunk

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

        logger.debug("Sending Anthropic streaming request: model={}, messages={}", self.model, len(messages))

        idle_timeout = 90  # seconds

        try:
            async with self.client.messages.stream(**params) as stream:
                # Stream text deltas for real-time display
                stream_iter = stream.text_stream.__aiter__()
                while True:
                    try:
                        text = await asyncio.wait_for(
                            stream_iter.__anext__(),
                            timeout=idle_timeout,
                        )
                    except StopAsyncIteration:
                        break
                    yield LLMStreamChunk(delta=text)

                # After streaming completes, extract tool calls from final message
                final_message = await asyncio.wait_for(
                    stream.get_final_message(),
                    timeout=idle_timeout,
                )

            # Parse final response (outside context manager)
            final_tool_calls = []
            accumulated_text = ""
            final_thinking = None
            for block in final_message.content:
                if block.type == "tool_use":
                    final_tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    ))
                elif block.type == "text":
                    accumulated_text += block.text
                elif block.type == "thinking":
                    final_thinking = block.thinking

            yield LLMStreamChunk(
                delta=None,
                done=True,
                tool_calls=final_tool_calls or None,
                thinking=final_thinking,
            )

        except asyncio.TimeoutError:
            logger.warning("Anthropic stream stalled for >{}s", idle_timeout)
            yield LLMStreamChunk(delta=None, done=True)
        except Exception as e:
            logger.error("Anthropic streaming error: {}", str(e))
            raise

    # ------------------------------------------------------------------
    # Tool conversion
    # ------------------------------------------------------------------

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
