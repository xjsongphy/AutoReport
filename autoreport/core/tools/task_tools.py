"""ManageTasksTool — agent-managed task operations (todolist/waitlist)."""

from typing import Any

from loguru import logger

from ...interfaces.types import AgentType, TaskStatus, TaskUpdateMessage, UserMessage
from .registry import Tool


class ManageTasksTool(Tool):
    """List, add, start, complete, cancel, or fail tasks.

    Authorization: agent_type is injected at construction. Only the
    target_agent can modify a task's status.
    """

    name = "manage_tasks"
    description = (
        "Manage your tasks. Todolist: tasks assigned to you. Waitlist: tasks you assigned to others.\n"
        "Actions:\n"
        "- 'list': Show todolist + waitlist with status.\n"
        "- 'add': Add a local todolist entry.\n"
        "- 'start': Mark task in_progress.\n"
        "- 'complete': Mark completed. For delegated tasks, provide 'reply_content'.\n"
        "- 'cancel': Cancel. Source agent notified.\n"
        "- 'fail': Mark failed. Source agent notified."
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
        brief: str = "",
        completion_summary: str | None = None,
        reply_content: str | None = None,
        response: str | None = None,
    ) -> dict[str, Any]:
        """Manage your tasks.

        Args:
            action: One of: list, add, start, complete, cancel, fail.
            description: Task description (required for 'add'). Detailed content for API.
            task_id: Task ID (required for start/complete/cancel/fail).
            priority: Priority for 'add' action. One of: normal, high, low.
            brief: Short summary for UI list display (optional, defaults to description prefix).
            completion_summary: Short summary for the completion result.
            reply_content: Reply body that will be sent automatically to the waiting agent.
            response: Backward-compatible alias for reply_content.

        Returns:
            Result dictionary with action-specific data.
        """
        valid_actions = ("list", "add", "start", "complete", "cancel", "fail")
        if action not in valid_actions:
            return {"status": "error", "error": f"Unknown action '{action}'. Valid: {', '.join(valid_actions)}"}

        if action == "list":
            return self._handle_list()

        if action == "add":
            return await self._handle_add(description, priority, brief)

        if action == "start":
            return await self._handle_start(task_id)

        if action == "complete":
            return await self._handle_complete(task_id, completion_summary, reply_content, response)

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
                    "brief": t.brief,
                    "status": t.status.value,
                    "source_agent": t.source_agent.value,
                    "priority": t.priority,
                }
                for t in todolist
            ],
            "waitlist": [
                {
                    "task_id": t.task_id,
                    "brief": t.brief,
                    "status": t.status.value,
                    "target_agent": t.target_agent.value,
                    "priority": t.priority,
                }
                for t in waitlist
            ],
        }

    async def _handle_add(self, description: str | None, priority: str = "normal", brief: str = "") -> dict[str, Any]:
        if not description:
            return {"status": "error", "error": "description is required for 'add' action"}
        task = self._task_board.create_task(
            source=self._agent_type,
            target=self._agent_type,
            brief=brief or description,
            priority=priority,
        )
        await self._publish_task_update(task, "created")
        logger.info("{} added local task {}: {}", self._agent_type, task.task_id, description)
        return {
            "status": "ok",
            "message": f"Added task {task.task_id}: {description}",
            "task_id": task.task_id,
        }

    async def _handle_start(self, task_id: str | None) -> dict[str, Any]:
        if not task_id:
            return {"status": "error", "error": "task_id is required for 'start' action"}
        try:
            any_task = self._task_board.get_task(task_id, active_only=False)
            if any_task is None:
                return {"status": "error", "error": f"Task {task_id} not found"}
            task = self._task_board.get_task(task_id, target_agent=self._agent_type, active_only=False)
            if task is None:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            if task.target_agent != self._agent_type:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            previous_status = task.status.value
            self._task_board.start_task(task_id, target_agent=self._agent_type)
            await self._publish_task_update(task, "started", previous_status)
            return {"status": "ok", "message": f"Task {task_id} started: {task.brief}"}
        except ValueError as e:
            return {"status": "error", "error": str(e)}

    async def _handle_complete(
        self,
        task_id: str | None,
        completion_summary: str | None = None,
        reply_content: str | None = None,
        response: str | None = None,
    ) -> dict[str, Any]:
        if not task_id:
            return {"status": "error", "error": "task_id is required for 'complete' action"}
        try:
            any_task = self._task_board.get_task(task_id, active_only=False)
            if any_task is None:
                return {"status": "error", "error": f"Task {task_id} not found"}
            task = self._task_board.get_task(task_id, target_agent=self._agent_type, active_only=False)
            if task is None:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            if task.target_agent != self._agent_type:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            needs_response = task.source_agent != task.target_agent
            summary_text = str(completion_summary or "").strip()
            reply_text = str(reply_content or response or "").strip()
            if needs_response and not reply_text:
                return {
                    "status": "error",
                    "error": (
                        f"Task {task_id} is delegated from {task.source_agent.value}; "
                        "reply_content is required for 'complete' so the waiting agent can be updated"
                    ),
                }
            previous_status = task.status.value
            affected = self._task_board.complete_task(task_id, target_agent=self._agent_type)
            await self._publish_chain_notifications(affected, "completed", previous_status)
            auto_replied = await self._publish_completion_replies(affected, reply_text)
            return {
                "status": "ok",
                "message": f"Task {task_id} completed: {task.brief}",
                "chain_affected": len(affected),
                "auto_replied": auto_replied,
                "completion_summary": summary_text or None,
                "_ui_summary": summary_text or None,
                "_ui_detail": reply_text or None,
            }
        except ValueError as e:
            return {"status": "error", "error": str(e)}

    async def _handle_cancel(self, task_id: str | None) -> dict[str, Any]:
        if not task_id:
            return {"status": "error", "error": "task_id is required for 'cancel' action"}
        try:
            any_task = self._task_board.get_task(task_id, active_only=False)
            if any_task is None:
                return {"status": "error", "error": f"Task {task_id} not found"}
            task = self._task_board.get_task(task_id, target_agent=self._agent_type, active_only=False)
            if task is None:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            if task.target_agent != self._agent_type:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            previous_status = task.status.value
            affected = self._task_board.cancel_task(task_id, target_agent=self._agent_type)
            await self._publish_chain_notifications(affected, "cancelled", previous_status)
            return {
                "status": "ok",
                "message": f"Task {task_id} cancelled: {task.brief}",
                "chain_affected": len(affected),
            }
        except ValueError as e:
            return {"status": "error", "error": str(e)}

    async def _handle_fail(self, task_id: str | None) -> dict[str, Any]:
        if not task_id:
            return {"status": "error", "error": "task_id is required for 'fail' action"}
        try:
            any_task = self._task_board.get_task(task_id, active_only=False)
            if any_task is None:
                return {"status": "error", "error": f"Task {task_id} not found"}
            task = self._task_board.get_task(task_id, target_agent=self._agent_type, active_only=False)
            if task is None:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            if task.target_agent != self._agent_type:
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            previous_status = task.status.value
            affected = self._task_board.fail_task(task_id, target_agent=self._agent_type)
            await self._publish_chain_notifications(affected, "failed", previous_status)
            return {
                "status": "ok",
                "message": f"Task {task_id} failed: {task.brief}",
                "chain_affected": len(affected),
            }
        except ValueError as e:
            return {"status": "error", "error": str(e)}

    async def _publish_chain_notifications(
        self, affected_tasks: list, action: str, previous_status: str
    ) -> None:
        for task in affected_tasks:
            await self._publish_task_update(task, action, previous_status)

    async def _publish_task_update(self, task, action: str, previous_status: str | None = None) -> None:
        msg = TaskUpdateMessage(
            task_id=task.task_id,
            action=action,
            source_agent=task.source_agent,
            target_agent=task.target_agent,
            brief=task.brief,
            previous_status=previous_status,
        )
        await self._bus.publish(msg)

    async def _publish_completion_replies(self, affected_tasks: list, response: str) -> int:
        if not response:
            return 0

        terminal = affected_tasks[-1] if affected_tasks else None
        leaf = affected_tasks[0] if affected_tasks else None
        if terminal is None or leaf is None:
            return 0
        if terminal.source_agent == terminal.target_agent:
            return 0

        source = "main_agent" if leaf.target_agent == AgentType.MAIN else leaf.target_agent.value
        await self._bus.publish(UserMessage(
            content=response,
            agent_type=terminal.source_agent,
            source=source,
        ))
        return 1
