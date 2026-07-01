"""Agent integration tests — headless backend, no GUI required.

Tests exercise the real agent loop with actual LLM calls (requires API key).
Mark tests with @pytest.mark.integration to separate from unit tests.

Run:
    uv run pytest tests/test_agent_integration.py -v            # all integration tests
    uv run pytest tests/test_agent_integration.py -v -m "not integration"  # skip slow ones
"""

import tempfile
from pathlib import Path

import pytest

from autoreport.interfaces.types import (
    AgentResponse,
    AgentType,
    Error,
    StatusChange,
    ToolCallMessage,
    ToolResult,
)

from .headless import HeadlessBackend, MessageCollector

# Mark all tests in this module as integration (requires API key + network)
pytestmark = pytest.mark.integration


def _workspace():
    """Create a temp workspace (avoid tmp_path to sidestep pytest-qt permission issue)."""
    tmpdir = tempfile.mkdtemp()
    ws = Path(tmpdir) / "test_project"
    ws.mkdir(parents=True)

    for d in ["data", "data/processed", "references", "theory", "plots", "tex"]:
        (ws / d).mkdir(parents=True, exist_ok=True)

    (ws / "data" / "experiment.csv").write_text(
        "time,voltage,current\n"
        "0.0,1.0,0.5\n"
        "0.1,1.2,0.6\n"
        "0.2,1.4,0.7\n"
        "0.3,1.6,0.8\n",
        encoding="utf-8",
    )
    return ws


class TestMainAgentBasic:
    """Basic main agent interaction."""

    @pytest.mark.asyncio
    async def test_main_agent_responds(self):
        """Main agent should respond to a simple user message."""
        async with HeadlessBackend(_workspace()) as b:
            collector = MessageCollector(b.bus)
            collector.start()

            await b.send("main", "你好，请简单介绍一下你能做什么")
            responses = await collector.wait_for(AgentResponse, timeout=60, count=1)

            assert len(responses) >= 1
            text = collector.get_full_agent_text(AgentType.MAIN)
            assert len(text) > 0

    @pytest.mark.asyncio
    async def test_status_transitions(self):
        """Agent should transition through idle → thinking → idle."""
        async with HeadlessBackend(_workspace()) as b:
            collector = MessageCollector(b.bus)
            collector.start()

            await b.send("main", "你好")
            await collector.wait_for(AgentResponse, timeout=60)

            statuses = collector.status_changes
            status_values = [s.status for s in statuses]

            assert "thinking" in status_values

    @pytest.mark.asyncio
    async def test_no_errors_on_simple_message(self):
        """Simple message should not produce errors."""
        async with HeadlessBackend(_workspace()) as b:
            collector = MessageCollector(b.bus)
            collector.start()

            await b.send("main", "你好")
            await collector.wait_for(AgentResponse, timeout=60)

            assert len(collector.errors) == 0


class TestMainAgentTools:
    """Main agent tool usage."""

    @pytest.mark.asyncio
    async def test_read_file_tool(self):
        """Main agent should be able to read files via tool calls."""
        ws = _workspace()
        (ws / "data" / "test.txt").write_text("Hello from test file", encoding="utf-8")

        async with HeadlessBackend(ws) as b:
            collector = MessageCollector(b.bus)
            collector.start()

            await b.send("main", "请读取 data/test.txt 文件的内容")
            # Wait for at least one tool call
            tool_calls = await collector.wait_for(ToolCallMessage, timeout=60, count=1)

            assert len(tool_calls) >= 1
            # Should have a read tool call
            tool_names = [tc.tool_name for tc in collector.tool_calls]
            assert "read" in tool_names

            # Should have tool results
            await collector.wait_for(ToolResult, timeout=30, count=1)
            assert len(collector.tool_results) >= 1

    @pytest.mark.asyncio
    async def test_list_directory_tool(self):
        """Main agent should be able to list directories."""
        async with HeadlessBackend(_workspace()) as b:
            collector = MessageCollector(b.bus)
            collector.start()

            await b.send("main", "请列出 data/ 目录中的文件")
            await collector.wait_for(ToolCallMessage, timeout=60, count=1)

            tool_names = [tc.tool_name for tc in collector.tool_calls]
            # Should use some directory/file listing tool
            assert len(tool_names) >= 1


