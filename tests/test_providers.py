"""Tests for LLM provider base classes, conversion, and factory."""

from unittest.mock import MagicMock

import pytest

from autoreport.core.providers.base import LLMProvider, LLMResponse, LLMToolCall, Message
from autoreport.core.providers.defaults import DEFAULT_MODELS
from autoreport.core.providers.factory import (
    ProviderFactory,
    ProviderManager,
)
from autoreport.core.providers.openai_provider import OpenAICompatProvider

# ── Base dataclass tests ────────────────────────────────────────────────


def test_tool_call_dataclass():
    tc = LLMToolCall(id="call_1", name="read", arguments={"path": "test.txt"})
    assert tc.id == "call_1"
    assert tc.name == "read"
    assert tc.arguments["path"] == "test.txt"


def test_message_dataclass():
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"
    assert msg.tool_calls is None
    assert msg.tool_call_id is None
    assert msg.is_tool_result is False


def test_message_with_tool_calls():
    tc = LLMToolCall(id="call_1", name="read", arguments={})
    msg = Message(role="assistant", content="", tool_calls=[tc])
    assert msg.tool_calls is not None
    assert len(msg.tool_calls) == 1


def test_message_tool_result():
    msg = Message(role="tool", content="result", tool_call_id="call_1", is_tool_result=True)
    assert msg.is_tool_result is True


def test_llm_response():
    resp = LLMResponse(content="Hello!", tool_calls=[], usage={"input_tokens": 10, "output_tokens": 5})
    assert resp.content == "Hello!"
    assert resp.usage["input_tokens"] == 10


def test_llm_response_defaults():
    resp = LLMResponse(content="Hi")
    assert resp.tool_calls == []
    assert resp.usage is None


# ── Anthropic provider conversion tests ─────────────────────────────────


def test_anthropic_convert_simple_messages():
    from autoreport.core.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    messages = [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi there!"),
    ]

    system, anthropic_msgs = provider._convert_messages(messages)

    assert system == "You are helpful."
    assert len(anthropic_msgs) == 2
    assert anthropic_msgs[0]["role"] == "user"
    assert anthropic_msgs[1]["role"] == "assistant"


def test_anthropic_convert_tool_calls():
    from autoreport.core.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    tc = LLMToolCall(id="call_1", name="read", arguments={"path": "test.txt"})
    messages = [
        Message(role="user", content="Read file"),
        Message(role="assistant", content="", tool_calls=[tc]),
        Message(role="tool", content="file content", tool_call_id="call_1", is_tool_result=True),
    ]

    _, anthropic_msgs = provider._convert_messages(messages)

    # User message comes first
    assert anthropic_msgs[0]["role"] == "user"
    assert anthropic_msgs[0]["content"] == "Read file"

    # Assistant with tool_use
    assistant_msg = anthropic_msgs[1]
    assert assistant_msg["role"] == "assistant"
    assert any(b["type"] == "tool_use" for b in assistant_msg["content"])

    # Tool result grouped into user message
    tool_result_msg = anthropic_msgs[2]
    assert tool_result_msg["role"] == "user"
    assert any(b["type"] == "tool_result" for b in tool_result_msg["content"])


def test_anthropic_convert_never_emits_null_content():
    from autoreport.core.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    messages = [
        Message(role="user", content=None),  # type: ignore[arg-type]
        Message(role="assistant", content="ok"),
    ]

    _, anthropic_msgs = provider._convert_messages(messages)

    assert anthropic_msgs[0]["content"] == ""
    assert anthropic_msgs[1]["content"] == "ok"


