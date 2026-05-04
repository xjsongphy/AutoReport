"""Tests for TaskBoard."""

import pytest

from autoreport.core.tools.task_board import TaskBoard
from autoreport.interfaces.types import AgentType, TaskStatus


class TestTaskBoard:
    def test_create_task_dual_view(self):
        board = TaskBoard()
        task = board.create_task(
            source=AgentType.DATA_ANALYSIS,
            target=AgentType.PLOTTING,
            description="Create scatter plot",
        )
        assert task in board.get_waitlist(AgentType.DATA_ANALYSIS)
        assert task in board.get_todolist(AgentType.PLOTTING)
        assert task not in board.get_waitlist(AgentType.PLOTTING)
        assert task not in board.get_todolist(AgentType.DATA_ANALYSIS)

    def test_create_task_ids_are_unique(self):
        board = TaskBoard()
        t1 = board.create_task(AgentType.MAIN, AgentType.THEORY, "t1")
        t2 = board.create_task(AgentType.MAIN, AgentType.THEORY, "t2")
        assert t1.task_id != t2.task_id
        assert t1.task_id == "T-001"
        assert t2.task_id == "T-002"

    def test_start_task(self):
        board = TaskBoard()
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot")
        result = board.start_task(task.task_id)
        assert result.status == TaskStatus.IN_PROGRESS

    def test_start_task_wrong_status_raises(self):
        board = TaskBoard()
        task = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot")
        board.complete_task(task.task_id)
        with pytest.raises(ValueError, match="COMPLETED"):
            board.start_task(task.task_id)

    def test_complete_task_chain(self):
        board = TaskBoard()
        t1 = board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate plot")
        t2 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "create plot",
                               parent_task_id=t1.task_id)
        affected = board.complete_task(t2.task_id)
        assert len(affected) == 2
        assert board.get_task(t2.task_id).status == TaskStatus.COMPLETED
        assert board.get_task(t1.task_id).status == TaskStatus.COMPLETED

    def test_fail_task_chain(self):
        board = TaskBoard()
        t1 = board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate")
        t2 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot",
                               parent_task_id=t1.task_id)
        affected = board.fail_task(t2.task_id)
        assert len(affected) == 2
        assert board.get_task(t1.task_id).status == TaskStatus.FAILED

    def test_cancel_task_chain(self):
        board = TaskBoard()
        t1 = board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate")
        t2 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot",
                               parent_task_id=t1.task_id)
        affected = board.cancel_task(t2.task_id)
        assert len(affected) == 2
        assert board.get_task(t1.task_id).status == TaskStatus.CANCELLED

    def test_chain_stops_at_resolved_parent(self):
        board = TaskBoard()
        t1 = board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate")
        t2 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot",
                               parent_task_id=t1.task_id)
        board.complete_task(t1.task_id)
        t3 = board.create_task(AgentType.REPORT, AgentType.PLOTTING, "other",
                               parent_task_id=t1.task_id)
        affected = board.complete_task(t3.task_id)
        assert len(affected) == 1
        assert affected[0].task_id == t3.task_id

    def test_get_all_tasks(self):
        board = TaskBoard()
        board.create_task(AgentType.MAIN, AgentType.THEORY, "t1")
        board.create_task(AgentType.DATA_ANALYSIS, AgentType.PLOTTING, "t2")
        all_t = board.get_all_tasks()
        assert "main" in all_t
        assert len(all_t["theory"]["todolist"]) == 1
        assert len(all_t["plotting"]["todolist"]) == 1

    def test_task_not_found_raises(self):
        board = TaskBoard()
        with pytest.raises(ValueError, match="not found"):
            board.start_task("T-999")
