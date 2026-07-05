"""Tests for file tools."""

import shutil
import tempfile
from pathlib import Path

import pytest

from autoreport.core.tools.file_tools import (
    ApplyPatchTool,
    ReadTool,
)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    workspace = Path(tempfile.mkdtemp())
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_file(temp_workspace):
    """Test reading a file."""
    # Create a test file
    test_file = temp_workspace / "test.txt"
    test_file.write_text("Hello, World!", encoding="utf-8")

    tool = ReadTool(workspace=temp_workspace)
    result = await tool(path="test.txt")

    assert Path(result["path"]) == test_file.resolve()
    assert result["content"] == "Hello, World!"
    assert result["line_count"] == 1
    assert result["lines_read"] == 1


@pytest.mark.asyncio
async def test_read_file_pdf_rejected(temp_workspace):
    test_file = temp_workspace / "paper.pdf"
    test_file.write_bytes(b"%PDF-1.4")
    tool = ReadTool(workspace=temp_workspace)
    with pytest.raises(ValueError, match="Use parse_pdf"):
        await tool(path="paper.pdf")


@pytest.mark.asyncio
async def test_apply_patch_creates_new_file(temp_workspace):
    """A pure-addition patch creates a new file."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()

    tool = ApplyPatchTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    result = await tool(
        path="output/test.txt",
        patch="+Hello\n+World\n",
    )

    assert result["created"] is True
    assert result["replacements_applied"] == 1
    assert (write_dir / "test.txt").read_text(encoding="utf-8") == "Hello\nWorld\n"


@pytest.mark.asyncio
async def test_apply_patch_permission_denied(temp_workspace):
    """Write permission is enforced."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()
    other_dir = temp_workspace / "other"
    other_dir.mkdir()

    tool = ApplyPatchTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    with pytest.raises(PermissionError):
        await tool(path="other/unauthorized.txt", patch="+x\n")


@pytest.mark.asyncio
async def test_apply_patch_path_traversal_blocked(temp_workspace):
    """Path traversal is blocked."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()

    tool = ApplyPatchTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    with pytest.raises(ValueError, match="Path traversal"):
        await tool(path="../unauthorized.txt", patch="+x\n")


@pytest.mark.asyncio
async def test_apply_patch_edits_existing_file(temp_workspace):
    """A removal/addition patch edits an existing file in place."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()
    test_file = write_dir / "test.txt"
    test_file.write_text("Hello World\n", encoding="utf-8")

    tool = ApplyPatchTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    result = await tool(
        path="output/test.txt",
        patch="-Hello World\n+Hello Universe\n",
    )

    assert Path(result["path"]) == test_file.resolve()
    assert result["replacements_applied"] == 1
    assert result["created"] is False
    assert test_file.read_text(encoding="utf-8") == "Hello Universe\n"
    # Existing file was backed up before the change.
    assert result.get("backup_path")


@pytest.mark.asyncio
async def test_apply_patch_anchor_disambiguates(temp_workspace):
    """@@ anchor picks the second of two identical lines."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()
    test_file = write_dir / "test.txt"
    test_file.write_text("def f():\n    return 0\n\ndef g():\n    return 0\n", encoding="utf-8")

    tool = ApplyPatchTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    result = await tool(
        path="output/test.txt",
        patch="@@ def g():\n-    return 0\n+    return 1\n",
    )

    assert result["replacements_applied"] == 1
    content = test_file.read_text(encoding="utf-8")
    assert "def f():\n    return 0" in content  # first untouched
    assert "def g():\n    return 1" in content


@pytest.mark.asyncio
async def test_apply_patch_not_found_writes_nothing(temp_workspace):
    """On a failed match the file is left unchanged and an error returned."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()
    test_file = write_dir / "test.txt"
    test_file.write_text("alpha\n", encoding="utf-8")

    tool = ApplyPatchTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    result = await tool(path="output/test.txt", patch="-zzz\n+QQQ\n")

    assert "error" in result
    assert test_file.read_text(encoding="utf-8") == "alpha\n"


@pytest.mark.asyncio
async def test_read_directory(temp_workspace):
    """Test reading directory contents."""
    # Create test structure
    (temp_workspace / "dir1").mkdir()
    (temp_workspace / "dir2").mkdir()
    (temp_workspace / "file1.txt").write_text("content")
    (temp_workspace / "dir1" / "subfile.txt").write_text("content")

    tool = ReadTool(workspace=temp_workspace)

    # Test non-recursive
    result = await tool(path=".", recursive=False)

    assert Path(result["path"]) == temp_workspace.resolve()
    assert set(result["directories"]) == {"dir1", "dir2"}
    assert set(result["files"]) == {"file1.txt"}

    # Test recursive
    result = await tool(path=".", recursive=True)

    assert "dir1/subfile.txt" in result["files"]