class TestSubAgentInteraction:
    """Sub-agent (data analysis) interaction."""

    @pytest.mark.asyncio
    async def test_data_analysis_agent_responds(self):
        """Data analysis agent should respond to direct messages."""
        async with HeadlessBackend(_workspace()) as b:
            collector = MessageCollector(b.bus)
            collector.start()

            await b.send("data_analysis", "请分析 data/experiment.csv 的数据结构")
            # Wait for the first response to confirm it reacts, then wait for
            # IDLE so get_full_agent_text captures the final non-streaming text.
            await collector.wait_for(AgentResponse, timeout=60)
            await collector.wait_for_idle(AgentType.DATA_ANALYSIS, timeout=90)

            text = collector.get_full_agent_text(AgentType.DATA_ANALYSIS)
            assert len(text) > 0

    @pytest.mark.asyncio
    async def test_data_analysis_reads_csv(self):
        """Data analysis agent should be able to read and analyze CSV files."""
        async with HeadlessBackend(_workspace()) as b:
            collector = MessageCollector(b.bus)
            collector.start()

            await b.send(
                "data_analysis",
                "读取 data/experiment.csv 文件，告诉我数据的基本统计信息",
            )
            await collector.wait_for(ToolCallMessage, timeout=60, count=1)

            # Should have tool calls (read or python_exec)
            assert len(collector.tool_calls) >= 1

            # Wait for the agent loop to finish so the final non-streaming
            # response has been published before reading the accumulated text.
            await collector.wait_for_idle(AgentType.DATA_ANALYSIS, timeout=90)
            text = collector.get_full_agent_text(AgentType.DATA_ANALYSIS)
            assert len(text) > 10


class TestAgentCoordination:
    """Main agent coordinating with sub-agents."""

    @pytest.mark.asyncio
    async def test_main_agent_can_delegate(self):
        """Main agent should be able to delegate tasks to sub-agents."""
        async with HeadlessBackend(_workspace()) as b:
            collector = MessageCollector(b.bus)
            collector.start()

            await b.send(
                "main",
                "请让数据分析 agent 分析 data/experiment.csv 文件中的电压和电流数据",
            )
            # Wait for any agent response (main or sub-agent) with generous timeout
            await collector.wait_for(AgentResponse, timeout=120)
            # Wait for MAIN to finish so its final non-streaming text is captured.
            # (Delegation may take longer, so allow a generous idle timeout.)
            await collector.wait_for_idle(AgentType.MAIN, timeout=180)

            # Should have at least a response from main or sub agent
            all_text = (
                collector.get_full_agent_text(AgentType.MAIN)
                or collector.get_full_agent_text(AgentType.DATA_ANALYSIS)
            )
            assert len(all_text) > 0, (
                f"No response text from main or data_analysis. "
                f"Messages: {[type(m).__name__ for m in collector.all_messages]}"
            )


class TestErrorHandling:
    """Error handling in agent execution."""

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        """Reading a nonexistent file should produce an error or graceful handling."""
        async with HeadlessBackend(_workspace()) as b:
            collector = MessageCollector(b.bus)
            collector.start()

            await b.send("main", "请读取 nonexistent_file.txt")
            await collector.wait_for(AgentResponse, timeout=60)
            # Wait for the loop to finish so the final (post-tool-call) text is
            # captured — the first AgentResponse is just a streaming chunk.
            await collector.wait_for_idle(AgentType.MAIN, timeout=90)

            # Agent should respond (either with error message or gracefully)
            text = collector.get_full_agent_text(AgentType.MAIN)
            assert len(text) > 0
