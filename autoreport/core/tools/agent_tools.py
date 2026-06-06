"""Inter-agent communication tools.

SendToAgentTool: Main Agent dispatches tasks to sub-agents and waits for responses.
ReportIssueTool: Sub-agents report issues back to the Main Agent.
"""

import asyncio
from typing import Any

from loguru import logger

from ...interfaces.types import AgentFeedback, AgentResponse, AgentType, TaskUpdateMessage, UserMessage
from ..loops.bus import MessageBus
from .registry import Tool


class SendToAgentTool(Tool):
    """Send a task to a sub-agent and wait for its response.

    Only available to the Main Agent. Dispatches a coordination message
    to the specified sub-agent, waits for the response, and returns it.
    """

    name = "send_to_agent"
    description = (
        "Send a task instruction to a sub-agent. Use this to dispatch work to: "
        "theory, data_analysis, plotting, report. Keep the message minimal: "
        "task goal, input file locations, dependency, and explicit user constraints only. "
        "Do not include formulas, implementation steps, copied source content, "
        "output filenames, or quality rules the sub-agent already owns. "
        "Modes (choose one):\n"
        "- blocking=True (default): Wait for response, no task tracking.\n"
        "- blocking=False with task_items: Non-blocking, creates tracked tasks for waitlist/todolist.\n"
        "Returns the sub-agent's full response text."
    )

    def __init__(self, bus: MessageBus, task_board=None, timeout: int = 120, session_id_resolver=None):
        self._bus = bus
        self._task_board = task_board
        self._timeout = timeout
        self._session_id_resolver = session_id_resolver

    def _session_id(self) -> str | None:
        if callable(self._session_id_resolver):
            try:
                return self._session_id_resolver()
            except Exception:
                return None
        return None

    async def __call__(
        self,
        agent_type: str,
        content: str,
        task_items: list[dict] | None = None,
        blocking: bool = True,
    ) -> dict[str, Any]:
        """Send a task to a sub-agent.

        Args:
            agent_type: Target sub-agent type. One of: theory, data_analysis, plotting, report.
            content: Task instruction to send to the sub-agent.
            task_items: Optional list of task dicts with 'brief' (short UI text)
                for waitlist/todolist tracking.
            blocking: If True, wait for response. If False, return immediately after dispatch.

        Returns:
            Dictionary with agent_type, status, response content, and any feedback.
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
        if not isinstance(content, str):
            return {
                "status": "error",
                "error": f"Invalid content type: expected str, got {type(content).__name__}.",
            }

        agent_type = agent_type.strip()
        content = content.strip()
        if not agent_type:
            return {"status": "error", "error": "agent_type cannot be empty."}
        if not content:
            return {"status": "error", "error": "content cannot be empty."}

        try:
            target = AgentType(agent_type)
        except ValueError:
            valid = ", ".join(t.value for t in AgentType if t != AgentType.MAIN)
            return {
                "status": "error",
                "error": f"Unknown agent type '{agent_type}'. Valid: {valid}",
            }

        # Validate: blocking and task_items are mutually exclusive by design
        if blocking and task_items:
            return {
                "status": "error",
                "error": "blocking=True does not support task_items. Use blocking=False with task_items for tracked tasks.",
            }
        if not blocking and not task_items and self._task_board:
            return {
                "status": "error",
                "error": "blocking=False requires task_items when task_board is available. Provide task_items to track tasks.",
            }

        # --- Task items: create linked waitlist/todolist entries (non-blocking only) ---
        created_task_ids: list[str] = []
        if task_items and self._task_board:
            main_type = AgentType.MAIN
            for item in task_items:
                brief = str(
                    item.get("brief")
                    or item.get("task_brief")
                    or content[:80]
                )
                task = self._task_board.create_task(
                    source=main_type,
                    target=target,
                    brief=brief,
                    blocking=blocking,
                    session_id=self._session_id(),
                )
                created_task_ids.append(task.task_id)
            logger.info("SendToAgentTool: created tasks {}", created_task_ids)
            for task_id in created_task_ids:
                task = self._task_board.get_task(task_id)
                if task is not None:
                    await self._bus.publish(TaskUpdateMessage(
                        task_id=task.task_id,
                        action="created",
                        source_agent=task.source_agent,
                        target_agent=task.target_agent,
                        brief=task.brief,
                        previous_status=None,
                    ))

        # Non-blocking: return immediately after dispatch
        if not blocking:
            await self._bus.publish(UserMessage(
                content=content,
                agent_type=target,
                source="main_agent",
            ))
            logger.info("Main Agent dispatched non-blocking task to {}", target)
            result: dict[str, Any] = {
                "status": "delegated",
                "agent_type": target.value,
                "message": f"Task sent to {target.value} (non-blocking). "
                           "Agent will be notified on completion.",
            }
            if created_task_ids:
                result["task_ids"] = created_task_ids
            return result

        # Create future to wait for response
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        feedback_items: list[dict[str, str]] = []

        def _on_response(msg: Any) -> None:
            if not isinstance(msg, AgentResponse):
                return
            if msg.agent_type != target.value and msg.agent_type != target:
                return
            if msg.streaming:
                return
            if not future.done():
                future.set_result(msg.content)

        def _on_feedback(msg: Any) -> None:
            if not isinstance(msg, AgentFeedback):
                return
            if msg.agent_type != target.value and msg.agent_type != target:
                return
            feedback_items.append({
                "type": msg.feedback_type,
                "content": msg.content,
            })

        # Subscribe BEFORE publishing to avoid race condition
        self._bus.subscribe(AgentResponse, _on_response)
        self._bus.subscribe(AgentFeedback, _on_feedback)

        await self._bus.publish(UserMessage(
            content=content,
            agent_type=target,
            source="main_agent",
        ))

        logger.info("Main Agent dispatched task to {}", target)

        # Wait for response
        try:
            response_content = await asyncio.wait_for(future, timeout=self._timeout)
            result: dict[str, Any] = {
                "status": "success",
                "agent_type": target.value,
                "response": response_content,
            }
            if feedback_items:
                result["feedback"] = feedback_items
            if created_task_ids:
                result["task_ids"] = created_task_ids
            return result
        except asyncio.TimeoutError:
            result = {
                "status": "timeout",
                "agent_type": target.value,
                "error": f"Sub-agent did not respond within {self._timeout}s. "
                         "It may still be processing. Try again or use read to check its output.",
            }
            if feedback_items:
                result["feedback"] = feedback_items
            return result
        finally:
            self._bus.unsubscribe(AgentResponse, _on_response)
            self._bus.unsubscribe(AgentFeedback, _on_feedback)


class ReportIssueTool(Tool):
    """Report an issue to the Main Agent.

    Available to all sub-agents. Use this when prerequisites are missing,
    input data is malformed, or you need Main Agent intervention.
    """

    name = "report_issue"
    description = (
        "Report an issue to the Main Agent. Use when: prerequisites are missing, "
        "input data is malformed, another agent's output has quality problems, "
        "or you need Main Agent to coordinate a fix."
    )

    def __init__(self, bus: MessageBus, agent_type: AgentType, task_board=None, session_id_resolver=None):
        self._bus = bus
        self._agent_type = agent_type
        self._task_board = task_board
        self._session_id_resolver = session_id_resolver

    def _session_id(self) -> str | None:
        if callable(self._session_id_resolver):
            try:
                return self._session_id_resolver()
            except Exception:
                return None
        return None

    async def __call__(
        self,
        content: str,
        issue_type: str = "missing_data",
        request_task_for: str | None = None,
        task_brief: str = "",
        task_message: str | None = None,
    ) -> dict[str, Any]:
        """Report an issue to the Main Agent.

        Args:
            content: Detailed description of the issue. Be specific about what is
                missing, wrong, or needed.
            issue_type: Type of issue. One of: missing_data (prerequisites absent),
                quality (output is wrong/malformed), query (need clarification).
            request_task_for: Optional agent type to request a task for.
            task_brief: Short summary for UI list display (optional).
            task_message: Optional message that should be auto-dispatched to the
                requested target when routing sub -> main -> sub.

        Returns:
            Confirmation dictionary.
        """
        valid_types = {"missing_data", "quality", "query"}
        if issue_type not in valid_types:
            issue_type = "missing_data"

        requested_target: AgentType | None = None
        if request_task_for:
            try:
                requested_target = AgentType(request_task_for)
            except ValueError:
                requested_target = None

        # Create task if requested
        created_task_id: str | None = None
        dispatched_task_id: str | None = None
        brief_text = str(task_brief or "").strip()
        if request_task_for and brief_text and self._task_board:
            task_link_id = self._task_board._next_id()
            parent_task = self._task_board.create_task(
                source=self._agent_type,
                target=AgentType.MAIN,
                brief=brief_text,
                blocking=False,
                task_id=task_link_id,
                session_id=self._session_id(),
            )
            created_task_id = parent_task.task_id
            logger.info(
                "ReportIssueTool: {} created task {} for main coordination (requested_target={})",
                self._agent_type, parent_task.task_id, request_task_for,
            )
            await self._bus.publish(TaskUpdateMessage(
                task_id=parent_task.task_id,
                action="created",
                source_agent=parent_task.source_agent,
                target_agent=parent_task.target_agent,
                brief=parent_task.brief,
                previous_status=None,
            ))
            if requested_target and requested_target != AgentType.MAIN:
                child_task = self._task_board.create_task(
                    source=AgentType.MAIN,
                    target=requested_target,
                    brief=brief_text,
                    blocking=False,
                    task_id=task_link_id,
                    session_id=self._session_id(),
                )
                dispatched_task_id = child_task.task_id
                logger.info(
                    "ReportIssueTool: auto-dispatched child task {} from main to {}",
                    child_task.task_id, requested_target,
                )
                await self._bus.publish(TaskUpdateMessage(
                    task_id=child_task.task_id,
                    action="created",
                    source_agent=child_task.source_agent,
                    target_agent=child_task.target_agent,
                    brief=child_task.brief,
                    previous_status=None,
                ))
                dispatch_content = str(task_message or "").strip() or brief_text
                issue_context = content.strip()
                if issue_context and issue_context != dispatch_content:
                    dispatch_content = (
                        f"{dispatch_content}\n\n"
                        f"Context from {self._agent_type.value}: {issue_context}"
                    )
                await self._bus.publish(UserMessage(
                    content=dispatch_content,
                    agent_type=requested_target,
                    source="main_agent",
                ))

        await self._bus.publish(AgentFeedback(
            agent_type=self._agent_type,
            content=content,
            feedback_type=issue_type,
        ))

        logger.info(
            "{} reported issue (type={}): {}",
            self._agent_type, issue_type, content[:80],
        )

        result: dict[str, Any] = {
            "status": "reported",
            "agent_type": self._agent_type.value if isinstance(self._agent_type, AgentType) else str(self._agent_type),
            "issue_type": issue_type,
        }
        if created_task_id:
            result["task_id"] = created_task_id
            result["requested_target"] = (
                requested_target.value if requested_target else request_task_for
            )
        if dispatched_task_id:
            result["dispatched_task_id"] = dispatched_task_id
        return result
