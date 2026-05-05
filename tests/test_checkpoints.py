"""Tests for per-agent checkpoint management."""

import shutil
import tempfile
from pathlib import Path

import pytest

from autoreport.core.checkpoints import CheckpointData, CheckpointManager, FileState


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    workspace = Path(tempfile.mkdtemp())

    # Create project structure
    for dir_name in ["data", "data/processed", "references", "theory", "code", "tex"]:
        (workspace / dir_name).mkdir(parents=True, exist_ok=True)

    # Create some test files
    (workspace / "data" / "test.csv").write_text("col1,col2\n1,2\n")
    (workspace / "data" / "processed" / "result.json").write_text('{"x": 1}')
    (workspace / "theory" / "test.md").write_text("# Theory\n\nSome content.\n")

    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


# ── Core API tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_checkpoint(temp_workspace):
    """Test creating a per-agent checkpoint."""
    manager = CheckpointManager(temp_workspace)

    cp_id = await manager.create_checkpoint(
        agent_type="main",
        description="Initial state",
    )

    assert cp_id is not None
    assert cp_id.startswith("cp_main_")

    cp = manager.get_checkpoint("main", cp_id)
    assert cp is not None
    assert cp.description == "Initial state"
    assert cp.agent_type == "main"
    assert cp.epoch == 1


@pytest.mark.asyncio
async def test_checkpoint_captures_files(temp_workspace):
    """Test that checkpoint captures only the agent's write directory."""
    manager = CheckpointManager(temp_workspace)

    cp_id = await manager.create_checkpoint(
        agent_type="data_analysis",
        description="Pre-processing",
    )

    cp = manager.get_checkpoint("data_analysis", cp_id)

    # data_analysis only watches data/processed/
    assert "data/processed/result.json" in cp.file_states
    # Should NOT include files from other agents' dirs
    assert "theory/test.md" not in cp.file_states
    assert "data/test.csv" not in cp.file_states


@pytest.mark.asyncio
async def test_main_agent_captures_all(temp_workspace):
    """Main agent captures files from all directories."""
    manager = CheckpointManager(temp_workspace)

    cp_id = await manager.create_checkpoint(
        agent_type="main",
        description="Full snapshot",
    )

    cp = manager.get_checkpoint("main", cp_id)
    assert "data/processed/result.json" in cp.file_states
    assert "theory/test.md" in cp.file_states
    assert "data/test.csv" in cp.file_states


@pytest.mark.asyncio
async def test_per_agent_isolation(temp_workspace):
    """Checkpoints from different agents don't mix."""
    manager = CheckpointManager(temp_workspace)

    await manager.create_checkpoint(agent_type="main", description="M1")
    await manager.create_checkpoint(agent_type="theory", description="T1")
    await manager.create_checkpoint(agent_type="main", description="M2")

    main_cps = manager.list_checkpoints("main")
    theory_cps = manager.list_checkpoints("theory")

    assert len(main_cps) == 2
    assert len(theory_cps) == 1
    assert theory_cps[0].description == "T1"


@pytest.mark.asyncio
async def test_list_checkpoints(temp_workspace):
    """Test listing checkpoints for a specific agent."""
    manager = CheckpointManager(temp_workspace)

    await manager.create_checkpoint(agent_type="plotting", description="P1")
    await manager.create_checkpoint(agent_type="plotting", description="P2")
    await manager.create_checkpoint(agent_type="plotting", description="P3")

    cps = manager.list_checkpoints("plotting")
    assert len(cps) == 3
    # Should be sorted by epoch ascending
    assert cps[0].description == "P1"
    assert cps[2].description == "P3"


@pytest.mark.asyncio
async def test_get_latest(temp_workspace):
    """Test getting the latest checkpoint for an agent."""
    manager = CheckpointManager(temp_workspace)

    await manager.create_checkpoint(agent_type="report", description="First")
    await manager.create_checkpoint(agent_type="report", description="Second")

    latest = manager.get_latest("report")
    assert latest is not None
    assert latest.description == "Second"
    assert latest.epoch == 2


