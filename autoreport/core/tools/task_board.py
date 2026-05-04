"""TaskBoard — central in-memory task store for agent task delegation."""

import hashlib
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from ...interfaces.types import AgentType, TaskItem, TaskStatus


class TaskBoard:
    """Central store for all task items. Lives in LoopManager.

    A single TaskItem serves dual purpose:
    - waitlist for source_agent (what this agent is waiting for)
    - todolist for target_agent (what this agent should do)

    Querying: get_waitlist(X) = items where source_agent == X
              get_todolist(X) = items where target_agent == X
    """

    def __init__(self):
        self._tasks: dict[str, TaskItem] = {}
        self._counter: int = 0

    def _next_id(self, description: str = "") -> str:
        self._counter += 1
        raw = f"{self._counter}-{description}-{id(self)}"
        return hashlib.md5(raw.encode()).hexdigest()[:8]

    def create_task(
        self,
        source: AgentType,
        target: AgentType,
        description: str,
        brief: str = "",
        blocking: bool = False,
        parent_task_id: str | None = None,
        priority: str = "normal",
    ) -> TaskItem:
        """Create a new task item."""
        task = TaskItem(
            task_id=self._next_id(description),
            brief=brief or description[:80],
            description=description,
            source_agent=source,
            target_agent=target,
            status=TaskStatus.PENDING,
            priority=priority,
            created_at=datetime.now(timezone.utc),
            parent_task_id=parent_task_id,
            blocking=blocking,
        )
        self._tasks[task.task_id] = task
        logger.debug("TaskBoard: created task {} ({})", task.task_id, description[:60])
        return task

    def get_task(self, task_id: str) -> Optional["TaskItem"]:
        return self._tasks.get(task_id)

    def start_task(self, task_id: str) -> TaskItem:
        """PENDING -> IN_PROGRESS. Raises ValueError if task not found or wrong status."""
        task = self._require_task(task_id)
        if task.status != TaskStatus.PENDING:
            raise ValueError(
                f"Task {task_id} is {task.status}, expected {TaskStatus.PENDING}"
            )
        task.status = TaskStatus.IN_PROGRESS
        logger.debug("TaskBoard: started task {}", task_id)
        return task

    def complete_task(self, task_id: str) -> list[TaskItem]:
        """Mark task COMPLETED, walk parent chain. Returns affected tasks (in chain order)."""
        task = self._require_task(task_id)
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        affected = [task]
        affected.extend(self._walk_parent_chain(task, TaskStatus.COMPLETED))
        logger.debug("TaskBoard: completed task {} (chain: {} affected)", task_id, len(affected))
        return affected

    def fail_task(self, task_id: str) -> list[TaskItem]:
        """Mark task FAILED, propagate up parent chain."""
        task = self._require_task(task_id)
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now(timezone.utc)
        affected = [task]
        affected.extend(self._walk_parent_chain(task, TaskStatus.FAILED))
        logger.debug("TaskBoard: failed task {} (chain: {} affected)", task_id, len(affected))
        return affected

    def cancel_task(self, task_id: str) -> list[TaskItem]:
        """Mark task CANCELLED, propagate up parent chain."""
        task = self._require_task(task_id)
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now(timezone.utc)
        affected = [task]
        affected.extend(self._walk_parent_chain(task, TaskStatus.CANCELLED))
        logger.debug("TaskBoard: cancelled task {} (chain: {} affected)", task_id, len(affected))
        return affected

    def _walk_parent_chain(self, trigger: TaskItem, new_status: TaskStatus) -> list[TaskItem]:
        """Walk up parent_task_id chain, updating each parent to new_status."""
        affected = []
        current = trigger
        while current.parent_task_id:
            parent = self._tasks.get(current.parent_task_id)
            if parent is None:
                break
            if parent.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                break
            parent.status = new_status
            parent.completed_at = datetime.now(timezone.utc)
            affected.append(parent)
            current = parent
        return affected

    def get_todolist(self, agent_type: AgentType) -> list[TaskItem]:
        """Active todolist for an agent (PENDING or IN_PROGRESS tasks targeting them)."""
        return [
            t for t in self._tasks.values()
            if t.target_agent == agent_type
            and t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        ]

    def get_waitlist(self, agent_type: AgentType) -> list[TaskItem]:
        """Active waitlist for an agent (PENDING or IN_PROGRESS tasks they created)."""
        return [
            t for t in self._tasks.values()
            if t.source_agent == agent_type
            and t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        ]

    def get_all_tasks(self) -> dict[str, dict[str, list[TaskItem]]]:
        """All tasks grouped by agent id. For main agent overview."""
        result: dict[str, dict[str, list[TaskItem]]] = {}
        for agent in AgentType:
            agent_id = agent.value
            result[agent_id] = {
                "todolist": self.get_todolist(agent),
                "waitlist": self.get_waitlist(agent),
            }
        return result

    def _require_task(self, task_id: str) -> TaskItem:
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        return task
