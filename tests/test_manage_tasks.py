"""Tests for ManageTasksTool."""

import asyncio

import pytest

from autoreport.core.loops.bus import MessageBus
from autoreport.core.tools.task_board import TaskBoard
from autoreport.core.tools.task_tools import ManageTasksTool
from autoreport.interfaces.types import AgentType, ReportMessage, TaskStatus, TaskUpdateMessage


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
    async def test_complete_moves_main_wait_to_todo_list_view(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw")
        plotting_tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        await plotting_tool(action="complete", task_id=task.task_id, reply_content="done")

        main_tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        listed = await main_tool(action="list")
        assert any(
            item["task_id"] == task.task_id
            and item["status"] == "pending"
            and item["brief"] == "Check Plotting completed: draw"
            for item in listed["todolist"]
        )
        assert any(
            item["task_id"] == task.task_id and item["status"] == "completed"
            for item in listed["waitlist"]
        )

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
        reply = next(msg for msg in messages if isinstance(msg, ReportMessage))
        assert reply.agent_type == AgentType.PLOTTING
        assert reply.task_id == task.task_id
        assert reply.report_type == "reply"
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
        replies = [msg for msg in messages if isinstance(msg, ReportMessage)]
        assert len(replies) == 1
        assert replies[0].agent_type == AgentType.THEORY
        assert replies[0].task_id == child.task_id
        assert replies[0].content == "formulas ready"

    @pytest.mark.asyncio
    async def test_complete_response_alias_still_supported(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)

        result = await tool(action="complete", task_id=task.task_id, response="legacy alias")

        assert result["status"] == "ok"
        messages = [await asyncio.wait_for(bus._queue.get(), timeout=1) for _ in range(2)]
        reply = next(msg for msg in messages if isinstance(msg, ReportMessage))
        assert reply.agent_type == AgentType.PLOTTING
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


# ------------------------------------------------------------------ #
#  Batch operation tests
# ------------------------------------------------------------------ #


class TestResolveIds:
    def test_task_id_only(self):
        result = ManageTasksTool._resolve_ids("tk001", None)
        assert result == ["tk001"]

    def test_task_ids_only(self):
        result = ManageTasksTool._resolve_ids(None, ["tk001", "tk002"])
        assert result == ["tk001", "tk002"]

    def test_both_with_overlap_deduplicates(self):
        result = ManageTasksTool._resolve_ids("tk001", ["tk001", "tk002"])
        assert result == ["tk001", "tk002"]

    def test_both_no_overlap(self):
        result = ManageTasksTool._resolve_ids("tk003", ["tk001", "tk002"])
        assert result == ["tk001", "tk002", "tk003"]

    def test_none_returns_empty(self):
        result = ManageTasksTool._resolve_ids(None, None)
        assert result == []


class TestBatchAdd:
    @pytest.mark.asyncio
    async def test_batch_add_creates_multiple_tasks(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(
            action="add",
            items=[
                {"description": "task alpha"},
                {"description": "task beta"},
            ],
        )
        assert result["status"] == "ok"
        tasks = board.get_todolist(AgentType.MAIN)
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_batch_add_publishes_single_notification(self, board, bus):
        notifications = []
        bus.subscribe(TaskUpdateMessage, lambda msg: notifications.append(msg))

        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(
            action="add",
            items=[
                {"description": "task alpha"},
                {"description": "task beta"},
            ],
        )
        assert result["status"] == "ok"

        msg = await asyncio.wait_for(bus._queue.get(), timeout=1)
        await bus._notify_subscribers(msg)
        assert len(notifications) == 1
        assert notifications[0].action == "created"
        assert "2 tasks" in notifications[0].brief

    @pytest.mark.asyncio
    async def test_batch_add_skips_empty_descriptions(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(
            action="add",
            items=[
                {"description": "valid task"},
                {"description": ""},
                {"description": "another valid"},
                {},
            ],
        )
        assert result["status"] == "ok"
        assert len(result["tasks"]) == 2
        tasks = board.get_todolist(AgentType.MAIN)
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_batch_add_returns_tasks_list(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(
            action="add",
            items=[
                {"description": "task one"},
                {"description": "task two", "brief": "short two"},
            ],
        )
        assert result["status"] == "ok"
        assert "tasks" in result
        assert len(result["tasks"]) == 2
        for item in result["tasks"]:
            assert "task_id" in item
            assert "brief" in item
        assert result["tasks"][1]["brief"] == "short two"


class TestBatchStatus:
    @pytest.mark.asyncio
    async def test_batch_start_multiple(self, board, bus):
        t1 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot a")
        t2 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot b")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(action="start", task_ids=[t1.task_id, t2.task_id])
        assert result["status"] == "ok"
        assert result["message"] == "started 2/2 tasks"
        assert len(result["results"]) == 2
        assert board.get_task(t1.task_id).status == TaskStatus.IN_PROGRESS
        assert board.get_task(t2.task_id).status == TaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_batch_cancel_multiple(self, board, bus):
        t1 = board.create_task(AgentType.MAIN, AgentType.THEORY, "derive x")
        t2 = board.create_task(AgentType.MAIN, AgentType.THEORY, "derive y")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.THEORY, bus=bus)
        result = await tool(action="cancel", task_ids=[t1.task_id, t2.task_id])
        assert result["status"] == "ok"
        assert result["message"] == "cancelled 2/2 tasks"
        assert board.get_task(t1.task_id).status == TaskStatus.CANCELLED
        assert board.get_task(t2.task_id).status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_batch_partial_failure(self, board, bus):
        t1 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "valid task")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(action="start", task_ids=[t1.task_id, "nonexistent_id"])
        assert result["status"] == "ok"  # top-level ok because at least one succeeded
        assert result["message"] == "started 1/2 tasks"
        assert len(result["results"]) == 2
        ok_results = [r for r in result["results"] if r["status"] == "ok"]
        err_results = [r for r in result["results"] if r["status"] == "error"]
        assert len(ok_results) == 1
        assert len(err_results) == 1
        assert "not found" in err_results[0]["error"]

    @pytest.mark.asyncio
    async def test_batch_single_id_backward_compat(self, board, bus):
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(action="start", task_ids=["nonexistent_id"])
        assert result["status"] == "error"
        assert "error" in result
        assert "not found" in result["error"]


class TestBatchComplete:
    @pytest.mark.asyncio
    async def test_batch_complete_multiple(self, board, bus):
        t1 = board.create_task(AgentType.MAIN, AgentType.MAIN, "self task a")
        t2 = board.create_task(AgentType.MAIN, AgentType.MAIN, "self task b")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.MAIN, bus=bus)
        result = await tool(
            action="complete",
            task_ids=[t1.task_id, t2.task_id],
            completion_summary="all done",
        )
        assert result["status"] == "ok"
        assert result["message"] == "Completed 2/2 tasks"
        assert len(result["results"]) == 2
        assert board.get_task(t1.task_id).status == TaskStatus.COMPLETED
        assert board.get_task(t2.task_id).status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_batch_complete_delegated_requires_reply(self, board, bus):
        t1 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "delegated draw")
        t2 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "another draw")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(action="complete", task_ids=[t1.task_id, t2.task_id])
        assert result["status"] == "error"
        assert len(result["results"]) == 2
        for r in result["results"]:
            assert r["status"] == "error"
            assert "reply_content is required" in r["error"]
        # Tasks should remain uncompleted
        assert board.get_task(t1.task_id).status == TaskStatus.PENDING
        assert board.get_task(t2.task_id).status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_batch_complete_single_backward_compat(self, board, bus):
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "single draw")
        tool = ManageTasksTool(task_board=board, agent_type=AgentType.PLOTTING, bus=bus)
        result = await tool(
            action="complete",
            task_ids=[task.task_id],
            completion_summary="done",
            reply_content="plot ready",
        )
        assert result["status"] == "ok"
        # Single-ID backward compat: top-level has task_id, chain_affected, completion_summary
        assert result["task_id"] == task.task_id
        assert result["chain_affected"] == 1
        assert result["completion_summary"] == "done"
        assert result["auto_replied"] == 1