def test_anthropic_convert_merges_consecutive_text_as_string():
    """Consecutive same-role *text* messages must merge into a plain string.

    Native Anthropic accepts array-form content, but Anthropic-compatible
    endpoints (DeepSeek, MiniMax) reject a text-only array with
    ``invalid type: null, expected a string``. The merge must collapse
    text-only results back to a string while keeping tool blocks as an array.
    """
    from autoreport.core.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    messages = [
        Message(role="user", content="first turn"),
        Message(role="assistant", content="reply one"),
        Message(role="assistant", content="reply two"),
        Message(role="user", content="second turn"),
        Message(role="user", content="third turn"),
    ]

    _, anthropic_msgs = provider._convert_messages(messages)

    # user, assistant(merged), user(merged) — alternating, 3 turns total.
    assert [m["role"] for m in anthropic_msgs] == ["user", "assistant", "user"]
    # Merged text content is a plain string, not a list of text blocks.
    assert isinstance(anthropic_msgs[1]["content"], str)
    assert anthropic_msgs[1]["content"] == "reply one\nreply two"
    assert isinstance(anthropic_msgs[2]["content"], str)
    assert anthropic_msgs[2]["content"] == "second turn\nthird turn"


def test_anthropic_convert_merges_text_with_tool_use_keeps_array():
    """A merged turn that still carries a tool_use block must stay a list."""
    from autoreport.core.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    tc = LLMToolCall(id="call_1", name="read", arguments={"path": "x"})
    messages = [
        Message(role="user", content="hi"),
        Message(role="assistant", content="thinking", tool_calls=[tc]),
        Message(role="assistant", content="more text"),
    ]

    _, anthropic_msgs = provider._convert_messages(messages)

    assistant = anthropic_msgs[1]
    assert assistant["role"] == "assistant"
    assert isinstance(assistant["content"], list)
    types = [b["type"] for b in assistant["content"]]
    assert "tool_use" in types
    assert types.count("text") == 2


def test_anthropic_convert_drops_thinking_blocks_on_replay():
    """Thinking blocks must NOT be replayed — the streaming path loses the
    API's encrypted ``signature``, so re-sending a fabricated thinking block
    makes the next request fail to deserialize (root cause of the
    "messages[0].content: invalid type: null" error on the second turn)."""
    from autoreport.core.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    tc = LLMToolCall(id="call_1", name="read", arguments={"path": "x"})
    messages = [
        Message(role="user", content="hi"),
        Message(
            role="assistant",
            content="",
            thinking="reasoning trace",
            tool_calls=[tc],
        ),
        Message(role="user", content="r", tool_call_id="call_1", is_tool_result=True),
        Message(role="user", content="next turn"),
    ]

    _, anthropic_msgs = provider._convert_messages(messages)

    assistant_msg = anthropic_msgs[1]
    assert assistant_msg["role"] == "assistant"
    # The assistant turn still carries its tool_use, but no thinking block.
    types = [b["type"] for b in assistant_msg["content"]]
    assert "thinking" not in types
    assert "tool_use" in types
    # No block anywhere carries a thinking type.
    for m in anthropic_msgs:
        if isinstance(m["content"], list):
            assert not any(b.get("type") == "thinking" for b in m["content"])


def test_anthropic_convert_flattens_historical_tool_replay_for_compatible_endpoints():
    """Historical tool_use/tool_result pairs should not be replayed as blocks.

    Anthropic-compatible endpoints accept structured tool exchange during the
    immediate follow-up round, but re-sending that old structured pair on a
    later user turn can fail. Once the assistant has already produced a normal
    follow-up reply, replay the plain-text assistant turns only.
    """
    from autoreport.core.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._supports_cache = False
    tc = LLMToolCall(id="call_1", name="send_to_agent", arguments={"agent_type": "theory"})
    messages = [
        Message(role="user", content="dispatch task"),
        Message(role="assistant", content="", tool_calls=[tc]),
        Message(
            role="user",
            content="{'status': 'success', 'response': 'done'}",
            tool_call_id="call_1",
            is_tool_result=True,
        ),
        Message(role="assistant", content="task completed"),
        Message(role="user", content="next turn"),
    ]

    _, anthropic_msgs = provider._convert_messages(messages)

    assert [m["role"] for m in anthropic_msgs] == ["user", "assistant", "user"]
    assert anthropic_msgs[0]["content"] == "dispatch task"
    assert anthropic_msgs[1]["content"] == "task completed"
    assert anthropic_msgs[2]["content"] == "next turn"


