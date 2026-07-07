"""Tests for SendToAgentTool and RespondTool — inter-agent communication."""

import asyncio

import pytest

from autoreport.core.loops.bus import MessageBus
from autoreport.core.tools.agent_tools import RespondTool, SendToAgentTool
from autoreport.core.tools.task_board import TaskBoard
from autoreport.interfaces.types import (
    AgentType,
    ReportMessage,
    TaskStatus,
    TaskUpdateMessage,
    UserMessage,
)


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def board():
    return TaskBoard()


async def _drain(bus) -> None:
    """Flush all queued messages through subscribers (tests have no process_loop)."""
    while True:
        try:
            msg = bus._queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        await bus._notify_subscribers(msg)


def _emit_report_on_dispatch(bus, board, target, report_type, summary, content):
    """Background task: when Main dispatches to `target`, drive a realistic RespondTool call.

    Uses RespondTool (not a raw ReportMessage) so the task status is updated
    exactly as in production. Drains the bus after each step so subscribers fire.
    """
    async def respond():
        rtool = RespondTool(bus=bus, agent_type=target, task_board=board)
        while True:
            msg = await asyncio.wait_for(bus._queue.get(), timeout=2)
            await bus._notify_subscribers(msg)
            if (
                isinstance(msg, UserMessage)
                and msg.agent_type == target
                and getattr(msg, "source", None) == "main_agent"
            ):
                tasks = board.get_waitlist(AgentType.MAIN)
                tid = tasks[0].task_id if tasks else None
                await rtool(task_id=tid, type=report_type, summary=summary, content=content)
                await _drain(bus)  # flush RespondTool's TaskUpdateMessage + ReportMessage
                break

    return asyncio.create_task(respond())


class TestSendToAgentTool:
    @pytest.mark.asyncio
    async def test_unknown_agent_type_returns_error(self, bus):
        tool = SendToAgentTool(bus=bus)
        result = await tool(agent_type="nonexistent", summary="test", content="test")
        assert result["status"] == "error"
        assert "Unknown agent type" in result["error"]

    @pytest.mark.asyncio
    async def test_blocking_success_on_reply_report(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)
        responder = _emit_report_on_dispatch(
            bus, board, AgentType.THEORY, "reply", "Theory completed", "theory done"
        )

        result = await tool(agent_type="theory", summary="Derive formula", content="derive formula")
        responder.cancel()

        assert result["status"] == "success"
        assert result["agent_type"] == "theory"
        assert result["summary"] == "Derive formula"
        assert result["response_summary"] == "Theory completed"
        assert result["response"] == "theory done"
        assert "task_id" in result
        # Task marked completed along the chain
        assert board.get_task(result["task_id"], target_agent=AgentType.THEORY).status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_liveness_wait_returns_already_completed_report(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        report = ReportMessage(
            agent_type=AgentType.THEORY,
            task_id="tk1",
            report_type="reply",
            summary="done",
            content="done",
        )
        future.set_result(report)

        result = await tool._await_with_liveness(future, AgentType.THEORY, loop)

        assert result is report

    @pytest.mark.asyncio
    async def test_blocking_blocked_on_missing_data_report(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)
        responder = _emit_report_on_dispatch(
            bus,
            board,
            AgentType.THEORY,
            "missing_data",
            "Need reference PDF",
            "need refs/x.pdf",
        )

        result = await tool(agent_type="theory", summary="Derive formula", content="derive formula")
        responder.cancel()

        assert result["status"] == "blocked"
        assert result["block_type"] == "missing_data"
        assert result["response_summary"] == "Need reference PDF"
        assert "need refs/x.pdf" in result["response"]
        assert board.get_task(result["task_id"], target_agent=AgentType.THEORY).status == TaskStatus.BLOCKED

    @pytest.mark.asyncio
    async def test_blocking_creates_task_with_brief(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)
        responder = _emit_report_on_dispatch(
            bus, board, AgentType.PLOTTING, "reply", "Plot done", "done"
        )

        result = await tool(
            agent_type="plotting",
            summary="Draw scatter plot",
            content="draw the scatter plot",
            task_items=[{"brief": "scatter plot"}],
        )
        responder.cancel()

        assert result["status"] == "success"
        task = board.get_task(result["task_id"], target_agent=AgentType.PLOTTING)
        assert task.brief == "scatter plot"

    @pytest.mark.asyncio
    async def test_redispatch_reuses_task_id_and_resets_in_progress(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)

        # First dispatch: sub reports missing_data -> task BLOCKED
        r1_responder = _emit_report_on_dispatch(
            bus, board, AgentType.THEORY, "missing_data", "Need x", "need x"
        )
        r1 = await tool(agent_type="theory", summary="Derive", content="derive")
        r1_responder.cancel()
        tid = r1["task_id"]
        assert board.get_task(tid, target_agent=AgentType.THEORY).status == TaskStatus.BLOCKED

        # Re-dispatch with same task_id: chain reset to IN_PROGRESS
        r2_responder = _emit_report_on_dispatch(
            bus, board, AgentType.THEORY, "reply", "Done now", "done now"
        )
        r2 = await tool(
            agent_type="theory", summary="Derive again", content="derive again", task_id=tid
        )
        r2_responder.cancel()

        assert r2["task_id"] == tid
        assert r2["status"] == "success"
        # Status went IN_PROGRESS (re-dispatch) then COMPLETED (reply)
        assert board.get_task(tid, target_agent=AgentType.THEORY).status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_redispatch_unknown_task_id_errors(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)
        result = await tool(agent_type="theory", summary="x", content="x", task_id="tk000")
        assert result["status"] == "error"
        assert "tk000" in result["error"]

    @pytest.mark.asyncio
    async def test_non_blocking_dispatches_without_waiting(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board)
        result = await tool(
            agent_type="data_analysis",
            summary="Analyze CSV",
            content="analyze data",
            blocking=False,
            task_items=[{"brief": "analyze CSV"}],
        )
        assert result["status"] == "delegated"
        assert result["agent_type"] == "data_analysis"
        assert result["blocking"] is False
        assert "task_id" in result
        task = board.get_task(result["task_id"], target_agent=AgentType.DATA_ANALYSIS)
        assert task is not None
        assert task.status == TaskStatus.IN_PROGRESS

        messages = [await asyncio.wait_for(bus._queue.get(), timeout=1) for _ in range(2)]
        started = next(msg for msg in messages if isinstance(msg, TaskUpdateMessage))
        dispatch = next(msg for msg in messages if isinstance(msg, UserMessage))

        assert started.action == "started"
        assert started.source_agent == AgentType.MAIN
        assert started.target_agent == AgentType.DATA_ANALYSIS
        assert dispatch.agent_type == AgentType.DATA_ANALYSIS
        assert dispatch.source == "main_agent"
        assert dispatch.summary == "Analyze CSV"
        assert dispatch.content == "analyze data"

    @pytest.mark.asyncio
    async def test_summary_is_required_before_task_creation(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board)

        result = await tool(
            agent_type="data_analysis",
            summary="  ",
            content="analyze data",
            blocking=False,
        )

        assert result["status"] == "error"
        assert "summary" in result["error"]
        assert board.get_todolist(AgentType.DATA_ANALYSIS) == []
        assert bus._queue.empty()

    @pytest.mark.asyncio
    async def test_timeout_when_no_report(self, bus, board):
        # timeout=0.2 -> wall_cap = 0.8s; no report emitted -> timeout
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=0.2)
        result = await tool(agent_type="plotting", summary="Draw plot", content="draw plot")
        assert result["status"] == "timeout"
        assert result["agent_type"] == "plotting"
        assert board.get_todolist(AgentType.PLOTTING) == []
        assert board.get_waitlist(AgentType.MAIN) == []


