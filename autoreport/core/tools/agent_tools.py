"""Inter-agent communication tools.

SendToAgentTool: Main Agent dispatches tasks to sub-agents and waits for their respond.
RespondTool: Sub-agents respond with the outcome (reply/blocked) of a Main-dispatched task.
"""

import asyncio
import uuid
from typing import Any

from loguru import logger

from ...interfaces.types import (
    AgentResponse,
    AgentStatus,
    AgentType,
    ReportMessage,
    StatusChange,
    TaskStatus,
    TaskUpdateMessage,
    UserMessage,
)
from ..loops.bus import MessageBus
from .registry import Tool
from .session_utils import resolve_session_id


class SendToAgentTool(Tool):
    """Dispatch a task to a sub-agent and wait for its `respond`.

    Only available to the Main Agent. Always creates (or, for re-dispatch,
    reuses) a tracked task. blocking=True (default) waits for the sub-agent's
    `respond`; blocking=False returns immediately and the sub-agent's later
    `respond` updates the task + notifies Main.
    """

    name = "send_to_agent"
    description = (
        "Send a task instruction to a sub-agent. Use this to dispatch work to: "
        "theory, data_analysis, plotting, report. Keep the message minimal: "
        "summary (short visible task summary) plus content (full task detail: "
        "task goal, input file locations, dependency, and explicit user constraints only). "
        "Do not include formulas, implementation steps, copied source content, "
        "output filenames, or quality rules the sub-agent already owns. "
        "summary is required and must be non-empty; content is required and must be non-empty. "
        "Modes (choose one):\n"
        "- blocking=True (default): Wait for the sub-agent's `respond` (reply or blocked).\n"
        "- blocking=False: Return immediately; the sub-agent's later `respond` notifies you.\n"
        "task_id: omit on first dispatch; pass an existing task_id to RE-DISPATCH a "
        "previously blocked task (resets it to in_progress)."
    )

    def __init__(self, bus: MessageBus, task_board=None, timeout: int = 120, session_id_resolver=None):
        self._bus = bus
        self._task_board = task_board
        self._timeout = timeout  # wall-clock fallback cap for the liveness wait
        self._session_id_resolver = session_id_resolver

    def _session_id(self) -> str | None:
        return resolve_session_id(self._session_id_resolver)

    @staticmethod
    def _clean_required_text(value: Any, field_name: str) -> tuple[str | None, dict[str, str] | None]:
        if not isinstance(value, str):
            return None, {
                "status": "error",
                "error": f"Invalid {field_name} type: expected str, got {type(value).__name__}.",
            }
        text = value.strip()
        if not text:
            return None, {"status": "error", "error": f"{field_name} cannot be empty."}
        if field_name == "summary" and SendToAgentTool._is_route_placeholder_summary(text):
            return None, {
                "status": "error",
                "error": (
                    "summary must describe the task outcome or blocker, not the message route."
                ),
            }
        return text, None

    @staticmethod
    def _is_route_placeholder_summary(text: str) -> bool:
        normalized = " ".join(str(text or "").strip().lower().replace("_", " ").split())
        route_placeholders = {
            "sub to main",
            "agent to main",
            "theory to main",
            "data analysis to main",
            "data-analysis to main",
            "plotting to main",
            "report to main",
            "main to sub",
            "main to theory",
            "main to data analysis",
            "main to data-analysis",
            "main to plotting",
            "main to report",
        }
        return normalized in route_placeholders

    async def __call__(
        self,
        agent_type: str,
        summary: str,
        content: str,
        task_items: list[dict] | None = None,
        blocking: bool = True,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a task to a sub-agent.

        Args:
            agent_type: Target sub-agent type. One of: theory, data_analysis, plotting, report.
            summary: Short visible task summary for bubbles and task context.
            content: Full task instruction to send to the sub-agent.
            task_items: Optional list of task dicts ('brief' and optionally 'description')
                for waitlist/todolist tracking. Used only when creating a new task.
            blocking: If True, wait for the sub-agent's report. If False, return immediately.
            task_id: Existing task_id to re-dispatch (resets BLOCKED/COMPLETED -> in_progress).

        Returns:
            Dictionary with agent_type, status, response content, and task_id.
        """
        # Defensive validation: surface clear input errors instead of
        # propagating obscure attribute/type exceptions from downstream logic.
        if not isinstance(agent_type, str):
            return {
                "status": "error",
                "error": (
                    f"Invalid agent_type type: expected str, got {type(agent_type).__name__}. "
                    "Use one of: theory, data_analysis, plotting, report."
                ),
            }
        summary, error = self._clean_required_text(summary, "summary")
        if error is not None:
            return error
        content, error = self._clean_required_text(content, "content")
        if error is not None:
            return error

        agent_type = agent_type.strip()
        if not agent_type:
            return {"status": "error", "error": "agent_type cannot be empty."}

        try:
            target = AgentType(agent_type)
        except ValueError:
            valid = ", ".join(t.value for t in AgentType if t != AgentType.MAIN)
            return {
                "status": "error",
                "error": f"Unknown agent type '{agent_type}'. Valid: {valid}",
            }

        request_summary = summary
        sid = self._session_id()

        # --- Create or re-dispatch task ---
        if task_id and self._task_board is not None:
            existing = self._task_board.get_task(
                task_id, target_agent=target, active_only=False, session_id=sid
            )
            if existing is None:
                return {
                    "status": "error",
                    "error": f"task_id {task_id} not found for {target.value}",
                }
            # Re-dispatch: reset the whole chain (target + sources) back to in_progress.
            for t in self._task_board.get_tasks_by_id(task_id):
                if t.status in (
                    TaskStatus.BLOCKED,
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                ):
                    t.status = TaskStatus.IN_PROGRESS
                    t.completed_at = None
            await self._bus.publish(TaskUpdateMessage(
                task_id=task_id,
                action="started",
                source_agent=AgentType.MAIN,
                target_agent=target,
                brief=existing.brief,
            ))
        elif self._task_board is not None:
            item = task_items[0] if task_items else {}
            brief = (
                str(item.get("brief") or item.get("task_brief") or "").strip()
                or summary[:30]
            )
            new_task = self._task_board.create_task(
                source=AgentType.MAIN,
                target=target,
                brief=brief,
                blocking=blocking,
                session_id=sid,
            )
            task_id = new_task.task_id
            await self._bus.publish(TaskUpdateMessage(
                task_id=task_id,
                action="created",
                source_agent=new_task.source_agent,
                target_agent=new_task.target_agent,
                brief=new_task.brief,
                previous_status=None,
            ))

        # Non-blocking: dispatch and return immediately
        if not blocking:
            await self._bus.publish(UserMessage(
                content=content,
                summary=summary,
                agent_type=target,
                source="main_agent",
            ))
            logger.info("Main Agent dispatched non-blocking task {} to {}", task_id, target)
            result: dict[str, Any] = {
                "status": "delegated",
                "agent_type": target.value,
                "blocking": False,
                "task_id": task_id,
                "summary": summary,
                "content": content,
                "request_summary": request_summary,
                "message": f"Task sent to {target.value} (non-blocking). "
                           "Agent will be notified on completion.",
            }
            return result

        # --- Blocking: wait for the sub-agent's ReportMessage on this task ---
        # The report IS the reply: type="reply" -> success; else -> blocked.
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ReportMessage] = loop.create_future()

        def _on_report(msg: Any) -> None:
            if not isinstance(msg, ReportMessage):
                return
            if msg.agent_type != target or msg.task_id != task_id:
                return
            if not future.done():
                future.set_result(msg)

        self._bus.subscribe(ReportMessage, _on_report)

        # Prefix with "blocking:" so agent_loop's auto-notify suppression still
        # recognizes this dispatch (the auto-notify path is removed in a later task,
        # but the prefix is harmless and keeps the suppression intact meanwhile).
        dispatch_message_id = f"blocking:{task_id}"
        await self._bus.publish(UserMessage(
            content=content,
            summary=summary,
            agent_type=target,
            source="main_agent",
            message_id=dispatch_message_id,
        ))

        logger.info("Main Agent dispatched task {} to {} (blocking)", task_id, target)

        try:
            report = await self._await_with_liveness(future, target, loop)
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "agent_type": target.value,
                "task_id": task_id,
                "summary": summary,
                "content": content,
                "request_summary": request_summary,
                "error": "Sub-agent did not report within the liveness budget. "
                         "It may still be processing — try again or read its output.",
            }
        finally:
            self._bus.unsubscribe(ReportMessage, _on_report)

        if report.report_type == "reply":
            return {
                "status": "success",
                "agent_type": target.value,
                "task_id": task_id,
                "blocking": True,
                "summary": summary,
                "content": content,
                "request_summary": request_summary,
                "response_summary": report.summary,
                "response": report.content,
            }
        return {
            "status": "blocked",
            "agent_type": target.value,
            "task_id": task_id,
            "blocking": True,
            "block_type": report.report_type,
            "summary": summary,
            "content": content,
            "request_summary": request_summary,
            "response_summary": report.summary,
            "response": report.content,
            "error": f"Sub-agent responded {report.report_type}: {report.content}",
        }

    async def _await_with_liveness(self, future, target, loop) -> ReportMessage:
        """Wait for future, counting only target IDLE/ERROR time (no-progress timeout).

        Subscribes to StatusChange from the target: THINKING/RUNNING_TOOL pauses
        the idle timer (busy != timeout); IDLE/ERROR arms/re-arms it. A wall-clock
        cap (4x timeout) bounds total wait so a never-reporting turn still resolves.
        """
        idle_budget = 60
        wall_cap = self._timeout * 4
        idle_handle: asyncio.TimerHandle | None = None
        wall_deadline = loop.time() + wall_cap

        if future.done():
            return await future

        def _fire_idle() -> None:
            if not future.done():
                future.set_exception(asyncio.TimeoutError())

        def arm_idle() -> None:
            nonlocal idle_handle
            if idle_handle:
                idle_handle.cancel()
            idle_handle = loop.call_later(idle_budget, _fire_idle)

        def _on_status(msg: Any) -> None:
            if not isinstance(msg, StatusChange) or msg.agent_type != target or future.done():
                return
            if msg.status in (AgentStatus.THINKING, AgentStatus.RUNNING_TOOL):
                if idle_handle:
                    idle_handle.cancel()
            else:  # IDLE / ERROR / DEBUG_MODE
                arm_idle()

        self._bus.subscribe(StatusChange, _on_status)
        arm_idle()  # target starts IDLE until it picks up the message
        try:
            while not future.done():
                try:
                    return await asyncio.wait_for(asyncio.shield(future), timeout=1.0)
                except asyncio.TimeoutError:
                    if loop.time() > wall_deadline:
                        raise
        finally:
            if idle_handle:
                idle_handle.cancel()
            self._bus.unsubscribe(StatusChange, _on_status)


class RespondTool(Tool):
    """Respond to Main with the outcome of a Main-dispatched task.

    Available to all sub-agents. This is the ONLY way to finish a task
    dispatched by Main. Required: a sub-agent MUST call `respond` before
    its turn can end on a Main-dispatched task (enforced by AgentLoop).

    - type="reply": task COMPLETED. content = final response to Main.
    - type="missing_data" | "quality": task BLOCKED. content = what is
      needed / what is wrong. Main must resolve before it can stop.
    """

    name = "respond"
    description = (
        "Respond to Main with the outcome of a task Main dispatched to you. This is the ONLY "
        "way to finish such a task — you MUST call it before stopping.\n"
        "summary is required and must be a concise visible summary of the result/blocker; "
        "content is required and must contain the full response details.\n"
        "Types:\n"
        "- 'reply': you finished. summary = short outcome; content = final response (results, file paths).\n"
        "- 'missing_data': you cannot proceed because an input is missing. summary = short blocker; content = exactly what is missing and where it should be.\n"
        "- 'quality': you cannot proceed because a dependency's output is wrong. summary = short issue; content = what is wrong and where.\n"
        "Do NOT use this to ask the user questions — make a reasonable assumption or report missing_data to Main."
    )

    _VALID_TYPES = ("reply", "missing_data", "quality")

    def __init__(self, bus: MessageBus, agent_type: AgentType, task_board=None, session_id_resolver=None):
        self._bus = bus
        self._agent_type = agent_type
        self._task_board = task_board
        self._session_id_resolver = session_id_resolver

    def _session_id(self) -> str | None:
        return resolve_session_id(self._session_id_resolver)

    def _find_assigned_task(self, task_id: str):
        if self._task_board is None:
            return None
        sid = self._session_id()
        task = self._task_board.get_task(
            task_id,
            target_agent=self._agent_type,
            active_only=False,
            session_id=sid,
        )
        if task is not None:
            return task
        return self._task_board.get_task(
            task_id,
            target_agent=self._agent_type,
            active_only=False,
        )

    async def __call__(self, task_id: str, type: str, summary: str, content: str) -> dict[str, Any]:
        """Report outcome of a Main-dispatched task.

        Args:
            task_id: The task you are reporting on (shown in your [当前任务] context).
            type: One of reply | missing_data | quality.
            summary: Short visible summary for Main's coordination bubble.
            content: reply -> final response; missing_data/quality -> what is needed/wrong.

        Returns:
            Result dictionary.
        """
        report_type = str(type).strip()
        if report_type not in self._VALID_TYPES:
            return {"status": "error", "error": f"Unknown report type '{type}'. Valid: {', '.join(self._VALID_TYPES)}"}

        if not task_id:
            return {"status": "error", "error": "task_id is required"}

        summary, error = SendToAgentTool._clean_required_text(summary, "summary")
        if error is not None:
            return error
        content, error = SendToAgentTool._clean_required_text(content, "content")
        if error is not None:
            return error

        sid = self._session_id()
        if self._task_board is not None:
            task = self._find_assigned_task(task_id)
            if task is None:
                any_task = (
                    self._task_board.get_task(task_id, active_only=False, session_id=sid)
                    or self._task_board.get_task(task_id, active_only=False)
                )
                if any_task is None:
                    return {"status": "error", "error": f"Task {task_id} not found"}
                return {"status": "error", "error": f"Task {task_id} is not assigned to you"}
            sid = task.session_id

        # Update task status + chain (reuses TaskBoard logic)
        affected: list = []
        if self._task_board is not None:
            try:
                if report_type == "reply":
                    affected = self._task_board.complete_task(task_id, target_agent=self._agent_type, session_id=sid)
                    action = "completed"
                else:
                    affected = self._task_board.block_task(task_id, target_agent=self._agent_type, session_id=sid)
                    action = "blocked"
            except ValueError as e:
                if report_type == "reply" and task is not None and task.status == TaskStatus.COMPLETED:
                    affected = []
                    action = "completed"
                elif report_type != "reply" and task is not None and task.status == TaskStatus.BLOCKED:
                    affected = []
                    action = "blocked"
                else:
                    return {"status": "error", "error": str(e)}

            # Notify UI task board (existing path)
            for t in affected:
                await self._bus.publish(TaskUpdateMessage(
                    task_id=t.task_id,
                    action=action,
                    source_agent=t.source_agent,
                    target_agent=t.target_agent,
                    brief=t.brief,
                ))

        # Single reply channel: resolves Main's wait + marks this loop's turn reported
        await self._bus.publish(ReportMessage(
            agent_type=self._agent_type,
            task_id=task_id,
            report_type=report_type,
            summary=summary,
            content=str(content or ""),
        ))

        logger.info("{} responded {} for task {}", self._agent_type, report_type, task_id)
        return {
            "status": "ok",
            "task_id": task_id,
            "report_type": report_type,
            "summary": summary,
            "content": str(content or ""),
            "message": f"Reported {report_type} for task {task_id}",
        }
