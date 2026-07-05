"""ManageTasksTool — agent-managed task operations (todolist/waitlist)."""

from typing import Any

from loguru import logger

from ...interfaces.types import AgentType, ReportMessage, TaskUpdateMessage
from .registry import Tool
from .session_utils import resolve_session_id


class ManageTasksTool(Tool):
    """List, add, start, complete, cancel, or fail tasks.

    Supports batch operations: pass a list to 'items' (for add) or
    'task_ids' (for start/complete/cancel/fail) to operate on multiple
    tasks in a single call. This reduces notification spam and tool round-trips.
    """

    name = "manage_tasks"
    description = (
        "Manage your tasks. Todolist: tasks assigned to you. Waitlist: tasks you assigned to others.\n"
        "Actions:\n"
        "- 'list': Show todolist + waitlist with status.\n"
        "- 'add': Add one or more local todolist entries. Use 'items' for batch.\n"
        "- 'start': Mark task(s) in_progress. Use 'task_ids' for batch.\n"
        "- 'complete': Mark completed. For delegated tasks, provide 'reply_content'. Use 'task_ids' for batch.\n"
        "- 'cancel': Cancel task(s). Use 'task_ids' for batch.\n"
        "- 'fail': Mark failed. Use 'task_ids' for batch."
    )

    def __init__(self, task_board, agent_type: AgentType, bus, session_id_resolver=None):
        self._task_board = task_board
        self._agent_type = agent_type
        self._bus = bus
        self._session_id_resolver = session_id_resolver

    def _session_id(self) -> str | None:
        return resolve_session_id(self._session_id_resolver)

    async def __call__(
        self,
        action: str,
        # Single-item params (backward compatible)
        description: str | None = None,
        task_id: str | None = None,
        brief: str = "",
        completion_summary: str | None = None,
        reply_content: str | None = None,
        response: str | None = None,
        # Batch params
        items: list[dict] | None = None,
        task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Manage your tasks.

        Args:
            action: One of: list, add, start, complete, cancel, fail.
            description: Task description (single add). Use 'items' for batch.
            task_id: Single task ID (for start/complete/cancel/fail). Use 'task_ids' for batch.
            brief: Short summary for single 'add'.
            completion_summary: Short summary for completion result.
            reply_content: Reply sent to waiting agent on complete.
            response: Backward-compatible alias for reply_content.
            items: Batch add — list of {description, brief?} dicts.
            task_ids: Batch status change — list of task ID strings.

        Returns:
            Result dictionary. Batch operations return 'results' list.
        """
        valid_actions = ("list", "add", "start", "complete", "cancel", "fail")
        if action not in valid_actions:
            return {
                "status": "error",
                "error": f"Unknown action '{action}'. Valid: {', '.join(valid_actions)}",
            }

        if action == "list":
            return self._handle_list()

        if action == "add":
            return await self._handle_add(description, brief, items)

        # Normalize single task_id → task_ids list
        ids = self._resolve_ids(task_id, task_ids)
        if not ids:
            return {"status": "error", "error": "task_id or task_ids is required"}

        if action == "start":
            return await self._handle_batch_status(ids, "start")

        if action == "complete":
            return await self._handle_batch_complete(
                ids, completion_summary, reply_content, response
            )

        if action == "cancel":
            return await self._handle_batch_status(ids, "cancel")

        if action == "fail":
            return await self._handle_batch_status(ids, "fail")

        return {"status": "error", "error": "Unreachable"}

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    _PAST_TENSE = {"start": "started", "complete": "completed", "cancel": "cancelled", "fail": "failed"}

    @classmethod
    def _past_tense(cls, action: str) -> str:
        return cls._PAST_TENSE.get(action, action + "d")

    @staticmethod
    def _resolve_ids(task_id: str | None, task_ids: list[str] | None) -> list[str]:
        """Resolve single task_id and/or task_ids list into a deduplicated list."""
        ids: list[str] = []
        if task_ids:
            ids.extend(task_ids)
        if task_id and task_id not in ids:
            ids.append(task_id)
        return ids

    def _check_auth(self, tid: str) -> tuple[dict | None, Any | None]:
        """Authorization check: verify task exists and belongs to this agent.

        Returns (error_dict, task) — if error_dict is not None, auth failed.
        """
        sid = self._session_id()
        any_task = self._task_board.get_task(tid, active_only=False, session_id=sid)
        if any_task is None:
            any_task = self._task_board.get_task(tid, active_only=False)
        if any_task is None:
            return {"status": "error", "error": f"Task {tid} not found"}, None
        task = self._task_board.get_task(
            tid, target_agent=self._agent_type, active_only=False, session_id=sid
        )
        if task is None:
            task = self._task_board.get_task(
                tid, target_agent=self._agent_type, active_only=False
            )
        if task is None:
            return {"status": "error", "error": f"Task {tid} is not assigned to you"}, None
        return None, task

    # ------------------------------------------------------------------ #
    #  List
    # ------------------------------------------------------------------ #

    def _handle_list(self) -> dict[str, Any]:
        sid = self._session_id()
        todolist = self._task_board.get_todolist(self._agent_type, session_id=sid)
        waitlist = self._task_board.get_waitlist(self._agent_type, session_id=sid)
        return {
            "status": "ok",
            "agent_type": self._agent_type.value,
            "todolist": [
                {
                    "task_id": t.task_id,
                    "brief": t.brief,
                    "status": t.status.value,
                    "source_agent": t.source_agent.value,
                }
                for t in todolist
            ],
            "waitlist": [
                {
                    "task_id": t.task_id,
                    "brief": t.brief,
                    "status": t.status.value,
                    "target_agent": t.target_agent.value,
                }
                for t in waitlist
            ],
        }

    # ------------------------------------------------------------------ #
    #  Add (single or batch)
    # ------------------------------------------------------------------ #

    async def _handle_add(
        self,
        description: str | None,
        brief: str = "",
        items: list[dict] | None = None,
    ) -> dict[str, Any]:
        # Batch add
        if items:
            return await self._handle_batch_add(items)

        # Single add
        if not description:
            return {
                "status": "error",
                "error": "description (or items) is required for 'add' action",
            }
        task = self._task_board.create_task(
            source=self._agent_type,
            target=self._agent_type,
            brief=brief or description,
            session_id=self._session_id(),
        )
        await self._publish_task_update(task, "created")
        logger.info("{} added local task {}: {}", self._agent_type, task.task_id, description)
        return {
            "status": "ok",
            "message": f"Added task {task.task_id}: {description}",
            "task_id": task.task_id,
        }

    async def _handle_batch_add(self, items: list[dict]) -> dict[str, Any]:
        """Add multiple local tasks at once, publish one batch notification."""
        if not isinstance(items, list):
            return {
                "status": "error",
                "error": f"'items' must be a list of dicts, got {type(items).__name__}",
            }
        created: list[dict] = []
        tasks: list = []
        for item in items:
            if not isinstance(item, dict):
                continue
            desc = str(item.get("description", ""))
            if not desc:
                continue
            b = str(item.get("brief", "")) or desc[:80]
            task = self._task_board.create_task(
                source=self._agent_type,
                target=self._agent_type,
                brief=b,
                session_id=self._session_id(),
            )
            tasks.append(task)
            created.append({"task_id": task.task_id, "brief": task.brief})

        # Single batch notification
        if tasks:
            await self._publish_batch_task_update(tasks, "created")

        logger.info("{} batch-added {} tasks", self._agent_type, len(created))
        return {
            "status": "ok",
            "message": f"Added {len(created)} tasks",
            "tasks": created,
        }

    # ------------------------------------------------------------------ #
    #  Status changes (start / cancel / fail — batch)
    # ------------------------------------------------------------------ #

    async def _handle_batch_status(self, ids: list[str], action: str) -> dict[str, Any]:
        """Apply a status action (start/cancel/fail) to multiple tasks."""
        board_fn = {
            "start": self._task_board.start_task,
            "cancel": self._task_board.cancel_task,
            "fail": self._task_board.fail_task,
        }[action]

        results: list[dict] = []
        all_affected: list = []
        prev_statuses: list[str] = []

        for tid in ids:
            err, task = self._check_auth(tid)
            if err:
                results.append({"task_id": tid, **err})
                continue
            try:
                previous_status = task.status.value
                result = board_fn(tid, target_agent=self._agent_type, session_id=task.session_id)
                # start_task returns a single TaskItem; others return a list
                affected = result if isinstance(result, list) else [result]
                all_affected.extend(affected)
                prev_statuses.append(previous_status)
                results.append(
                    {
                        "task_id": tid,
                        "status": "ok",
                        "message": f"Task {tid} {action}d: {task.brief}",
                        "chain_affected": len(affected),
                    }
                )
            except ValueError as e:
                results.append({"task_id": tid, "status": "error", "error": str(e)})

        # Publish individual notifications for each affected task
        for i, task in enumerate(all_affected):
            await self._publish_task_update(
                task, self._past_tense(action), prev_statuses[i] if i < len(prev_statuses) else None
            )

        ok_count = sum(1 for r in results if r.get("status") == "ok")
        result = {
            "status": "ok" if ok_count else "error",
            "message": f"{self._past_tense(action)} {ok_count}/{len(ids)} tasks",
            "results": results,
        }
        # Backward compat: single-ID error surfaces at top level
        if len(ids) == 1 and ok_count == 0 and results:
            result["error"] = results[0].get("error", "unknown error")
        return result

    # ------------------------------------------------------------------ #
    #  Complete (batch)
    # ------------------------------------------------------------------ #

    async def _handle_batch_complete(
        self,
        ids: list[str],
        completion_summary: str | None = None,
        reply_content: str | None = None,
        response: str | None = None,
    ) -> dict[str, Any]:
        reply_text = str(reply_content or response or "").strip()
        summary_text = str(completion_summary or "").strip()

        results: list[dict] = []
        all_affected: list = []
        prev_statuses: list[str] = []

        for tid in ids:
            err, task = self._check_auth(tid)
            if err:
                results.append({"task_id": tid, **err})
                continue

            needs_response = task.source_agent != task.target_agent
            if needs_response and not reply_text:
                results.append(
                    {
                        "task_id": tid,
                        "status": "error",
                        "error": f"Task {tid} is delegated from {task.source_agent.value}; reply_content is required",
                    }
                )
                continue

            try:
                previous_status = task.status.value
                affected = self._task_board.complete_task(
                    tid,
                    target_agent=self._agent_type,
                    session_id=task.session_id,
                )
                all_affected.extend(affected)
                prev_statuses.append(previous_status)
                results.append(
                    {
                        "task_id": tid,
                        "status": "ok",
                        "message": f"Task {tid} completed: {task.brief}",
                        "chain_affected": len(affected),
                    }
                )
            except ValueError as e:
                results.append({"task_id": tid, "status": "error", "error": str(e)})

        # Publish individual notifications — chain tasks have different
        # source/target agents and must be delivered separately.
        for i, task in enumerate(all_affected):
            await self._publish_task_update(task, "completed", prev_statuses[i] if i < len(prev_statuses) else None)

        # Send completion replies (one per chain root that needs it)
        auto_replied = await self._publish_completion_replies(all_affected, reply_text)

        ok_count = sum(1 for r in results if r.get("status") == "ok")
        result: dict[str, Any] = {
            "status": "ok" if ok_count else "error",
            "message": f"Completed {ok_count}/{len(ids)} tasks",
            "results": results,
            "auto_replied": auto_replied,
            "_ui_summary": summary_text or None,
            "_ui_detail": reply_text or None,
        }
        # Backward compat: single-ID success surfaces key fields at top level
        if len(ids) == 1 and ok_count == 1 and results:
            result["task_id"] = results[0]["task_id"]
            result["chain_affected"] = results[0]["chain_affected"]
            result["completion_summary"] = summary_text or None
        elif len(ids) == 1 and ok_count == 0 and results:
            result["error"] = results[0].get("error", "unknown error")
        return result

    # ------------------------------------------------------------------ #
    #  Notification helpers
    # ------------------------------------------------------------------ #

    async def _publish_task_update(
        self, task, action: str, previous_status: str | None = None
    ) -> None:
        msg = TaskUpdateMessage(
            task_id=task.task_id,
            action=action,
            source_agent=task.source_agent,
            target_agent=task.target_agent,
            brief=task.brief,
            previous_status=previous_status,
        )
        await self._bus.publish(msg)

    async def _publish_batch_task_update(
        self, tasks: list, action: str, previous_status: str | None = None
    ) -> None:
        """Publish a single batch notification covering multiple tasks."""
        if not tasks:
            return
        # For a single task, just use the normal path
        if len(tasks) == 1:
            await self._publish_task_update(tasks[0], action, previous_status)
            return

        # Build a combined brief
        briefs = [f"{t.task_id}: {t.brief}" for t in tasks[:10]]
        combined_brief = f"{len(tasks)} tasks — " + "; ".join(briefs)
        if len(tasks) > 10:
            combined_brief += f"; +{len(tasks) - 10} more"

        msg = TaskUpdateMessage(
            task_id=tasks[0].task_id,
            action=action,
            source_agent=tasks[0].source_agent,
            target_agent=tasks[0].target_agent,
            brief=combined_brief,
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

        await self._bus.publish(
            ReportMessage(
                agent_type=leaf.target_agent,
                task_id=leaf.task_id,
                report_type="reply",
                content=response,
            )
        )
        return 1
