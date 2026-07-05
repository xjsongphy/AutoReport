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
    TaskUpdateMessage,
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
    async def test_non_blocking_requires_task_items_with_board(self, bus):
        board = TaskBoard()
        tool = SendToAgentTool(bus=bus, task_board=board)
        result = await tool(
            agent_type="data_analysis",
            content="analyze data",
            blocking=False,
        )
        assert result["status"] == "error"
        assert "requires task_items" in result["error"]

    @pytest.mark.asyncio
    async def test_non_blocking_with_task_items_delegates(self, bus):
        board = TaskBoard()
        tool = SendToAgentTool(bus=bus, task_board=board)
        result = await tool(
            agent_type="data_analysis",
            content="analyze data",
            blocking=False,
            task_items=[{"brief": "analyze CSV"}],
        )
        assert result["status"] == "delegated"
        assert result["agent_type"] == "data_analysis"
        assert "task_ids" in result

    @pytest.mark.asyncio
    async def test_task_items_creates_tracked_tasks(self, bus):
        board = TaskBoard()
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=1)
        result = await tool(
            agent_type="plotting",
            content="create scatter",
            blocking=False,
            task_items=[
                {"brief": "scatter plot"},
                {"brief": "histogram"},
            ],
        )
        assert "task_ids" in result
        assert len(result["task_ids"]) == 2
        tasks = board.get_todolist(AgentType.PLOTTING)
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_blocking_with_task_items_rejected(self, bus):
        board = TaskBoard()
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=0.2)
        result = await tool(
            agent_type="report",
            content="compile report",
            task_items=[{"brief": "final report"}],
        )
        assert result["status"] == "error"
        assert "does not support task_items" in result["error"]
        # No task created
        tasks = board.get_todolist(AgentType.REPORT)
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_non_blocking_without_board_ignored(self, bus):
        tool = SendToAgentTool(bus=bus, timeout=0.2)
        result = await tool(
            agent_type="theory",
            content="test",
            blocking=False,
            task_items=[{"brief": "no board to track"}],
        )
        # Without task_board, task_items are ignored and allowed
        assert result["status"] == "delegated"
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
            task_brief="derive formulas for overlay",
        )
        assert result["status"] == "reported"
        assert "task_id" in result
        assert result["requested_target"] == "theory"
        tasks = board.get_todolist(AgentType.MAIN)
        assert len(tasks) == 1
        assert tasks[0].brief == "derive formulas for overlay"

    @pytest.mark.asyncio
    async def test_request_task_auto_dispatches_child_task(self, bus):
        board = TaskBoard()
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

        result = await tool(
            content="missing theory curves",
            issue_type="missing_data",
            request_task_for="theory",
            task_brief="theory overlay",
            task_message="derive formulas for overlay",
        )

        assert result["status"] == "reported"
        assert result["requested_target"] == "theory"
        assert "task_id" in result
        assert "dispatched_task_id" in result

        parent = board.get_task(result["task_id"], target_agent=AgentType.MAIN)
        child = board.get_task(result["dispatched_task_id"], target_agent=AgentType.THEORY)
        assert parent is not None
        assert child is not None
        assert parent.source_agent == AgentType.PLOTTING
        assert parent.target_agent == AgentType.MAIN
        assert child.source_agent == AgentType.MAIN
        assert child.target_agent == AgentType.THEORY
        assert child.task_id == parent.task_id
        assert child.brief == "theory overlay"

        queued = [await asyncio.wait_for(bus._queue.get(), timeout=1) for _ in range(4)]
        task_updates = [msg for msg in queued if isinstance(msg, TaskUpdateMessage)]
        user_messages = [msg for msg in queued if isinstance(msg, UserMessage)]
        feedbacks = [msg for msg in queued if isinstance(msg, AgentFeedback)]

        assert len(task_updates) == 2
        assert len(user_messages) == 1
        assert len(feedbacks) == 1
        assert user_messages[0].agent_type == AgentType.THEORY
        assert user_messages[0].source == "main_agent"
        assert "derive formulas for overlay" in user_messages[0].content
        assert "missing theory curves" in user_messages[0].content

    @pytest.mark.asyncio
    async def test_request_task_invalid_target_defaults_to_main(self, bus):
        board = TaskBoard()
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)
        result = await tool(
            content="test",
            request_task_for="nonexistent_agent",
            task_brief="something",
        )
        assert "task_id" in result
        assert "dispatched_task_id" not in result
        tasks = board.get_todolist(AgentType.MAIN)
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_no_task_without_board(self, bus):
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.THEORY)
        result = await tool(
            content="test",
            request_task_for="main",
            task_brief="help",
        )
        assert "task_id" not in result

    @pytest.mark.asyncio
    async def test_no_task_without_brief(self, bus):
        board = TaskBoard()
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.THEORY, task_board=board)
        result = await tool(
            content="test",
            request_task_for="main",
            task_brief="",
        )
        assert "task_id" not in result


