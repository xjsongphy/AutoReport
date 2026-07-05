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


def _emit_report_on_dispatch(bus, board, target, report_type, content):
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
                await rtool(task_id=tid, type=report_type, content=content)
                await _drain(bus)  # flush RespondTool's TaskUpdateMessage + ReportMessage
                break

    return asyncio.create_task(respond())


class TestSendToAgentTool:
    @pytest.mark.asyncio
    async def test_unknown_agent_type_returns_error(self, bus):
        tool = SendToAgentTool(bus=bus)
        result = await tool(agent_type="nonexistent", content="test")
        assert result["status"] == "error"
        assert "Unknown agent type" in result["error"]

    @pytest.mark.asyncio
    async def test_blocking_success_on_reply_report(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)
        responder = _emit_report_on_dispatch(bus, board, AgentType.THEORY, "reply", "theory done")

        result = await tool(agent_type="theory", content="derive formula")
        responder.cancel()

        assert result["status"] == "success"
        assert result["agent_type"] == "theory"
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
            content="done",
        )
        future.set_result(report)

        result = await tool._await_with_liveness(future, AgentType.THEORY, loop)

        assert result is report

    @pytest.mark.asyncio
    async def test_blocking_blocked_on_missing_data_report(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)
        responder = _emit_report_on_dispatch(bus, board, AgentType.THEORY, "missing_data", "need refs/x.pdf")

        result = await tool(agent_type="theory", content="derive formula")
        responder.cancel()

        assert result["status"] == "blocked"
        assert result["block_type"] == "missing_data"
        assert "need refs/x.pdf" in result["response"]
        assert board.get_task(result["task_id"], target_agent=AgentType.THEORY).status == TaskStatus.BLOCKED

    @pytest.mark.asyncio
    async def test_blocking_creates_task_with_brief(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)
        responder = _emit_report_on_dispatch(bus, board, AgentType.PLOTTING, "reply", "done")

        result = await tool(
            agent_type="plotting",
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
        r1_responder = _emit_report_on_dispatch(bus, board, AgentType.THEORY, "missing_data", "need x")
        r1 = await tool(agent_type="theory", content="derive")
        r1_responder.cancel()
        tid = r1["task_id"]
        assert board.get_task(tid, target_agent=AgentType.THEORY).status == TaskStatus.BLOCKED

        # Re-dispatch with same task_id: chain reset to IN_PROGRESS
        r2_responder = _emit_report_on_dispatch(bus, board, AgentType.THEORY, "reply", "done now")
        r2 = await tool(agent_type="theory", content="derive again", task_id=tid)
        r2_responder.cancel()

        assert r2["task_id"] == tid
        assert r2["status"] == "success"
        # Status went IN_PROGRESS (re-dispatch) then COMPLETED (reply)
        assert board.get_task(tid, target_agent=AgentType.THEORY).status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_redispatch_unknown_task_id_errors(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=5)
        result = await tool(agent_type="theory", content="x", task_id="tk000")
        assert result["status"] == "error"
        assert "tk000" in result["error"]

    @pytest.mark.asyncio
    async def test_non_blocking_dispatches_without_waiting(self, bus, board):
        tool = SendToAgentTool(bus=bus, task_board=board)
        result = await tool(
            agent_type="data_analysis",
            content="analyze data",
            blocking=False,
            task_items=[{"brief": "analyze CSV"}],
        )
        assert result["status"] == "delegated"
        assert result["agent_type"] == "data_analysis"
        assert result["blocking"] is False
        assert "task_id" in result
        # A dispatch UserMessage to the target was published (after a TaskUpdateMessage)
        dispatch = None
        for _ in range(5):
            msg = await asyncio.wait_for(bus._queue.get(), timeout=1)
            if isinstance(msg, UserMessage):
                dispatch = msg
                break
        assert dispatch is not None
        assert dispatch.agent_type == AgentType.DATA_ANALYSIS
        assert dispatch.source == "main_agent"

    @pytest.mark.asyncio
    async def test_timeout_when_no_report(self, bus, board):
        # timeout=0.2 -> wall_cap = 0.8s; no report emitted -> timeout
        tool = SendToAgentTool(bus=bus, task_board=board, timeout=0.2)
        result = await tool(agent_type="plotting", content="draw plot")
        assert result["status"] == "timeout"
        assert result["agent_type"] == "plotting"


class TestTaskBriefFallback:
    """task_items brief resolution and content fallback (one task per dispatch)."""

    @pytest.mark.asyncio
    async def test_brief_key_used_when_present(self, bus, board):
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
    async def test_content_fallback_when_no_brief(self, bus, board):
        """When task_items have no 'brief', falls back to the request summary (first line, ≤30 chars)."""
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
        expected = "Derive the uncertainty formula for single-slit diffraction experiment"[:30]
        assert tasks[0].brief == expected