class TestTaskBriefFallback:
    """task_items brief resolution and content fallback (one task per dispatch)."""

    @pytest.mark.asyncio
    async def test_brief_key_used_when_present(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board)
        result = await tool(
            agent_type="data_analysis",
            summary="Analyze CSV",
            content="analyze the CSV data file",
            blocking=False,
            task_items=[{"brief": "Analyze CSV"}],
        )
        assert result["status"] == "delegated"
        tasks = board.get_todolist(AgentType.DATA_ANALYSIS)
        assert len(tasks) == 1
        assert tasks[0].brief == "Analyze CSV"

    @pytest.mark.asyncio
    async def test_summary_fallback_when_no_brief(self, bus, board):
        """When task_items have no 'brief', falls back to the required summary."""
        tool = SendToAgentTool(bus=bus, task_board=board)
        result = await tool(
            agent_type="theory",
            summary="Derive uncertainty formula",
            content="Derive the uncertainty formula for single-slit diffraction experiment",
            blocking=False,
            task_items=[{}],
        )
        assert result["status"] == "delegated"
        tasks = board.get_todolist(AgentType.THEORY)
        assert len(tasks) == 1
        expected = "Derive uncertainty formula"[:30]
        assert tasks[0].brief == expected


class TestRespondOrdering:
    @pytest.mark.asyncio
    async def test_respond_publishes_report_before_task_updates(self, bus, board):
        task = board.create_task(AgentType.MAIN, AgentType.THEORY, "derive")
        tool = RespondTool(bus=bus, agent_type=AgentType.THEORY, task_board=board)

        result = await tool(
            task_id=task.task_id,
            type="reply",
            summary="Derived",
            content="done",
        )

        assert result["status"] == "ok"
        first = await asyncio.wait_for(bus._queue.get(), timeout=1)
        second = await asyncio.wait_for(bus._queue.get(), timeout=1)
        assert isinstance(first, ReportMessage)
        assert second.__class__.__name__ == "TaskUpdateMessage"