class TestTaskBriefFallback:
    """task_items brief key resolution and content fallback."""

    @pytest.mark.asyncio
    async def test_brief_key_used_when_present(self, bus):
        """When task_items contain 'brief', that value is used for the task."""
        board = TaskBoard()
        tool = SendToAgentTool(bus=bus, task_board=board)
        result = await tool(
            agent_type="data_analysis",
            content="analyze the CSV data file",
            blocking=False,
            task_items=[{"brief": "Analyze CSV"}],
        )
        assert result["status"] == "delegated"
        tasks = board.get_todolist(AgentType.DATA_ANALYSIS)
        assert len(tasks) == 1
        assert tasks[0].brief == "Analyze CSV"

    @pytest.mark.asyncio
    async def test_content_fallback_when_no_brief(self, bus):
        """When task_items have no 'brief', falls back to content[:80]."""
        board = TaskBoard()
        tool = SendToAgentTool(bus=bus, task_board=board)
        result = await tool(
            agent_type="theory",
            content="Derive the uncertainty formula for single-slit diffraction experiment",
            blocking=False,
            task_items=[{}],
        )
        assert result["status"] == "delegated"
        tasks = board.get_todolist(AgentType.THEORY)
        assert len(tasks) == 1
        expected = "Derive the uncertainty formula for single-slit diffraction experiment"[:80]
        assert tasks[0].brief == expected


class TestReportIssueTaskMessage:
    """ReportIssueTool task_message merging and fallback behavior."""

    @pytest.mark.asyncio
    async def test_task_message_merges_with_content(self, bus):
        """When task_message differs from content, both are included in the dispatched message."""
        board = TaskBoard()
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

        result = await tool(
            content="the theory curves are wrong",
            issue_type="quality",
            request_task_for="theory",
            task_brief="fix theory curves",
            task_message="please rederive the diffraction formula",
        )

        assert result["status"] == "reported"
        assert "dispatched_task_id" in result

        # Drain the bus queue to find the UserMessage dispatched to theory
        queued = [await asyncio.wait_for(bus._queue.get(), timeout=1) for _ in range(4)]
        user_messages = [msg for msg in queued if isinstance(msg, UserMessage)]
        assert len(user_messages) == 1
        assert user_messages[0].agent_type == AgentType.THEORY
        # task_message is used as the primary dispatch content
        assert "please rederive the diffraction formula" in user_messages[0].content
        # content is merged as context when it differs from the dispatch content
        assert "the theory curves are wrong" in user_messages[0].content

    @pytest.mark.asyncio
    async def test_task_message_empty_falls_back_to_brief(self, bus):
        """When task_message is empty/None, the dispatch uses task_brief as content."""
        board = TaskBoard()
        tool = ReportIssueTool(bus=bus, agent_type=AgentType.DATA_ANALYSIS, task_board=board)

        result = await tool(
            content="raw data has outliers",
            issue_type="quality",
            request_task_for="plotting",
            task_brief="create cleaned scatter plot",
            task_message=None,
        )

        assert result["status"] == "reported"
        assert "dispatched_task_id" in result

        # Drain the bus queue
        queued = [await asyncio.wait_for(bus._queue.get(), timeout=1) for _ in range(4)]
        user_messages = [msg for msg in queued if isinstance(msg, UserMessage)]
        assert len(user_messages) == 1
        assert user_messages[0].agent_type == AgentType.PLOTTING
        # Falls back to task_brief when task_message is empty
        assert "create cleaned scatter plot" in user_messages[0].content
        # Content is merged as context since it differs
        assert "raw data has outliers" in user_messages[0].content