@pytest.mark.asyncio
async def test_clear_old(temp_workspace):
    """Test clearing old checkpoints per agent."""
    manager = CheckpointManager(temp_workspace)

    for i in range(5):
        await manager.create_checkpoint(agent_type="theory", description=f"T{i}")

    removed = manager.clear_old("theory", keep=2)
    assert removed == 3
    remaining = manager.list_checkpoints("theory")
    assert len(remaining) == 2


@pytest.mark.asyncio
async def test_id_generation(temp_workspace):
    """Checkpoint IDs are unique and contain agent type."""
    manager = CheckpointManager(temp_workspace)

    id1 = await manager.create_checkpoint(agent_type="main", description="First")
    id2 = await manager.create_checkpoint(agent_type="main", description="Second")

    assert id1 != id2
    assert id1.startswith("cp_main_")
    assert id2.startswith("cp_main_")


@pytest.mark.asyncio
async def test_rollback_restores_files(temp_workspace):
    """Rollback should restore file content from checkpoint snapshot."""
    manager = CheckpointManager(temp_workspace)

    # Create initial state
    await manager.create_checkpoint(
        agent_type="data_analysis",
        description="Before modification",
    )

    # Modify a file
    result_file = temp_workspace / "data" / "processed" / "result.json"
    original = result_file.read_text()
    result_file.write_text('{"modified": true}')

    # Rollback
    cps = manager.list_checkpoints("data_analysis")
    restored = await manager.rollback("data_analysis", cps[0].id)
    assert restored == 1
    assert result_file.read_text() == original


@pytest.mark.asyncio
async def test_epoch_monotonic(temp_workspace):
    """Epochs are monotonically increasing per agent."""
    manager = CheckpointManager(temp_workspace)

    cp1 = await manager.create_checkpoint(agent_type="main", description="A")
    cp2 = await manager.create_checkpoint(agent_type="main", description="B")
    cp3 = await manager.create_checkpoint(agent_type="main", description="C")

    e1 = manager.get_checkpoint("main", cp1).epoch
    e2 = manager.get_checkpoint("main", cp2).epoch
    e3 = manager.get_checkpoint("main", cp3).epoch

    assert e1 < e2 < e3


@pytest.mark.asyncio
async def test_empty_agent_no_checkpoints(temp_workspace):
    """An agent with no checkpoints returns empty list and None latest."""
    manager = CheckpointManager(temp_workspace)

    assert manager.list_checkpoints("data_analysis") == []
    assert manager.get_latest("data_analysis") is None


# ── Serialization tests ───────────────────────────────────────────────

def test_file_state_serialization():
    """Test FileState round-trip."""
    state = FileState(
        path="test.txt",
        hash="abc123",
        size=1024,
        mtime=123456.789,
        is_binary=False,
    )

    data = state.to_dict()
    restored = FileState.from_dict(data)

    assert restored.path == state.path
    assert restored.hash == state.hash
    assert restored.size == state.size
    assert restored.mtime == state.mtime
    assert restored.is_binary == state.is_binary


def test_checkpoint_data_serialization():
    """Test CheckpointData round-trip with new fields."""
    checkpoint = CheckpointData(
        id="cp_main_0001_20260505",
        agent_type="main",
        timestamp="2026-05-05T12:00:00+00:00",
        epoch=1,
        description="Test checkpoint",
        source="pre_message",
        file_states={
            "test.txt": FileState(
                path="test.txt",
                hash="abc123",
                size=1024,
                mtime=123456.789,
                is_binary=False,
            )
        },
    )

    data = checkpoint.to_dict()
    restored = CheckpointData.from_dict(data)

    assert restored.id == checkpoint.id
    assert restored.agent_type == "main"
    assert restored.epoch == 1
    assert restored.description == checkpoint.description
    assert restored.source == "pre_message"
    assert "test.txt" in restored.file_states
