"""Integration tests for read-before-edit / file_state mechanism.

Verifies the full lifecycle:
  read        → records state
  apply_patch → warns if not read / if stale (existing file); no warning for new file
  delete_file → (optional check)
"""
import hashlib
from pathlib import Path

import pytest

from autoreport.core.tools.file_state import FileState, FileStateManager
from autoreport.core.tools.file_tools import (
    ApplyPatchTool,
    DeleteFileTool,
    ReadTool,
)
from autoreport.core.tools.manifest_tool import ManifestManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def allowed_dir(workspace: Path) -> Path:
    d = workspace / "output"
    d.mkdir()
    return d


@pytest.fixture
def fsm() -> FileStateManager:
    return FileStateManager()


@pytest.fixture
def manifest(workspace: Path) -> ManifestManager:
    return ManifestManager(workspace)


@pytest.fixture
def read_tool(workspace: Path, fsm: FileStateManager) -> ReadTool:
    return ReadTool(workspace, file_state_manager=fsm)


@pytest.fixture
def patch_tool(workspace: Path, allowed_dir: Path, fsm: FileStateManager, manifest: ManifestManager) -> ApplyPatchTool:
    return ApplyPatchTool(
        workspace=workspace,
        write_allowed_dir=allowed_dir,
        manifest_manager=manifest,
        agent_type="test",
        file_state_manager=fsm,
    )


@pytest.fixture
def delete_tool(workspace: Path, allowed_dir: Path, fsm: FileStateManager, manifest: ManifestManager) -> DeleteFileTool:
    return DeleteFileTool(
        workspace=workspace,
        write_allowed_dir=allowed_dir,
        manifest_manager=manifest,
        agent_type="test",
        file_state_manager=fsm,
    )


# ---------------------------------------------------------------------------
# FileState unit tests
# ---------------------------------------------------------------------------

