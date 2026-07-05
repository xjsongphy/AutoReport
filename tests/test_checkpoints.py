"""Tests for the operation-log checkpoint model (codex-style)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from autoreport.core.checkpoints import (
    CheckpointData,
    CheckpointManager,
    FileOperation,
)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    workspace = Path(tempfile.mkdtemp())
    for dir_name in ["Data", "Data/Processed", "References", "Theory", "Plots", "Tex"]:
        (workspace / dir_name).mkdir(parents=True, exist_ok=True)
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


# ── Core API tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_checkpoint(temp_workspace):
    """create_checkpoint makes an empty operation-log container."""
    manager = CheckpointManager(temp_workspace)

    cp_id = await manager.create_checkpoint(agent_type="main", description="Initial")

    assert cp_id.startswith("cp_main_")
    cp = manager.get_checkpoint("main", cp_id)
    assert cp is not None
    assert cp.description == "Initial"
    assert cp.epoch == 1
    assert cp.operations == []


@pytest.mark.asyncio
async def test_record_operations_appends_to_current(temp_workspace):
    """record_operations appends to the latest checkpoint."""
    manager = CheckpointManager(temp_workspace)
    cp_id = await manager.create_checkpoint(agent_type="theory", description="t1")

    await manager.record_operations("theory", [
        FileOperation(path="Theory/a.md", kind="add", before=None, after="hello"),
    ])

    cp = manager.get_checkpoint("theory", cp_id)
    assert len(cp.operations) == 1
    assert cp.operations[0].kind == "add"
    assert cp.operations[0].after == "hello"


@pytest.mark.asyncio
async def test_record_operations_without_checkpoint_is_noop(temp_workspace):
    manager = CheckpointManager(temp_workspace)
    # No checkpoint created — recording should warn and not crash.
    await manager.record_operations("theory", [
        FileOperation(path="Theory/a.md", kind="add", after="x"),
    ])
    assert manager.list_checkpoints("theory") == []


@pytest.mark.asyncio
async def test_rollback_reverses_modify(temp_workspace):
    """modify op restores the before-content on rollback."""
    manager = CheckpointManager(temp_workspace)
    f = temp_workspace / "Theory" / "a.md"
    f.write_text("original", encoding="utf-8")

    cp_id = await manager.create_checkpoint(agent_type="theory", description="t1")
    await manager.record_operations("theory", [
        FileOperation(path="Theory/a.md", kind="modify", before="original", after="changed"),
    ])
    f.write_text("changed", encoding="utf-8")

    n = await manager.rollback("theory", cp_id)
    assert n == 1
    assert f.read_text(encoding="utf-8") == "original"


@pytest.mark.asyncio
async def test_rollback_reverses_add(temp_workspace):
    """add op deletes the file on rollback."""
    manager = CheckpointManager(temp_workspace)
    f = temp_workspace / "Theory" / "new.md"

    cp_id = await manager.create_checkpoint(agent_type="theory", description="t1")
    await manager.record_operations("theory", [
        FileOperation(path="Theory/new.md", kind="add", before=None, after="created"),
    ])
    f.write_text("created", encoding="utf-8")
    assert f.exists()

    await manager.rollback("theory", cp_id)
    assert not f.exists()


@pytest.mark.asyncio
async def test_rollback_reverses_delete_text(temp_workspace):
    """delete op restores the file content on rollback."""
    manager = CheckpointManager(temp_workspace)
    f = temp_workspace / "Theory" / "a.md"
    f.write_text("keep me", encoding="utf-8")

    cp_id = await manager.create_checkpoint(agent_type="theory", description="t1")
    await manager.record_operations("theory", [
        FileOperation(path="Theory/a.md", kind="delete", before="keep me"),
    ])
    f.unlink()
    assert not f.exists()

    await manager.rollback("theory", cp_id)
    assert f.read_text(encoding="utf-8") == "keep me"


@pytest.mark.asyncio
async def test_rollback_reverses_delete_binary(temp_workspace):
    """delete of a binary file is restored from base64 bytes."""
    import base64

    manager = CheckpointManager(temp_workspace)
    f = temp_workspace / "Plots" / "fig.png"
    raw = b"\x89PNG\r\n\x1a\n\x00\x00IHDR"
    f.write_bytes(raw)

    cp_id = await manager.create_checkpoint(agent_type="plotting", description="p1")
    await manager.record_operations("plotting", [
        FileOperation(
            path="Plots/fig.png",
            kind="delete",
            before_binary_b64=base64.b64encode(raw).decode("ascii"),
        ),
    ])
    f.unlink()

    await manager.rollback("plotting", cp_id)
    assert f.read_bytes() == raw


@pytest.mark.asyncio
async def test_rollback_chain_reverses_target_through_latest(temp_workspace):
    """Rolling back to checkpoint N reverses [N..latest] in order.

    cp1: file F modified A→B
    cp2: file F modified B→C
    Current F = C. Rollback to cp1 → reverse cp2 (write B) then cp1 (write A) → A.
    """
    manager = CheckpointManager(temp_workspace)
    f = temp_workspace / "Theory" / "a.md"
    f.write_text("A", encoding="utf-8")

    cp1 = await manager.create_checkpoint(agent_type="theory", description="t1")
    await manager.record_operations("theory", [
        FileOperation(path="Theory/a.md", kind="modify", before="A", after="B"),
    ])
    f.write_text("B", encoding="utf-8")

    cp2 = await manager.create_checkpoint(agent_type="theory", description="t2")
    await manager.record_operations("theory", [
        FileOperation(path="Theory/a.md", kind="modify", before="B", after="C"),
    ])
    f.write_text("C", encoding="utf-8")

    # Rollback to cp1 undoes both t2 and t1.
    await manager.rollback("theory", cp1)
    assert f.read_text(encoding="utf-8") == "A"

    # Rollback to cp2 (after re-applying) would keep t1; here we only verify
    # the chain math: re-run forward to C, rollback to cp2 restores B.
    f.write_text("C", encoding="utf-8")
    await manager.rollback("theory", cp2)
    assert f.read_text(encoding="utf-8") == "B"


@pytest.mark.asyncio
async def test_rollback_leaves_untracked_files_untouched(temp_workspace):
    """Files not in any operation record are never modified by rollback."""
    manager = CheckpointManager(temp_workspace)
    bystander = temp_workspace / "Theory" / "bystander.md"
    bystander.write_text("virgin", encoding="utf-8")
    target = temp_workspace / "Theory" / "target.md"
    target.write_text("v1", encoding="utf-8")

    cp_id = await manager.create_checkpoint(agent_type="theory", description="t1")
    await manager.record_operations("theory", [
        FileOperation(path="Theory/target.md", kind="modify", before="v1", after="v2"),
    ])
    target.write_text("v2", encoding="utf-8")

    await manager.rollback("theory", cp_id)
    assert target.read_text(encoding="utf-8") == "v1"
    assert bystander.read_text(encoding="utf-8") == "virgin"


@pytest.mark.asyncio
async def test_persistence_round_trip(temp_workspace):
    """Operations survive save/load to disk."""
    manager = CheckpointManager(temp_workspace)
    cp_id = await manager.create_checkpoint(agent_type="theory", description="t1")
    await manager.record_operations("theory", [
        FileOperation(path="Theory/a.md", kind="modify", before="x", after="y"),
    ])

    # Re-load from disk.
    manager2 = CheckpointManager(temp_workspace)
    cp = manager2.get_checkpoint("theory", cp_id)
    assert cp is not None
    assert len(cp.operations) == 1
    assert cp.operations[0].before == "x"
    assert cp.operations[0].after == "y"


@pytest.mark.asyncio
async def test_legacy_format_skipped_on_load(temp_workspace):
    """Old snapshot/diff JSON (no 'operations' key) is ignored, not crashed on."""
    agent_dir = temp_workspace / ".checkpoints" / "theory"
    agent_dir.mkdir(parents=True, exist_ok=True)
    legacy = {
        "id": "cp_theory_0001_legacy",
        "agent_type": "theory",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "epoch": 1,
        "description": "legacy",
        "source": "pre_message",
        "file_states": {"Theory/a.md": {"path": "Theory/a.md", "hash": "h", "size": 1, "mtime": 0.0, "is_binary": False, "content": "x"}},
        "file_diffs": {},
        "parent_id": None,
        "conversation_history": [],
    }
    (agent_dir / "cp_theory_0001_legacy.json").write_text(
        __import__("json").dumps(legacy), encoding="utf-8"
    )

    manager = CheckpointManager(temp_workspace)
    # Legacy checkpoint is skipped, not loaded.
    assert manager.list_checkpoints("theory") == []
    # Fresh checkpoints still work from epoch 1.
    cp_id = await manager.create_checkpoint(agent_type="theory", description="fresh")
    assert manager.get_checkpoint("theory", cp_id).epoch == 1


@pytest.mark.asyncio
async def test_per_agent_isolation(temp_workspace):
    """Checkpoints from different agents don't mix."""
    manager = CheckpointManager(temp_workspace)
    await manager.create_checkpoint(agent_type="main", description="M1")
    await manager.create_checkpoint(agent_type="theory", description="T1")
    await manager.create_checkpoint(agent_type="main", description="M2")

    assert len(manager.list_checkpoints("main")) == 2
    assert len(manager.list_checkpoints("theory")) == 1


