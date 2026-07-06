import asyncio

import pytest

from autoreport.core.loops.bus import MessageBus
from autoreport.core.tools.agent_tools import SendToAgentTool
from autoreport.core.tools.task_board import TaskBoard
from autoreport.interfaces.types import AgentType, TaskStatus, TaskUpdateMessage, UserMessage


@pytest.mark.asyncio
async def test_nonblocking_send_marks_main_task_in_progress_and_publishes_started():
    board = TaskBoard()
    bus = MessageBus()
    tool = SendToAgentTool(bus=bus, task_board=board)

    result = await tool(
        agent_type="theory",
        summary="Read reference",
        content="Read the uploaded reference and summarize the key model.",
        blocking=False,
    )

    assert result["status"] == "delegated"
    task = board.get_task(result["task_id"], target_agent=AgentType.THEORY)
    assert task is not None
    assert task.status == TaskStatus.IN_PROGRESS

    messages = [await asyncio.wait_for(bus._queue.get(), timeout=1) for _ in range(2)]
    started = next(msg for msg in messages if isinstance(msg, TaskUpdateMessage))
    dispatched = next(msg for msg in messages if isinstance(msg, UserMessage))
    assert started.action == "started"
    assert started.source_agent == AgentType.MAIN
    assert started.target_agent == AgentType.THEORY
    assert dispatched.agent_type == AgentType.THEORY
