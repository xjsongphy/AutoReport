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
        "Send a task instruction to a sub-agent and wait for its response. "
        "Use this to dispatch work to: theory, data_analysis, plotting, report. "
        "Returns the sub-agent's full response text."
    )

    def __init__(self, bus: MessageBus, timeout: int = 120):
        self._bus = bus
        self._timeout = timeout

    async def __call__(
        self,
        agent_type: str,
        content: str,
    ) -> dict[str, Any]:
        """Send a task to a sub-agent.

        Args:
            agent_type: Target sub-agent type. One of: theory, data_analysis, plotting, report.
            content: Task instruction to send to the sub-agent.

        Returns:
            Dictionary with agent_type, status, and response content.
        """
        try:
            target = AgentType(agent_type)
        except ValueError:
            valid = ", ".join(t.value for t in AgentType if t != AgentType.MAIN)
            return {
                "status": "error",
                "error": f"Unknown agent type '{agent_type}'. Valid: {valid}",
            }

        # Create future to wait for response
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()

        def _on_response(msg: Any) -> None:
            if not isinstance(msg, AgentResponse):
                return
            if msg.agent_type != target.value and msg.agent_type != target:
                return
            if msg.streaming:
                return
            if not future.done():
                future.set_result(msg.content)

        # Subscribe and send
        self._bus.subscribe(AgentResponse, _on_response)

        await self._bus.publish(UserMessage(
            content=content,
            agent_type=target,
            source="main_agent",
        ))

        logger.info("Main Agent dispatched task to {}", target)

        # Wait for response
        try:
            response_content = await asyncio.wait_for(future, timeout=self._timeout)
            return {
                "status": "success",
                "agent_type": target.value,
                "response": response_content,
            }
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "agent_type": target.value,
                "error": f"Sub-agent did not respond within {self._timeout}s. "
                         "It may still be processing. Try again or use read_file to check its output.",
            }
        finally:
            self._bus.unsubscribe(AgentResponse, _on_response)


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

    def __init__(self, bus: MessageBus, agent_type: AgentType):
        self._bus = bus
        self._agent_type = agent_type

    async def __call__(
        self,
        content: str,
        issue_type: str = "missing_data",
    ) -> dict[str, Any]:
        """Report an issue to the Main Agent.

        Args:
            content: Detailed description of the issue. Be specific about what is
                missing, wrong, or needed.
            issue_type: Type of issue. One of: missing_data (prerequisites absent),
                quality (output is wrong/malformed), query (need clarification).

        Returns:
            Confirmation dictionary.
        """
        valid_types = {"missing_data", "quality", "query"}
        if issue_type not in valid_types:
            issue_type = "missing_data"

        await self._bus.publish(AgentFeedback(
            agent_type=self._agent_type,
            content=content,
            feedback_type=issue_type,
        ))

        logger.info(
            "{} reported issue (type={}): {}",
            self._agent_type, issue_type, content[:80],
        )

        return {
            "status": "reported",
            "agent_type": self._agent_type.value if isinstance(self._agent_type, AgentType) else str(self._agent_type),
            "issue_type": issue_type,
        }
