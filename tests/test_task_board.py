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
            brief="Create scatter plot",
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
        assert t1.task_id == "tk001"
        assert t2.task_id == "tk002"

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

    def test_complete_task_chain_with_shared_id(self):
        board = TaskBoard()
        t1 = board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate plot", task_id="tk999")
        t2 = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "create plot", task_id="tk999")
        affected = board.complete_task(t2.task_id, target_agent=AgentType.PLOTTING)
        assert len(affected) == 2
        assert board.get_task(t2.task_id, target_agent=AgentType.PLOTTING).status == TaskStatus.COMPLETED
        assert board.get_task(t1.task_id, target_agent=AgentType.MAIN).status == TaskStatus.COMPLETED

    def test_local_todo_not_in_own_waitlist(self):
        """A local todo (source == target) must not appear in the agent's own
        waitlist — otherwise the agent sees 'waiting on myself' forever."""
        board = TaskBoard()
        local = board.create_task(AgentType.MAIN, AgentType.MAIN, "audit project")
        assert local in board.get_todolist(AgentType.MAIN)
        assert local not in board.get_waitlist(AgentType.MAIN)
        # A genuinely delegated task still waits correctly
        delegated = board.create_task(AgentType.MAIN, AgentType.THEORY, "write theory")
        assert delegated in board.get_waitlist(AgentType.MAIN)

    def test_completed_waitlist_item_becomes_source_todo_view(self):
        board = TaskBoard()
        delegated = board.create_task(AgentType.MAIN, AgentType.PLOTTING, "create plot")
        board.complete_task(delegated.task_id, target_agent=AgentType.PLOTTING)
        main_todo = board.get_todolist(AgentType.MAIN)
        assert any(
            t.task_id == delegated.task_id
            and t.source_agent == AgentType.MAIN
            and t.target_agent == AgentType.PLOTTING
            and t.status == TaskStatus.COMPLETED
            for t in main_todo
        )

    def test_fail_task_chain_with_shared_id(self):
        board = TaskBoard()
        board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate", task_id="tk999")
        board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot", task_id="tk999")
        affected = board.fail_task("tk999", target_agent=AgentType.PLOTTING)
        assert len(affected) == 2
        assert board.get_task("tk999", target_agent=AgentType.MAIN).status == TaskStatus.FAILED

    def test_cancel_task_chain_with_shared_id(self):
        board = TaskBoard()
        board.create_task(AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate", task_id="tk999")
        board.create_task(AgentType.MAIN, AgentType.PLOTTING, "plot", task_id="tk999")
        affected = board.cancel_task("tk999", target_agent=AgentType.PLOTTING)
        assert len(affected) == 2
        assert board.get_task("tk999", target_agent=AgentType.MAIN).status == TaskStatus.CANCELLED

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
            board.start_task("deadbeef")

    def test_block_task_marks_target_and_propagates_upchain(self):
        # Data -> Main -> Plotting delegation chain, shared task_id
        board = TaskBoard()
        board.create_task(
            AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate plot", task_id="tk1",
        )
        board.create_task(
            AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1",
        )
        affected = board.block_task("tk1", target_agent=AgentType.PLOTTING)
        statuses = {t.target_agent: t.status for t in affected}
        assert statuses[AgentType.PLOTTING].value == "blocked"
        # The Main-side entry (source) is also blocked via chain
        assert statuses[AgentType.MAIN].value == "blocked"

    def test_get_blocked_waitlist_lists_only_blocked_delegated(self):
        board = TaskBoard()
        board.create_task(
            AgentType.DATA_ANALYSIS, AgentType.MAIN, "delegate plot", task_id="tk1",
        )
        board.create_task(
            AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1",
        )
        board.block_task("tk1", target_agent=AgentType.PLOTTING)
        blocked = board.get_blocked_waitlist(AgentType.MAIN)
        assert [t.task_id for t in blocked] == ["tk1"]
