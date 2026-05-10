"""Tests for checkpoint tools — CreateCheckpointTool, ListCheckpointsTool, RollbackCheckpointTool."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from autoreport.core.checkpoints import CheckpointManager
from autoreport.core.tools.checkpoint_tool import (
    CreateCheckpointTool,
    ListCheckpointsTool,
    RollbackCheckpointTool,
)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    workspace = Path(tempfile.mkdtemp())

    for dir_name in ["data", "data/processed", "references", "theory", "code", "tex"]:
        (workspace / dir_name).mkdir(parents=True, exist_ok=True)

    (workspace / "data" / "processed" / "result.json").write_text('{"x": 1}')
    (workspace / "theory" / "test.md").write_text("# Theory\n")

    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture
def manager(temp_workspace):
    return CheckpointManager(temp_workspace)


# ── CreateCheckpointTool ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_checkpoint_tool_basic(manager):
    tool = CreateCheckpointTool(manager, "main")
    result = await tool(description="manual snapshot")

    assert "检查点已创建" in result
    assert "manual snapshot" in result

    cp_id = result.split(": ")[1].split(" ")[0]
    cp = manager.get_checkpoint("main", cp_id)
    assert cp is not None
    assert cp.source == "manual"
    assert cp.description == "manual snapshot"


@pytest.mark.asyncio
async def test_create_checkpoint_tool_per_agent(manager):
    tool = CreateCheckpointTool(manager, "theory")
    result = await tool(description="before derivation")

    assert "检查点已创建" in result

    cp_id = result.split(": ")[1].split(" ")[0]
    cp = manager.get_checkpoint("theory", cp_id)
    assert cp is not None
    assert cp.agent_type == "theory"
    assert "theory/test.md" in cp.file_states


@pytest.mark.asyncio
async def test_create_checkpoint_tool_properties():
    mgr = AsyncMock()
    mgr.create_checkpoint = AsyncMock(return_value="cp_test_0001_20260101_000000")

    tool = CreateCheckpointTool(mgr, "test")
    assert tool.name == "create_checkpoint"
    assert "检查点" in tool.description
    assert "description" in tool.parameters["properties"]
    assert tool.parameters["required"] == ["description"]


# ── ListCheckpointsTool ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_checkpoints_empty(manager):
    tool = ListCheckpointsTool(manager, "plotting")
    result = await tool()
    assert result == "当前没有检查点。"


@pytest.mark.asyncio
async def test_list_checkpoints_with_data(manager):
    await manager.create_checkpoint(agent_type="main", description="first")
    await manager.create_checkpoint(agent_type="main", description="second")

    tool = ListCheckpointsTool(manager, "main")
    result = await tool()

    assert "共 2 个检查点" in result
    assert "first" in result
    assert "second" in result


@pytest.mark.asyncio
async def test_list_checkpoints_limits_to_10(manager):
    for i in range(12):
        await manager.create_checkpoint(agent_type="main", description=f"cp{i}")

    tool = ListCheckpointsTool(manager, "main")
    result = await tool()

    assert "共 12 个检查点" in result
    assert "还有 2 个更早" in result


@pytest.mark.asyncio
async def test_list_checkpoints_agent_isolation(manager):
    await manager.create_checkpoint(agent_type="main", description="main cp")
    await manager.create_checkpoint(agent_type="theory", description="theory cp")

    main_result = await ListCheckpointsTool(manager, "main")()
    theory_result = await ListCheckpointsTool(manager, "theory")()

    assert "main cp" in main_result
    assert "theory cp" not in main_result
    assert "theory cp" in theory_result


@pytest.mark.asyncio
async def test_list_checkpoints_tool_properties():
    tool = ListCheckpointsTool(AsyncMock(), "test")
    assert tool.name == "list_checkpoints"
    assert tool.parameters["required"] == []


# ── RollbackCheckpointTool ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rollback_main_agent(manager, temp_workspace):
    # Create checkpoint, modify file, rollback
    cp_id = await manager.create_checkpoint(
        agent_type="main", description="before change"
    )

    result_file = temp_workspace / "theory" / "test.md"
    original = result_file.read_text()
    result_file.write_text("# Modified\n")

    tool = RollbackCheckpointTool(manager, "main")
    result = await tool(checkpoint_id=cp_id)

    assert "已回滚" in result
    assert "恢复了" in result
    assert result_file.read_text() == original


@pytest.mark.asyncio
async def test_rollback_sub_agent_rejected(manager):
    tool = RollbackCheckpointTool(manager, "data_analysis")
    result = await tool(checkpoint_id="any_id")

    assert "错误" in result
    assert "仅主 Agent" in result


@pytest.mark.asyncio
async def test_rollback_invalid_checkpoint_id(manager):
    tool = RollbackCheckpointTool(manager, "main")
    result = await tool(checkpoint_id="nonexistent_id")

    assert "回滚失败" in result


@pytest.mark.asyncio
async def test_rollback_creates_post_checkpoint(manager, temp_workspace):
    cp_id = await manager.create_checkpoint(
        agent_type="main", description="pre-rollback"
    )

    tool = RollbackCheckpointTool(manager, "main")
    result = await tool(checkpoint_id=cp_id)

    # Post-rollback checkpoint should exist
    cps = manager.list_checkpoints("main")
    assert len(cps) == 2
    post_cp = cps[-1]
    assert post_cp.source == "rollback"
    assert "回滚" in post_cp.description


@pytest.mark.asyncio
async def test_rollback_tool_properties():
    tool = RollbackCheckpointTool(AsyncMock(), "main")
    assert tool.name == "rollback_checkpoint"
    assert "checkpoint_id" in tool.parameters["properties"]
    assert tool.parameters["required"] == ["checkpoint_id"]
