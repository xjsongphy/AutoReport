"""Tests for checkpoint management."""

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
    (workspace / "theory" / "test.md").write_text("# Theory\n\nSome content.\n")

    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_create_checkpoint(temp_workspace):
    """Test creating a checkpoint."""
    manager = CheckpointManager(temp_workspace)

    checkpoint_id = await manager.create_checkpoint("Test checkpoint")

    assert checkpoint_id is not None
    assert checkpoint_id.startswith("cp_")

    # Verify checkpoint was saved
    checkpoint = manager.get_checkpoint(checkpoint_id)
    assert checkpoint is not None
    assert checkpoint.description == "Test checkpoint"
    assert checkpoint.source == "main_agent"


@pytest.mark.asyncio
async def test_checkpoint_captures_files(temp_workspace):
    """Test that checkpoint captures file states."""
    manager = CheckpointManager(temp_workspace)

    checkpoint_id = await manager.create_checkpoint("Initial state")

    checkpoint = manager.get_checkpoint(checkpoint_id)

    # Should have captured our test files
    assert "data/test.csv" in checkpoint.file_states
    assert "theory/test.md" in checkpoint.file_states

    # Check file state
    csv_state = checkpoint.file_states["data/test.csv"]
    assert csv_state.size > 0
    assert csv_state.hash is not None


@pytest.mark.asyncio
async def test_get_all_checkpoints(temp_workspace):
    """Test getting all checkpoints."""
    manager = CheckpointManager(temp_workspace)

    # Create multiple checkpoints
    await manager.create_checkpoint("First checkpoint")
    await manager.create_checkpoint("Second checkpoint")
    await manager.create_checkpoint("Third checkpoint")

    checkpoints = manager.get_checkpoints()

    assert len(checkpoints) == 3
    assert checkpoints[0].description == "First checkpoint"
    assert checkpoints[1].description == "Second checkpoint"
    assert checkpoints[2].description == "Third checkpoint"


@pytest.mark.asyncio
async def test_clear_old_checkpoints(temp_workspace):
    """Test clearing old checkpoints."""
    manager = CheckpointManager(temp_workspace)

    # Create multiple checkpoints
    await manager.create_checkpoint("First")
    await manager.create_checkpoint("Second")
    await manager.create_checkpoint("Third")

    # Clear old checkpoints, keep 2
    manager.clear_old_checkpoints(keep=2)

    checkpoints = manager.get_checkpoints()
    assert len(checkpoints) == 2


@pytest.mark.asyncio
async def test_checkpoint_id_generation(temp_workspace):
    """Test that checkpoint IDs are unique."""
    manager = CheckpointManager(temp_workspace)

    id1 = await manager.create_checkpoint("First")
    id2 = await manager.create_checkpoint("Second")

    assert id1 != id2
    assert id1.startswith("cp_")
    assert id2.startswith("cp_")


def test_file_state_serialization():
    """Test FileState serialization."""
    state = FileState(
        path="test.txt",
        hash="abc123",
        size=1024,
        mtime=123456.789,
        is_binary=False,
    )

    # Convert to dict and back
    data = state.to_dict()
    restored = FileState.from_dict(data)

    assert restored.path == state.path
    assert restored.hash == state.hash
    assert restored.size == state.size
    assert restored.mtime == state.mtime
    assert restored.is_binary == state.is_binary


def test_checkpoint_data_serialization():
    """Test CheckpointData serialization."""
    checkpoint = CheckpointData(
        id="cp_test",
        timestamp="2024-01-01T12:00:00",
        description="Test checkpoint",
        source="main_agent",
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

    # Convert to dict and back
    data = checkpoint.to_dict()
    restored = CheckpointData.from_dict(data)

    assert restored.id == checkpoint.id
    assert restored.description == checkpoint.description
    assert "test.txt" in restored.file_states
