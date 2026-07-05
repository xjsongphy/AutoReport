import pytest
from autoreport.core.loops.bus import MessageBus
from autoreport.core.tools.agent_tools import RespondTool
from autoreport.core.tools.task_board import TaskBoard
from autoreport.interfaces.types import (
    AgentType, ReportMessage, TaskStatus, TaskUpdateMessage,
)


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def board():
    return TaskBoard()


@pytest.mark.asyncio
async def test_reply_completes_task_and_publishes_report(board, bus):
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    tool = RespondTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

    result = await tool(
        task_id="tk1",
        type="reply",
        summary="Plot complete",
        content="done, see Plots/Fig/a.png",
    )

    assert result["status"] == "ok"
    assert result["summary"] == "Plot complete"
    assert board.get_task("tk1", target_agent=AgentType.PLOTTING).status == TaskStatus.COMPLETED

    published = []
    for _ in range(2):
        msg = await bus._queue.get()
        published.append(msg)
    assert any(
        isinstance(m, ReportMessage)
        and m.report_type == "reply"
        and m.summary == "Plot complete"
        for m in published
    )
    assert any(isinstance(m, TaskUpdateMessage) and m.action == "completed" for m in published)


@pytest.mark.asyncio
async def test_reply_finds_main_dispatched_task_from_different_agent_session(board, bus):
    board.create_task(
        AgentType.MAIN,
        AgentType.PLOTTING,
        "draw",
        task_id="tk1",
        session_id="main-session",
    )
    tool = RespondTool(
        bus=bus,
        agent_type=AgentType.PLOTTING,
        task_board=board,
        session_id_resolver=lambda: "plotting-session",
    )

    result = await tool(task_id="tk1", type="reply", summary="Done", content="done")

    assert result["status"] == "ok"
    assert board.get_task("tk1", target_agent=AgentType.PLOTTING).status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_reply_is_idempotent_for_already_completed_task(board, bus):
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    board.complete_task("tk1", target_agent=AgentType.PLOTTING)
    tool = RespondTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

    result = await tool(task_id="tk1", type="reply", summary="Already done", content="done again")

    assert result["status"] == "ok"
    published = [await bus._queue.get()]
    assert any(
        isinstance(m, ReportMessage)
        and m.task_id == "tk1"
        and m.summary == "Already done"
        for m in published
    )


@pytest.mark.asyncio
async def test_missing_data_blocks_task(board, bus):
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    tool = RespondTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

    result = await tool(
        task_id="tk1",
        type="missing_data",
        summary="Need data file",
        content="need data.csv",
    )

    assert result["status"] == "ok"
    assert board.get_task("tk1", target_agent=AgentType.PLOTTING).status == TaskStatus.BLOCKED

    # Consume both messages (TaskUpdateMessage + ReportMessage)
    published = []
    for _ in range(2):
        msg = await bus._queue.get()
        published.append(msg)
    assert any(isinstance(m, ReportMessage) and m.report_type == "missing_data" for m in published)


@pytest.mark.asyncio
async def test_invalid_type_rejected(board, bus):
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    tool = RespondTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)
    result = await tool(task_id="tk1", type="query", summary="Question", content="?")
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_summary_is_required_before_task_mutation(board, bus):
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    tool = RespondTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

    result = await tool(task_id="tk1", type="reply", summary=" ", content="done")

    assert result["status"] == "error"
    assert "summary" in result["error"]
    assert board.get_task("tk1", target_agent=AgentType.PLOTTING).status == TaskStatus.PENDING
    assert bus._queue.empty()


@pytest.mark.asyncio
async def test_placeholder_summary_is_rejected_before_task_mutation(board, bus):
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    tool = RespondTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

    result = await tool(task_id="tk1", type="reply", summary="Sub to Main", content="done")

    assert result["status"] == "error"
    assert "summary" in result["error"]
    assert board.get_task("tk1", target_agent=AgentType.PLOTTING).status == TaskStatus.PENDING
    assert bus._queue.empty()


@pytest.mark.asyncio
async def test_content_is_required_before_task_mutation(board, bus):
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    tool = RespondTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

    result = await tool(task_id="tk1", type="reply", summary="Done", content=" ")

    assert result["status"] == "error"
    assert "content" in result["error"]
    assert board.get_task("tk1", target_agent=AgentType.PLOTTING).status == TaskStatus.PENDING
    assert bus._queue.empty()
