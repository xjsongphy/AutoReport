import pytest
from autoreport.core.loops.bus import MessageBus
from autoreport.core.tools.agent_tools import ReportTool
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
    tool = ReportTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

    result = await tool(task_id="tk1", type="reply", content="done, see plots/a.png")

    assert result["status"] == "ok"
    assert board.get_task("tk1", target_agent=AgentType.PLOTTING).status == TaskStatus.COMPLETED

    published = []
    for _ in range(2):
        msg = await bus._queue.get()
        published.append(msg)
    assert any(isinstance(m, ReportMessage) and m.report_type == "reply" for m in published)
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
    tool = ReportTool(
        bus=bus,
        agent_type=AgentType.PLOTTING,
        task_board=board,
        session_id_resolver=lambda: "plotting-session",
    )

    result = await tool(task_id="tk1", type="reply", content="done")

    assert result["status"] == "ok"
    assert board.get_task("tk1", target_agent=AgentType.PLOTTING).status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_missing_data_blocks_task(board, bus):
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    tool = ReportTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)

    result = await tool(task_id="tk1", type="missing_data", content="need data.csv")

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
    tool = ReportTool(bus=bus, agent_type=AgentType.PLOTTING, task_board=board)
    result = await tool(task_id="tk1", type="query", content="?")
    assert result["status"] == "error"
