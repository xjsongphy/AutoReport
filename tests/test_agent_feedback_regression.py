"""Regression tests for AgentFeedback capture in SendToAgentTool.

Verifies:
- SendToAgentTool subscribes to AgentFeedback BEFORE publishing (race condition fix)
- AgentFeedback from the correct agent is captured
- Multiple feedback items are all accumulated
- Empty response on no-tool-call path works correctly
"""

import asyncio

import pytest

from autoreport.core.loops.bus import MessageBus
from autoreport.core.tools.agent_tools import SendToAgentTool
from autoreport.interfaces.types import (
    AgentFeedback,
    AgentResponse,
    AgentType,
    UserMessage,
)


@pytest.fixture
def bus():
    return MessageBus()


class TestAgentFeedbackCapture:
    @pytest.mark.asyncio
    async def test_single_feedback_captured(self, bus):
        """Regression: AgentFeedback from the target agent is captured."""
        tool = SendToAgentTool(bus=bus, timeout=5)

        async def respond():
            while True:
                msg = await asyncio.wait_for(bus._queue.get(), timeout=2)
                await bus._notify_subscribers(msg)
                if isinstance(msg, UserMessage) and msg.agent_type == AgentType.DATA_ANALYSIS:
                    fb = AgentFeedback(
                        agent_type=AgentType.DATA_ANALYSIS,
                        content="missing columns",
                        feedback_type="quality",
                    )
                    await bus._notify_subscribers(fb)
                    # Completion signal: system UserMessage to MAIN echoing the
                    # dispatch message_id (matches agent_loop auto-notify).
                    await bus._notify_subscribers(UserMessage(
                        content="analysis complete",
                        agent_type=AgentType.MAIN,
                        source="system",
                        message_id=msg.message_id,
                    ))
                    break

        task = asyncio.create_task(respond())
        result = await tool(agent_type="data_analysis", content="analyze")
        task.cancel()

        assert result["status"] == "success"
        assert result["feedback"][0]["content"] == "missing columns"
        assert result["feedback"][0]["type"] == "quality"

    @pytest.mark.asyncio
    async def test_multiple_feedback_captured(self, bus):
        """Multiple AgentFeedback messages are all captured."""
        tool = SendToAgentTool(bus=bus, timeout=5)

        async def respond():
            while True:
                msg = await asyncio.wait_for(bus._queue.get(), timeout=2)
                await bus._notify_subscribers(msg)
                if isinstance(msg, UserMessage) and msg.agent_type == AgentType.PLOTTING:
                    for content in ["issue 1", "issue 2", "issue 3"]:
                        await bus._notify_subscribers(AgentFeedback(
                            agent_type=AgentType.PLOTTING,
                            content=content,
                            feedback_type="quality",
                        ))
                    await bus._notify_subscribers(UserMessage(
                        content="done",
                        agent_type=AgentType.MAIN,
                        source="system",
                        message_id=msg.message_id,
                    ))
                    break

        task = asyncio.create_task(respond())
        result = await tool(agent_type="plotting", content="plot")
        task.cancel()

        assert len(result["feedback"]) == 3

    @pytest.mark.asyncio
    async def test_feedback_from_wrong_agent_ignored(self, bus):
        """AgentFeedback from a different agent is not captured."""
        tool = SendToAgentTool(bus=bus, timeout=5)

        async def respond():
            while True:
                msg = await asyncio.wait_for(bus._queue.get(), timeout=2)
                await bus._notify_subscribers(msg)
                if isinstance(msg, UserMessage) and msg.agent_type == AgentType.THEORY:
                    # Feedback from wrong agent
                    await bus._notify_subscribers(AgentFeedback(
                        agent_type=AgentType.PLOTTING,
                        content="not for you",
                        feedback_type="quality",
                    ))
                    await bus._notify_subscribers(UserMessage(
                        content="theory done",
                        agent_type=AgentType.MAIN,
                        source="system",
                        message_id=msg.message_id,
                    ))
                    break

        task = asyncio.create_task(respond())
        result = await tool(agent_type="theory", content="derive")
        task.cancel()

        assert result["status"] == "success"
        assert "feedback" not in result or len(result.get("feedback", [])) == 0


class TestEmptyResponsePath:
    @pytest.mark.asyncio
    async def test_empty_content_response(self, bus):
        """Regression: tool call path with empty final content doesn't crash."""
        tool = SendToAgentTool(bus=bus, timeout=5)

        async def respond():
            while True:
                msg = await asyncio.wait_for(bus._queue.get(), timeout=2)
                await bus._notify_subscribers(msg)
                if isinstance(msg, UserMessage):
                    await bus._notify_subscribers(UserMessage(
                        content="",  # Empty content
                        agent_type=AgentType.MAIN,
                        source="system",
                        message_id=msg.message_id,
                    ))
                    break

        task = asyncio.create_task(respond())
        result = await tool(agent_type="theory", content="test")
        task.cancel()

        # Should not crash, empty string is valid
        assert result["status"] == "success"
        assert result["response"] == ""

    @pytest.mark.asyncio
    async def test_streaming_chunks_ignored(self, bus):
        """Streaming chunks should not resolve the future — only the system
        completion UserMessage does. AgentResponse messages (streaming or not)
        are no longer the resolution signal after the loop-completion refactor.
        """
        tool = SendToAgentTool(bus=bus, timeout=5)

        async def respond():
            while True:
                msg = await asyncio.wait_for(bus._queue.get(), timeout=2)
                await bus._notify_subscribers(msg)
                if isinstance(msg, UserMessage) and msg.agent_type == AgentType.REPORT:
                    # Streaming chunks must NOT resolve the future.
                    await bus._notify_subscribers(AgentResponse(
                        agent_type=AgentType.REPORT,
                        content="chunk",
                        streaming=True,
                    ))
                    # Non-streaming AgentResponse also no longer resolves —
                    # only the system UserMessage to MAIN does.
                    await bus._notify_subscribers(AgentResponse(
                        agent_type=AgentType.REPORT,
                        content="ignored",
                        streaming=False,
                    ))
                    # Real completion signal.
                    await bus._notify_subscribers(UserMessage(
                        content="final response",
                        agent_type=AgentType.MAIN,
                        source="system",
                        message_id=msg.message_id,
                    ))
                    break

        task = asyncio.create_task(respond())
        result = await tool(agent_type="report", content="compile")
        task.cancel()

        assert result["response"] == "final response"
