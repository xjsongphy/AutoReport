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
        result = await tool(action="complete", task_id=task.task_id)
        assert result["status"] == "ok"
        assert result["chain_affected"] == 1

        # Process notification
        msg = await asyncio.wait_for(bus._queue.get(), timeout=1)
        await bus._notify_subscribers(msg)
        assert len(notifications) == 1
        assert notifications[0].action == "completed"

    @pytest.mark.asyncio
    async def test_complete_chain_notifies_all(self, board, bus):
        t1 = board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate")
        t2 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw",
                               parent_task_id=t1.task_id)
        notifications = []
        bus.subscribe(TaskUpdateMessage, lambda msg: notifications.append(msg))

        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(action="complete", task_id=t2.task_id)
        assert result["chain_affected"] == 2  # t2 + t1

        # Process notifications
        for _ in range(2):
            msg = await asyncio.wait_for(bus._queue.get(), timeout=1)
            await bus._notify_subscribers(msg)
        assert len(notifications) == 2


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
        result = await tool(action="start", task_id="T-999")
        assert result["status"] == "error"
        assert "not found" in result["error"]
