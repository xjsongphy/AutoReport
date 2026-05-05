"""Checkpoint tools — per-agent state snapshots for rollback.

Agents can create and list checkpoints.  Only the Main Agent can trigger
rollbacks (they affect the workspace globally).
"""

from pathlib import Path
from typing import Any

from loguru import logger


class CreateCheckpointTool:
    """Create a checkpoint for the calling agent.

    Captures the current file state of the agent's write directory so the
    agent can roll back to this point later.  Called automatically before
    each message is processed; can also be called manually.
    """

    def __init__(self, checkpoint_manager, agent_type: str):
        self._mgr = checkpoint_manager
        self._agent_type = agent_type

    @property
    def name(self) -> str:
        return "create_checkpoint"

    @property
    def description(self) -> str:
        return (
            "创建一个检查点，保存当前工作目录的文件状态。"
            "在重要操作（如写入文件、运行代码）前调用，以便出错时回滚。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "检查点描述（例如：'在生成图表前'、'开始数据分析'）",
                },
            },
            "required": ["description"],
        }

    async def __call__(self, description: str) -> str:
        cp_id = await self._mgr.create_checkpoint(
            agent_type=self._agent_type,
            description=description,
            source="manual",
        )
        logger.info("Agent {} created checkpoint {}: {}", self._agent_type, cp_id, description)
        return f"检查点已创建: {cp_id} ({description})"


class ListCheckpointsTool:
    """List all checkpoints for the calling agent."""

    def __init__(self, checkpoint_manager, agent_type: str):
        self._mgr = checkpoint_manager
        self._agent_type = agent_type

    @property
    def name(self) -> str:
        return "list_checkpoints"

    @property
    def description(self) -> str:
        return "列出当前 Agent 的所有检查点。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def __call__(self) -> str:
        cps = self._mgr.list_checkpoints(self._agent_type)
        if not cps:
            return "当前没有检查点。"

        lines = [f"共 {len(cps)} 个检查点:"]
        for cp in cps[-10:]:  # Show most recent 10
            lines.append(
                f"  - {cp.id} (epoch={cp.epoch}) — {cp.description} "
                f"[{cp.timestamp[:19]}]"
            )
        if len(cps) > 10:
            lines.append(f"  ... 还有 {len(cps) - 10} 个更早的检查点")
        return "\n".join(lines)


class RollbackCheckpointTool:
    """Rollback to a specific checkpoint.  Main Agent only.

    Restores all files captured at the checkpoint.  After rollback, a new
    checkpoint is automatically created to mark the rollback point.
    """

    def __init__(self, checkpoint_manager, agent_type: str):
        self._mgr = checkpoint_manager
        self._agent_type = agent_type

    @property
    def name(self) -> str:
        return "rollback_checkpoint"

    @property
    def description(self) -> str:
        return (
            "回滚到指定的检查点。恢复该检查点时的所有文件内容。"
            "回滚后会自动创建一个新检查点。仅主 Agent 可用。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "checkpoint_id": {
                    "type": "string",
                    "description": "要回滚到的检查点 ID（从 list_checkpoints 获取）",
                },
            },
            "required": ["checkpoint_id"],
        }

    async def __call__(self, checkpoint_id: str) -> str:
        if self._agent_type != "main":
            return "错误: 仅主 Agent 可以执行回滚操作。"

        try:
            restored = await self._mgr.rollback(self._agent_type, checkpoint_id)
            # Create a post-rollback checkpoint
            new_id = await self._mgr.create_checkpoint(
                agent_type=self._agent_type,
                description=f"回滚到 {checkpoint_id} 之后",
                source="rollback",
            )
            return (
                f"已回滚到检查点 {checkpoint_id}，恢复了 {restored} 个文件。\n"
                f"新检查点: {new_id}"
            )
        except ValueError as e:
            return f"回滚失败: {e}"
