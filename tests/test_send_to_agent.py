"""Tests for SendToAgentTool and ReportIssueTool — inter-agent communication."""

import asyncio

import pytest

from autoreport.core.loops.bus import MessageBus
from autoreport.core.tools.agent_tools import ReportIssueTool, SendToAgentTool
from autoreport.core.tools.task_board import TaskBoard
from autoreport.interfaces.types import (
    AgentFeedback,
    AgentResponse,
    AgentType,
    UserMessage,
)


@pytest.fixture
def bus():
    return MessageBus()


class TestSendToAgentTool:
    @pytest.mark.asyncio
    async def test_unknown_agent_type_returns_error(self, bus):
        tool = SendToAgentTool(bus=bus)
        result = await tool(agent_type="nonexistent", content="test")
        assert result["status"] == "error"
        assert "Unknown agent type" in result["error"]

    @pytest.mark.asyncio
    async def test_blocking_success(self, bus):
        tool = SendToAgentTool(bus=bus, timeout=5)

        async def respond():
            while True:
                msg = await asyncio.wait_for(bus._queue.get(), timeout=2)
                await bus._notify_subscribers(msg)
                if isinstance(msg, UserMessage) and msg.agent_type == AgentType.THEORY:
                    resp = AgentResponse(
                        agent_type=AgentType.THEORY,
                        content="theory done",
                    )
                    await bus._notify_subscribers(resp)
                    break

        task = asyncio.create_task(respond())
        result = await tool(agent_type="theory", content="derive formula")
        task.cancel()

        assert result["status"] == "success"
        assert result["agent_type"] == "theory"
        assert result["response"] == "theory done"

    @pytest.mark.asyncio
    async def test_timeout_when_no_response(self, bus):
        tool = SendToAgentTool(bus=bus, timeout=0.2)
        result = await tool(agent_type="plotting", content="draw plot")
        assert result["status"] == "timeout"
        assert result["agent_type"] == "plotting"

    @pytest.mark.asyncio
    async def test_captures_feedback(self, bus):
        tool = SendToAgentTool(bus=bus, timeout=5)

        async def respond_with_feedback():
            while True:
                msg = await asyncio.wait_for(bus._queue.get(), timeout=2)
                await bus._notify_subscribers(msg)
                if isinstance(msg, UserMessage) and msg.agent_type == AgentType.THEORY:
                    fb = AgentFeedback(
                        agent_type=AgentType.THEORY,
                        content="need more data",
                        feedback_type="quality",
                    )
                    await bus._notify_subscribers(fb)
                    resp = AgentResponse(
                        agent_type=AgentType.THEORY,
                        content="done",
                    )
                    await bus._notify_subscribers(resp)
                    break

        task = asyncio.create_task(respond_with_feedback())
        result = await tool(agent_type="theory", content="derive")
        task.cancel()

        assert result["status"] == "success"
        assert "feedback" in result
        assert len(result["feedback"]) == 1
        assert result["feedback"][0]["type"] == "quality"

    @pytest.mark.asyncio
    async def test_non_blocking_dispatches_immediately(self, bus):
        tool = SendToAgentTool(bus=bus)
        result = await tool(
            agent_type="data_analysis",
            content="analyze data",
            blocking=False,
        )
        assert result["status"] == "delegated"
        assert result["agent_type"] == "data_analysis"

    @pytest.mark.asyncio
    async def test_task_items_creates_tracked_tasks(self, bus):
        board = TaskBoard()
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=1)
        result = await tool(
            agent_type="plotting",
            content="create scatter",
            blocking=False,
            task_items=[
                {"description": "scatter plot"},
                {"description": "histogram"},
            ],
        )
        assert "task_ids" in result
        assert len(result["task_ids"]) == 2
        tasks = board.get_todolist(AgentType.PLOTTING)
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_blocking_with_task_items_creates_on_board(self, bus):
        board = TaskBoard()
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=0.2)
        result = await tool(
            agent_type="report",
            content="compile report",
            task_items=[{"description": "final report"}],
        )
        assert result["status"] == "timeout"
        # Task is created on board regardless of timeout
        tasks = board.get_todolist(AgentType.REPORT)
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_no_task_items_without_board(self, bus):
        tool = SendToAgentTool(bus=bus, timeout=0.2)
        result = await tool(
            agent_type="theory",
            content="test",
            task_items=[{"description": "should be ignored"}],
        )
        assert "task_ids" not in result


class TestReportIssueTool:
    @pytest.mark.asyncio
    async def test_reports_issue_to_bus(self, bus):
        received = []
        bus.subscribe(AgentFeedback, lambda msg: received.append(msg))

        tool = ReportIssueTool(bus=bus, agent_type=AgentType.DATA_ANALYSIS)
        result = await tool(content="raw data is corrupted")

        assert result["status"] == "reported"
        assert result["agent_type"] == "data_analysis"
        assert result["issue_type"] == "missing_data"

        msg = await asyncio.wait_for(bus._queue.get(), timeout=1)
        await bus._notify_subscribers(msg)
        assert len(received) == 1
        assert received[0].content == "raw data is corrupted"

    @pytest.mark.asyncio
    async def test_invalid_issue_type_defaults(self, bus):
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.THEORY)
        result = await tool(content="test", issue_type="invalid_type")
        assert result["issue_type"] == "missing_data"

    @pytest.mark.asyncio
    async def test_all_valid_issue_types(self, bus):
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.PLOTTING)
        for itype in ("missing_data", "quality", "query"):
            result = await tool(content="test", issue_type=itype)
            assert result["issue_type"] == itype

    @pytest.mark.asyncio
    async def test_request_task_creates_task(self, bus):
        board = TaskBoard()
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)
        result = await tool(
            content="missing theory curves",
            issue_type="missing_data",
            request_task_for="theory",
            task_description="derive formulas for overlay",
        )
        assert result["status"] == "reported"
        assert "task_id" in result
        assert result["requested_target"] == "theory"
        tasks = board.get_todolist(AgentType.THEORY)
        assert len(tasks) == 1
        assert tasks[0].description == "derive formulas for overlay"

    @pytest.mark.asyncio
    async def test_request_task_invalid_target_defaults_to_main(self, bus):
        board = TaskBoard()
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)
        result = await tool(
            content="test",
            request_task_for="nonexistent_agent",
            task_description="something",
        )
        assert "task_id" in result
        tasks = board.get_todolist(AgentType.MAIN)
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_no_task_without_board(self, bus):
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.THEORY)
        result = await tool(
            content="test",
            request_task_for="main",
            task_description="help",
        )
        assert "task_id" not in result

    @pytest.mark.asyncio
    async def test_no_task_without_description(self, bus):
        board = TaskBoard()
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.THEORY, task_board=board)
        result = await tool(
            content="test",
            request_task_for="main",
            task_description=None,
        )
        assert "task_id" not in result
