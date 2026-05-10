"""Tests for ManageTasksTool."""

import asyncio

import pytest

from autoreport.core.loops.bus import MessageBus
from autoreport.core.tools.task_board import TaskBoard
from autoreport.core.tools.task_tools import ManageTasksTool
from autoreport.interfaces.types import AgentType, TaskStatus, TaskUpdateMessage


@pytest.fixture
def board():
    return TaskBoard()


@pytest.fixture
def bus():
    return MessageBus()


class TestManageTasksToolList:
    @pytest.mark.asyncio
    async def test_list_empty(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(action="list")
        assert result["status"] == "ok"
        assert result["todolist"] == []
        assert result["waitlist"] == []

    @pytest.mark.asyncio
    async def test_list_with_tasks(self, board, bus):
        board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw")
        board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "analyze")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(action="list")
        assert len(result["todolist"]) == 1  # analyze task targets MAIN
        assert len(result["waitlist"]) == 1  # draw task sourced by MAIN
        assert "description" not in result["todolist"][0]
        assert "description" not in result["waitlist"][0]


class TestManageTasksToolAdd:
    @pytest.mark.asyncio
    async def test_add_local_task(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(action="add", description="local todo")
        assert result["status"] == "ok"
        assert "task_id" in result
        # Self-assigned task
        tasks = board.get_todolist(AgentType.MAIN)
        assert len(tasks) == 1
        assert tasks[0].source_agent == AgentType.MAIN
        assert tasks[0].target_agent == AgentType.MAIN

    @pytest.mark.asyncio
    async def test_add_publishes_created_notification(self, board, bus):
        notifications = []
        bus.subscribe(TaskUpdateMessage, lambda msg: notifications.append(msg))

        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(action="add", description="local todo")
        assert result["status"] == "ok"

        msg = await asyncio.wait_for(bus._queue.get(), timeout=1)
        await bus._notify_subscribers(msg)
        assert len(notifications) == 1
        assert notifications[0].action == "created"
        assert notifications[0].brief == "local todo"

    @pytest.mark.asyncio
    async def test_add_requires_description(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(action="add")
        assert result["status"] == "error"
        assert "description" in result["error"]


class TestManageTasksToolStart:
    @pytest.mark.asyncio
    async def test_start_task(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(action="start", task_id=task.task_id)
        assert result["status"] == "ok"
        assert board.get_task(task.task_id).status == TaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_start_publishes_started_notification(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot summary")
        notifications = []
        bus.subscribe(TaskUpdateMessage, lambda msg: notifications.append(msg))

        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(action="start", task_id=task.task_id)
        assert result["status"] == "ok"

        msg = await asyncio.wait_for(bus._queue.get(), timeout=1)
        await bus._notify_subscribers(msg)
        assert len(notifications) == 1
        assert notifications[0].action == "started"
        assert notifications[0].brief == "plot summary"

    @pytest.mark.asyncio
    async def test_start_wrong_agent_rejected(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.THEORY, bus=bus)
        result = await tool(action="start", task_id=task.task_id)
        assert result["status"] == "error"
        assert "not assigned" in result["error"]

    @pytest.mark.asyncio
    async def test_start_requires_task_id(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(action="start")
        assert result["status"] == "error"


class TestManageTasksToolComplete:
    @pytest.mark.asyncio
    async def test_complete_publishes_notification(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw")
        notifications = []
        bus.subscribe(TaskUpdateMessage, lambda msg: notifications.append(msg))

        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(
            action="complete",
            task_id=task.task_id,
            completion_summary="completed draw",
            reply_content="done",
        )
        assert result["status"] == "ok"
        assert result["chain_affected"] == 1
        assert result["completion_summary"] == "completed draw"
        assert result["_ui_summary"] == "completed draw"
        assert result["_ui_detail"] == "done"

        # Process notification
        msg = await asyncio.wait_for(bus._queue.get(), timeout=1)
        await bus._notify_subscribers(msg)
        assert len(notifications) == 1
        assert notifications[0].action == "completed"

    @pytest.mark.asyncio
    async def test_complete_chain_notifies_all(self, board, bus):
        t1 = board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate", task_id="tk900")
        t2 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk900")
        notifications = []
        bus.subscribe(TaskUpdateMessage, lambda msg: notifications.append(msg))

        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(action="complete", task_id=t2.task_id, reply_content="done")
        assert result["chain_affected"] == 2  # t2 + t1

        # Process notifications
        for _ in range(2):
            msg = await asyncio.wait_for(bus._queue.get(), timeout=1)
            await bus._notify_subscribers(msg)
        assert len(notifications) == 2

    @pytest.mark.asyncio
    async def test_complete_delegated_task_requires_response(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)

        result = await tool(action="complete", task_id=task.task_id)

        assert result["status"] == "error"
        assert "reply_content is required" in result["error"]
        assert board.get_task(task.task_id).status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_complete_delegated_task_auto_replies(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)

        result = await tool(action="complete", task_id=task.task_id, reply_content="plot done")

        assert result["status"] == "ok"
        assert result["auto_replied"] == 1

        messages = [await asyncio.wait_for(bus._queue.get(), timeout=1) for _ in range(2)]
        reply = next(msg for msg in messages if hasattr(msg, "source") and getattr(msg, "source", None) == "plotting")
        assert reply.agent_type == AgentType.MAIN
        assert reply.content == "plot done"

    @pytest.mark.asyncio
    async def test_complete_sub_main_sub_chain_auto_replies_to_main_and_origin(self, board, bus):
        parent = board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "coordinate theory", task_id="tk901")
        child = board.create_task(
            AgentType.MAIN,
            AgentType.THEORY,
            "derive formulas",
            task_id="tk901",
        )
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.THEORY, bus=bus)

        result = await tool(
            action="complete",
            task_id=child.task_id,
            completion_summary="theory finished",
            reply_content="formulas ready",
        )

        assert result["status"] == "ok"
        assert result["chain_affected"] == 2
        assert result["auto_replied"] == 1
        assert result["completion_summary"] == "theory finished"
        assert board.get_task(parent.task_id).status == TaskStatus.COMPLETED
        assert board.get_task(child.task_id).status == TaskStatus.COMPLETED

        messages = [await asyncio.wait_for(bus._queue.get(), timeout=1) for _ in range(3)]
        replies = [msg for msg in messages if hasattr(msg, "source") and getattr(msg, "source", None) == "theory"]
        assert len(replies) == 1
        assert replies[0].agent_type == AgentType.DATA_ANALYSIS

    @pytest.mark.asyncio
    async def test_complete_response_alias_still_supported(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)

        result = await tool(action="complete", task_id=task.task_id, response="legacy alias")

        assert result["status"] == "ok"
        messages = [await asyncio.wait_for(bus._queue.get(), timeout=1) for _ in range(2)]
        reply = next(msg for msg in messages if hasattr(msg, "source") and getattr(msg, "source", None) == "plotting")
        assert reply.content == "legacy alias"


class TestManageTasksToolCancel:
    @pytest.mark.asyncio
    async def test_cancel_task(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.THEORY, "derive")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.THEORY, bus=bus)
        result = await tool(action="cancel", task_id=task.task_id)
        assert result["status"] == "ok"
        assert board.get_task(task.task_id).status == TaskStatus.CANCELLED


class TestManageTasksToolFail:
    @pytest.mark.asyncio
    async def test_fail_task(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.THEORY, "derive")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.THEORY, bus=bus)
        result = await tool(action="fail", task_id=task.task_id)
        assert result["status"] == "ok"
        assert board.get_task(task.task_id).status == TaskStatus.FAILED


class TestManageTasksToolErrors:
    @pytest.mark.asyncio
    async def test_unknown_action(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(action="unknown")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_task_id_for_complete(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(action="complete")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_nonexistent_task(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(action="start", task_id="deadbeef")
        assert result["status"] == "error"
        assert "not found" in result["error"]
