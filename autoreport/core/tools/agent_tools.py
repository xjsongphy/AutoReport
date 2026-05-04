"""Inter-agent communication tools.

SendToAgentTool: Main Agent dispatches tasks to sub-agents and waits for responses.
ReportIssueTool: Sub-agents report issues back to the Main Agent.
"""

import asyncio
from typing import Any

from loguru import logger

from ...interfaces.types import AgentFeedback, AgentResponse, AgentType, UserMessage
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
        "theory, data_analysis, plotting, report. "
        "Optionally create tracked tasks with 'task_items' parameter for "
        "waitlist/todolist tracking. "
        "Set blocking=False for non-blocking delegation — the task will be "
        "tracked and you'll be notified when the sub-agent completes it. "
        "Returns the sub-agent's full response text."
    )

    def __init__(self, bus: MessageBus, task_board=None, timeout: int = 120):
        self._bus = bus
        self._task_board = task_board
        self._timeout = timeout

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
            task_items: Optional list of task dicts with 'description' keys for tracking.
            blocking: If True, wait for response. If False, return immediately after dispatch.

        Returns:
            Dictionary with agent_type, status, response content, and any feedback.
        """
        try:
            target = AgentType(agent_type)
        except ValueError:
            valid = ", ".join(t.value for t in AgentType if t != AgentType.MAIN)
            return {
                "status": "error",
                "error": f"Unknown agent type '{agent_type}'. Valid: {valid}",
            }

        # --- Task items: create linked waitlist/todolist entries ---
        created_task_ids: list[str] = []
        if task_items and self._task_board:
            main_type = AgentType.MAIN
            for item in task_items:
                desc = str(item.get("description", content[:120]))
                task = self._task_board.create_task(
                    source=main_type,
                    target=target,
                    description=desc,
                    blocking=blocking,
                )
                created_task_ids.append(task.task_id)
            logger.info("SendToAgentTool: created tasks {}", created_task_ids)

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
                         "It may still be processing. Try again or use read_file to check its output.",
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

    def __init__(self, bus: MessageBus, agent_type: AgentType, task_board=None):
        self._bus = bus
        self._agent_type = agent_type
        self._task_board = task_board

    async def __call__(
        self,
        content: str,
        issue_type: str = "missing_data",
        request_task_for: str | None = None,
        task_description: str | None = None,
    ) -> dict[str, Any]:
        """Report an issue to the Main Agent.

        Args:
            content: Detailed description of the issue. Be specific about what is
                missing, wrong, or needed.
            issue_type: Type of issue. One of: missing_data (prerequisites absent),
                quality (output is wrong/malformed), query (need clarification).
            request_task_for: Optional agent type to request a task for.
            task_description: Description for the requested task.

        Returns:
            Confirmation dictionary.
        """
        valid_types = {"missing_data", "quality", "query"}
        if issue_type not in valid_types:
            issue_type = "missing_data"

        # Create task if requested
        created_task_id: str | None = None
        if request_task_for and task_description and self._task_board:
            try:
                target = AgentType(request_task_for)
            except ValueError:
                target = AgentType.MAIN
            task = self._task_board.create_task(
                source=self._agent_type,
                target=target,
                description=task_description,
                blocking=False,
            )
            created_task_id = task.task_id
            logger.info(
                "ReportIssueTool: {} created task {} for delegation to {}",
                self._agent_type, task.task_id, request_task_for,
            )

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
            result["requested_target"] = request_task_for
        return result