def test_anthropic_convert_tools():
    from autoreport.core.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    tools = [{"name": "read", "description": "Read a file or inspect a directory", "input_schema": {"type": "object"}}]

    result = provider._convert_tools(tools)
    assert len(result) == 1
    assert result[0]["name"] == "read"
    assert "input_schema" in result[0]


# ── OpenAI provider conversion tests ────────────────────────────────────


def test_openai_convert_simple_messages():
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    messages = [
        Message(role="system", content="System prompt"),
        Message(role="user", content="Hello"),
    ]

    result = provider._convert_messages(messages)
    assert len(result) == 2
    assert result[0] == {"role": "system", "content": "System prompt"}
    assert result[1] == {"role": "user", "content": "Hello"}


def test_openai_convert_tool_calls():
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    tc = LLMToolCall(id="call_1", name="read", arguments={"path": "test.txt"})
    messages = [
        Message(role="user", content="Read"),
        Message(role="assistant", content="", tool_calls=[tc]),
        Message(role="tool", content="data", tool_call_id="call_1", is_tool_result=True),
    ]

    result = provider._convert_messages(messages)

    # Assistant with tool_calls field
    assistant_msg = result[1]
    assert assistant_msg["role"] == "assistant"
    assert "tool_calls" in assistant_msg
    assert assistant_msg["tool_calls"][0]["function"]["name"] == "read"

    # Tool result
    tool_msg = result[2]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "call_1"


def test_openai_convert_tools():
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    tools = [{"name": "exec", "description": "Execute", "input_schema": {"type": "object"}}]

    result = provider._convert_tools(tools)
    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "exec"


def test_openai_parse_arguments():
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    assert provider._parse_arguments('{"path": "test.txt"}') == {"path": "test.txt"}


def test_openai_parse_arguments_invalid():
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    assert provider._parse_arguments("invalid json") == {}


# ── ProviderFactory tests ───────────────────────────────────────────────


def test_factory_unknown_type():
    with pytest.raises(ValueError, match="Unknown provider type"):
        ProviderFactory.create_provider("unknown_type", "key")


def test_factory_default_models():
    assert "anthropic" in DEFAULT_MODELS
    assert "openai" in DEFAULT_MODELS
    assert "deepseek" in DEFAULT_MODELS


# ── ProviderManager tests ───────────────────────────────────────────────


def test_provider_manager_register():
    manager = ProviderManager()
    mock_provider = MagicMock(spec=LLMProvider)
    manager.register_provider("test", mock_provider)
    assert manager.has_provider("test")


def test_provider_manager_first_registered_becomes_active():
    manager = ProviderManager()
    mock1 = MagicMock(spec=LLMProvider)
    mock2 = MagicMock(spec=LLMProvider)

    manager.register_provider("first", mock1)
    manager.register_provider("second", mock2)

    assert manager.get_active_provider() is mock1


def test_provider_manager_set_active():
    manager = ProviderManager()
    mock1 = MagicMock(spec=LLMProvider)
    mock2 = MagicMock(spec=LLMProvider)

    manager.register_provider("a", mock1)
    manager.register_provider("b", mock2)
    manager.set_active_provider("b")

    assert manager.get_active_provider() is mock2


def test_provider_manager_set_active_unknown():
    manager = ProviderManager()
    with pytest.raises(ValueError, match="Provider not registered"):
        manager.set_active_provider("nonexistent")


def test_provider_manager_no_active():
    manager = ProviderManager()
    with pytest.raises(ValueError, match="No active provider"):
        manager.get_active_provider()


def test_provider_manager_get_available():
    manager = ProviderManager()
    manager.register_provider("a", MagicMock(spec=LLMProvider))
    manager.register_provider("b", MagicMock(spec=LLMProvider))

    available = manager.get_available_providers()
    assert "a" in available
    assert "b" in available
