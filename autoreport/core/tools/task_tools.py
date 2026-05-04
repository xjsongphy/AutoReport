"""ManageTasksTool — agent-managed task operations (todolist/waitlist)."""

from typing import Any

from loguru import logger

from ...interfaces.types import AgentType, TaskStatus, TaskUpdateMessage
from .registry import Tool


class ManageTasksTool(Tool):
    """List, add, start, complete, cancel, or fail tasks.

    Authorization: agent_type is injected at construction. Only the
    target_agent can modify a task's status.
    """

    name = "manage_tasks"
    description = (
        "Manage your own tasks (todolist and waitlist). Actions:\n"
        "- 'list': Show your current todolist + waitlist with status.\n"
        "- 'add': Add a local-only todolist entry for yourself.\n"
        "- 'start': Mark a task as in_progress.\n"
        "- 'complete': Mark a task as completed. If the task was delegated to you, "
        "the source agent will be notified automatically.\n"
        "- 'cancel': Cancel a task. The source agent will be notified.\n"
        "- 'fail': Mark a task as failed. The source agent will be notified."
    )

    def __init__(self, task_board, agent_type: AgentType, bus):
        self._task_board = task_board
        self._agent_type = agent_type
        self._bus = bus

    async def __call__(
        self,
        action: str,
        description: str | None = None,
        task_id: str | None = None,
        priority: str = "normal",
    ) -> dict[str, Any]:
        """Manage your tasks.

        Args:
            action: One of: list, add, start, complete, cancel, fail.
            description: Task description (required for 'add').
            task_id: Task ID (required for start/complete/cancel/fail).
            priority: Priority for 'add' action. One of: normal, high, low.

        Returns:
            Result dictionary with action-specific data.
        """
        valid_actions = ("list", "add", "start", "complete", "cancel", "fail")
        if action not in valid_actions:
            return {"status": "error", "error": f"Unknown action '{action}'. Valid: {', '.join(valid_actions)}"}

        if action == "list":
            return self._handle_list()

        if action == "add":
            return self._handle_add(description, priority)

        if action == "start":
            return self._handle_start(task_id)

        if action == "complete":
            return await self._handle_complete(task_id)

        if action == "cancel":
            return await self._handle_cancel(task_id)

        if action == "fail":
            return await self._handle_fail(task_id)

        return {"status": "error", "error": "Unreachable"}

    def _handle_list(self) -> dict[str, Any]:
        todolist = self._task_board.get_todolist(self._agent_type)
        waitlist = self._task_board.get_waitlist(self._agent_type)
        return {
            "status": "ok",
            "agent_type": self._agent_type.value,
            "todolist": [
                {
                    "task_id": t.task_id,
                    "description": t.description,
                    "status": t.status.value,
                    "source_agent": t.source_agent.value,
                    "priority": t.priority,
                    "parent_task_id": t.parent_task_id,
                }
                for t in todolist
            ],
            "waitlist": [
                {
                    "task_id": t.task_id,
                    "description": t.description,
                    "status": t.status.value,
                    "target_agent": t.target_agent.value,
                    "priority": t.priority,
                    "parent_task_id": t.parent_task_id,
                }
                for t in waitlist
            ],
        }

    def _handle_add(self, description: str | None, priority: str = "normal") -> dict[str, Any]:
        if not description:
            return {"status": "error", "error": "description is required for 'add' action"}
        task = self._task_board.create_task(
            source=self._agent_type,
            target=self._agent_type,
            description=description,
            priority=priority,
        )
        logger.info("{} added local task {}: {}", self._agent_type, task.task_id, description)
        return {
            "status": "ok",
            "message": f"Added task {task.task_id}: {description}",
            "task_id": task.task_id,
        }

    def _handle_start(self, task_id: str | None) -> dict[str, Any]:
        if not task_id:
            return {"status": "error", "error": "task_id is required for 'start' action"}
        try:
            task = self._task_board.get_task(task_id)
            if task is None:
                return {"status": "error", "error": f"Task {task_id} not found"}
            if task.target_agent != self._agent_type:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            self._task_board.start_task(task_id)
            return {"status": "ok", "message": f"Task {task_id} started: {task.description}"}
        except ValueError as e:
            return {"status": "error", "error": str(e)}

    async def _handle_complete(self, task_id: str | None) -> dict[str, Any]:
        if not task_id:
            return {"status": "error", "error": "task_id is required for 'complete' action"}
        try:
            task = self._task_board.get_task(task_id)
            if task is None:
                return {"status": "error", "error": f"Task {task_id} not found"}
            if task.target_agent != self._agent_type:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            previous_status = task.status.value
            affected = self._task_board.complete_task(task_id)
            await self._publish_chain_notifications(affected, "completed", previous_status)
            return {
                "status": "ok",
                "message": f"Task {task_id} completed: {task.description}",
                "chain_affected": len(affected),
            }
        except ValueError as e:
            return {"status": "error", "error": str(e)}

    async def _handle_cancel(self, task_id: str | None) -> dict[str, Any]:
        if not task_id:
            return {"status": "error", "error": "task_id is required for 'cancel' action"}
        try:
            task = self._task_board.get_task(task_id)
            if task is None:
                return {"status": "error", "error": f"Task {task_id} not found"}
            if task.target_agent != self._agent_type:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            previous_status = task.status.value
            affected = self._task_board.cancel_task(task_id)
            await self._publish_chain_notifications(affected, "cancelled", previous_status)
            return {
                "status": "ok",
                "message": f"Task {task_id} cancelled: {task.description}",
                "chain_affected": len(affected),
            }
        except ValueError as e:
            return {"status": "error", "error": str(e)}

    async def _handle_fail(self, task_id: str | None) -> dict[str, Any]:
        if not task_id:
            return {"status": "error", "error": "task_id is required for 'fail' action"}
        try:
            task = self._task_board.get_task(task_id)
            if task is None:
                return {"status": "error", "error": f"Task {task_id} not found"}
            if task.target_agent != self._agent_type:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            previous_status = task.status.value
            affected = self._task_board.fail_task(task_id)
            await self._publish_chain_notifications(affected, "failed", previous_status)
            return {
                "status": "ok",
                "message": f"Task {task_id} failed: {task.description}",
                "chain_affected": len(affected),
            }
        except ValueError as e:
            return {"status": "error", "error": str(e)}

    async def _publish_chain_notifications(
        self, affected_tasks: list, action: str, previous_status: str
    ) -> None:
        for task in affected_tasks:
            msg = TaskUpdateMessage(
                task_id=task.task_id,
                action=action,
                source_agent=task.source_agent,
                target_agent=task.target_agent,
                description=task.description,
                previous_status=previous_status,
            )
            await self._bus.publish(msg)
