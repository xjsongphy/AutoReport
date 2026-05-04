"""Tests for context auto-compaction — _estimate_tokens and _trim_messages_to_budget."""

import pytest

from autoreport.core.loops.agent_loop import _estimate_tokens, _trim_messages_to_budget
from autoreport.core.providers.base import Message as LLMMessage


class TestEstimateTokens:
    def test_empty_messages(self):
        assert _estimate_tokens([]) == 0

    def test_single_message_overhead(self):
        msgs = [LLMMessage(role="user", content="")]
        # Each message has 4 tokens overhead
        assert _estimate_tokens(msgs) == 4

    def test_text_content_estimation(self):
        content = "a" * 100
        msgs = [LLMMessage(role="user", content=content)]
        # 4 overhead + 100 * 0.3 = 34
        assert _estimate_tokens(msgs) == 34

    def test_tool_calls_add_overhead(self):
        from autoreport.core.providers.base import ToolCall
        tc = ToolCall(id="call_1", name="read_file", arguments={"path": "test.txt"})
        msgs = [LLMMessage(role="assistant", content="", tool_calls=[tc])]
        tokens = _estimate_tokens(msgs)
        # 4 overhead + 20 tool call overhead + arguments tokens
        assert tokens >= 24

    def test_thinking_adds_tokens(self):
        msgs = [LLMMessage(role="assistant", content="", thinking="thinking text")]
        tokens = _estimate_tokens(msgs)
        assert tokens > 4

    def test_multiple_messages(self):
        msgs = [
            LLMMessage(role="system", content="system prompt"),
            LLMMessage(role="user", content="hello"),
            LLMMessage(role="assistant", content="hi"),
        ]
        tokens = _estimate_tokens(msgs)
        assert tokens > 12  # At least 3 * 4 overhead


class TestTrimMessagesToBudget:
    def test_no_trimming_when_within_budget(self):
        msgs = [
            LLMMessage(role="system", content="system"),
            LLMMessage(role="user", content="hello"),
        ]
        result = _trim_messages_to_budget(msgs, context_window=100000, max_output=4096)
        assert result == msgs

    def test_trims_old_messages(self):
        system = LLMMessage(role="system", content="system prompt")
        old = LLMMessage(role="user", content="a" * 10000)
        recent = LLMMessage(role="user", content="recent question")

        msgs = [system, old, recent]
        # Force compaction with small budget
        result = _trim_messages_to_budget(msgs, context_window=2000, max_output=256)
        assert len(result) < len(msgs)
        # System message always preserved
        assert result[0] == system
        # Recent message preserved
        assert recent in result

    def test_preserves_system_message(self):
        system = LLMMessage(role="system", content="system")
        msgs = [system] + [
            LLMMessage(role="user", content="a" * 5000)
            for _ in range(20)
        ]
        result = _trim_messages_to_budget(msgs, context_window=1000, max_output=256)
        assert result[0] == system

    def test_returns_same_list_if_no_compaction_needed(self):
        msgs = [
            LLMMessage(role="system", content="system"),
            LLMMessage(role="user", content="short"),
        ]
        result = _trim_messages_to_budget(msgs, context_window=128000)
        assert result is msgs

    def test_only_system_survives_extreme_compaction(self):
        system = LLMMessage(role="system", content="system")
        msgs = [system, LLMMessage(role="user", content="a" * 100000)]
        result = _trim_messages_to_budget(msgs, context_window=500, max_output=100)
        assert result[0] == system
