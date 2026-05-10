"""TaskBoard - central in-memory task store for agent task delegation."""

from datetime import datetime, timezone

from loguru import logger

from ...interfaces.types import AgentType, TaskItem, TaskStatus


class TaskBoard:
    """Central store for task items keyed by a shared link id."""

    def __init__(self):
        self._tasks: list[TaskItem] = []
        self._counter: int = 0

    def _encode_counter(self, value: int) -> str:
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
        if value <= 0:
            return "0"
        chars: list[str] = []
        current = value
        while current:
            current, remainder = divmod(current, len(alphabet))
            chars.append(alphabet[remainder])
        return "".join(reversed(chars))

    def _next_id(self) -> str:
        self._counter += 1
        return f"tk{self._encode_counter(self._counter).zfill(3)}"

    def create_task(
        self,
        source: AgentType,
        target: AgentType,
        brief: str,
        blocking: bool = False,
        priority: str = "normal",
        task_id: str | None = None,
    ) -> TaskItem:
        """Create a new task item. task_id may be reused across a routed chain."""
        text = str(brief or "").strip()
        task = TaskItem(
            task_id=task_id or self._next_id(),
            brief=text or "task",
            source_agent=source,
            target_agent=target,
            status=TaskStatus.PENDING,
            priority=priority,
            created_at=datetime.now(timezone.utc),
            blocking=blocking,
        )
        self._tasks.append(task)
        logger.debug("TaskBoard: created task {} ({} -> {}, {})", task.task_id, source, target, task.brief[:60])
        return task

    def get_task(
        self,
        task_id: str,
        *,
        target_agent: AgentType | None = None,
        source_agent: AgentType | None = None,
        active_only: bool = False,
    ) -> TaskItem | None:
        for task in self._tasks:
            if task.task_id != task_id:
                continue
            if target_agent is not None and task.target_agent != target_agent:
                continue
            if source_agent is not None and task.source_agent != source_agent:
                continue
            if active_only and task.status not in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
                continue
            return task
        return None

    def get_tasks_by_id(self, task_id: str) -> list[TaskItem]:
        return [task for task in self._tasks if task.task_id == task_id]

    def start_task(self, task_id: str, target_agent: AgentType | None = None) -> TaskItem:
        task = self._require_task(task_id, target_agent=target_agent, active_only=False)
        if task.status != TaskStatus.PENDING:
            raise ValueError(f"Task {task_id} is {task.status}, expected {TaskStatus.PENDING}")
        task.status = TaskStatus.IN_PROGRESS
        logger.debug("TaskBoard: started task {}", task_id)
        return task

    def complete_task(self, task_id: str, target_agent: AgentType | None = None) -> list[TaskItem]:
        return self._update_chain(task_id, TaskStatus.COMPLETED, target_agent=target_agent)

    def fail_task(self, task_id: str, target_agent: AgentType | None = None) -> list[TaskItem]:
        return self._update_chain(task_id, TaskStatus.FAILED, target_agent=target_agent)

    def cancel_task(self, task_id: str, target_agent: AgentType | None = None) -> list[TaskItem]:
        return self._update_chain(task_id, TaskStatus.CANCELLED, target_agent=target_agent)

    def _update_chain(
        self, task_id: str, new_status: TaskStatus, *, target_agent: AgentType | None = None
    ) -> list[TaskItem]:
        task = self._require_task(task_id, target_agent=target_agent, active_only=False)
        if task.status not in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
            raise ValueError(f"Task {task_id} is {task.status}, cannot {new_status.value}")
        affected: list[TaskItem] = []
        self._mark(task, new_status)
        affected.append(task)

        current_target = task.source_agent
        while True:
            upstream = self.get_task(task_id, target_agent=current_target, active_only=True)
            if upstream is None:
                break
            self._mark(upstream, new_status)
            affected.append(upstream)
            current_target = upstream.source_agent

        logger.debug("TaskBoard: {} task {} (chain: {} affected)", new_status.value, task_id, len(affected))
        return affected

    def _mark(self, task: TaskItem, new_status: TaskStatus) -> None:
        task.status = new_status
        task.completed_at = datetime.now(timezone.utc)

    def get_todolist(self, agent_type: AgentType) -> list[TaskItem]:
        return [
            t for t in self._tasks
            if t.target_agent == agent_type and t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        ]

    def get_waitlist(self, agent_type: AgentType) -> list[TaskItem]:
        return [
            t for t in self._tasks
            if t.source_agent == agent_type and t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        ]

    def get_all_tasks(self) -> dict[str, dict[str, list[TaskItem]]]:
        result: dict[str, dict[str, list[TaskItem]]] = {}
        for agent in AgentType:
            result[agent.value] = {
                "todolist": self.get_todolist(agent),
                "waitlist": self.get_waitlist(agent),
            }
        return result

    def _require_task(
        self,
        task_id: str,
        *,
        target_agent: AgentType | None = None,
        source_agent: AgentType | None = None,
        active_only: bool = False,
    ) -> TaskItem:
        task = self.get_task(
            task_id,
            target_agent=target_agent,
            source_agent=source_agent,
            active_only=active_only,
        )
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        return task