@pytest.mark.asyncio
async def test_clear_old_keeps_recent(temp_workspace):
    manager = CheckpointManager(temp_workspace)
    ids = []
    for i in range(5):
        ids.append(await manager.create_checkpoint(agent_type="main", description=f"c{i}"))

    removed = manager.clear_old("main", keep=2)
    assert removed == 3
    remaining = manager.list_checkpoints("main")
    assert len(remaining) == 2
    # Kept the most recent two.
    assert remaining[-1].id == ids[-1]


# ── Serialization unit tests ──────────────────────────────────────────


def test_file_operation_round_trip():
    op = FileOperation(path="Theory/a.md", kind="modify", before="x", after="y")
    d = op.to_dict()
    assert d == {
        "path": "Theory/a.md",
        "kind": "modify",
        "before": "x",
        "after": "y",
        "before_binary_b64": None,
    }
    restored = FileOperation.from_dict(d)
    assert restored == op


def test_checkpoint_data_round_trip():
    cp = CheckpointData(
        id="cp_theory_0001_x",
        agent_type="theory",
        timestamp="2026-01-01T00:00:00+00:00",
        epoch=1,
        description="t",
        source="pre_message",
        operations=[FileOperation(path="a", kind="add", after="hi")],
    )
    restored = CheckpointData.from_dict(cp.to_dict())
    assert restored.operations == cp.operations
    assert restored.id == cp.id