class TestFileState:
    def test_from_file_creates_state(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        state = FileState.from_file(f)
        assert state.hash is not None
        assert state.mtime is not None
        assert state.size == 11
        # SHA-256 of "hello world"
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert state.hash == expected

    def test_matches_current_same_file(self, tmp_path: Path):
        f = tmp_path / "a.txt"
        f.write_text("content", encoding="utf-8")
        state = FileState.from_file(f)
        match, current = state.matches_current(f)
        assert match is True
        assert current is not None

    def test_matches_current_after_change(self, tmp_path: Path):
        f = tmp_path / "b.txt"
        f.write_text("content", encoding="utf-8")
        state = FileState.from_file(f)
        f.write_text("changed content", encoding="utf-8")
        match, _ = state.matches_current(f)
        assert match is False

    def test_matches_current_file_deleted(self, tmp_path: Path):
        f = tmp_path / "c.txt"
        f.write_text("content", encoding="utf-8")
        state = FileState.from_file(f)
        f.unlink()
        match, current = state.matches_current(f)
        assert match is False
        assert current is None


# ---------------------------------------------------------------------------
# FileStateManager unit tests
# ---------------------------------------------------------------------------

class TestFileStateManager:
    def test_record_and_get(self, tmp_path: Path, fsm: FileStateManager):
        f = tmp_path / "recorded.txt"
        f.write_text("data", encoding="utf-8")
        fsm.record_read(f)
        state = fsm.get_state(f)
        assert state is not None
        assert state.size == 4

    def test_get_state_none(self, tmp_path: Path, fsm: FileStateManager):
        f = tmp_path / "never_read.txt"
        state = fsm.get_state(f)
        assert state is None

    def test_check_without_read_returns_warning(self, tmp_path: Path, fsm: FileStateManager):
        f = tmp_path / "unread.txt"
        f.write_text("data", encoding="utf-8")
        result = fsm.check_read_before_write(f)
        assert result["has_read"] is False
        assert result["warning"] is not None
        assert "without having read it" in result["warning"]

    def test_check_after_read_returns_no_warning(self, tmp_path: Path, fsm: FileStateManager):
        f = tmp_path / "read_ok.txt"
        f.write_text("data", encoding="utf-8")
        fsm.record_read(f)
        result = fsm.check_read_before_write(f)
        assert result["has_read"] is True
        assert result["is_stale"] is False
        assert result["warning"] is None

    def test_check_stale_after_change(self, tmp_path: Path, fsm: FileStateManager):
        f = tmp_path / "stale.txt"
        f.write_text("original", encoding="utf-8")
        fsm.record_read(f)
        f.write_text("modified", encoding="utf-8")
        result = fsm.check_read_before_write(f)
        assert result["has_read"] is True
        assert result["is_stale"] is True
        assert result["warning"] is not None
        assert "changed" in result["warning"]

    def test_clear_removes_all(self, tmp_path: Path, fsm: FileStateManager):
        f = tmp_path / "clear_test.txt"
        f.write_text("data", encoding="utf-8")
        fsm.record_read(f)
        assert fsm.get_state(f) is not None
        fsm.clear()
        assert fsm.get_state(f) is None


# ---------------------------------------------------------------------------
# Integration: ReadTool records state
# ---------------------------------------------------------------------------

class TestReadFileIntegration:
    async def test_read_records_state(self, workspace: Path, read_tool: ReadTool, fsm: FileStateManager):
        f = workspace / "test.txt"
        f.write_text("hello\nworld\n", encoding="utf-8")
        result = await read_tool(path="test.txt")
        assert result["path"] is not None
        assert "content" in result
        # Should be recorded in FSM
        state = fsm.get_state(f)
        assert state is not None, "read should record state in FSM"
        assert state.size == f.stat().st_size

    async def test_read_binary_returns_error(self, workspace: Path, read_tool: ReadTool):
        f = workspace / "binary.bin"
        f.write_bytes(b"\x80\x81\x82\x83")  # invalid UTF-8
        result = await read_tool(path="binary.bin")
        assert "error" in result
        assert "binary" in result["error"].lower() or "utf-8" in result["error"].lower()

    async def test_read_then_patch_passes(self, workspace: Path, allowed_dir: Path,
                                          read_tool: ReadTool, patch_tool: ApplyPatchTool):
        f = allowed_dir / "read_edit.txt"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        # Read first
        await read_tool(path="output/read_edit.txt")
        # Patch should succeed without warning
        result = await patch_tool(path="output/read_edit.txt", patch="-line2\n+modified\n")
        assert "warning" not in result, f"Unexpected warning: {result.get('warning')}"
        assert result["replacements_applied"] >= 1

    async def test_patch_without_read_returns_warning(self, allowed_dir: Path, patch_tool: ApplyPatchTool):
        f = allowed_dir / "no_read.txt"
        f.write_text("content\n", encoding="utf-8")
        result = await patch_tool(path="output/no_read.txt", patch="-content\n+changed\n")
        assert "warning" in result
        assert "without having read it" in result["warning"]

    async def test_patch_stale_after_change(self, workspace: Path, allowed_dir: Path,
                                            read_tool: ReadTool, patch_tool: ApplyPatchTool):
        f = allowed_dir / "stale_edit.txt"
        f.write_text("original\n", encoding="utf-8")
        # Read
        await read_tool(path="output/stale_edit.txt")
        # External modification (simulated)
        f.write_text("externally modified\n", encoding="utf-8")
        # Patch should warn about staleness
        result = await patch_tool(path="output/stale_edit.txt", patch="-externally modified\n+changed\n")
        assert "warning" in result
        assert "changed" in result["warning"]

    async def test_delete_file_no_safety_check(self, allowed_dir: Path, delete_tool: DeleteFileTool):
        """DeleteFileTool doesn't enforce read-before-delete (by design)."""
        f = allowed_dir / "delete_me.txt"
        f.write_text("delete me\n", encoding="utf-8")
        result = await delete_tool(path="output/delete_me.txt")
        assert result["deleted"] is True

    async def test_new_file_patch_no_warning(self, allowed_dir: Path, patch_tool: ApplyPatchTool):
        """A pure-addition patch on a brand-new file should NOT trigger safety warning."""
        result = await patch_tool(path="output/brand_new.txt", patch="+fresh\n")
        assert "warning" not in result, f"Unexpected warning: {result.get('warning')}"
        assert result["created"] is True

    async def test_read_state_isolated_between_agents(self, workspace: Path, allowed_dir: Path, manifest: ManifestManager):
        """Read state should be isolated per agent (no cross-agent sharing)."""
        fsm_a = FileStateManager()
        fsm_b = FileStateManager()
        read_a = ReadTool(workspace, file_state_manager=fsm_a)
        patch_b = ApplyPatchTool(
            workspace=workspace,
            write_allowed_dir=allowed_dir,
            manifest_manager=manifest,
            agent_type="agent_b",
            file_state_manager=fsm_b,
        )
        file_path = allowed_dir / "isolated.txt"
        file_path.write_text("hello\n", encoding="utf-8")

        # Agent A reads file
        await read_a(path="output/isolated.txt")
        # Agent B should still be blocked by read-before-edit
        result = await patch_b(path="output/isolated.txt", patch="-hello\n+world\n")
        assert "warning" in result
        assert result["has_read"] is False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
