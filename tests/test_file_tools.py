"""Tests for file tools."""

import shutil
import tempfile
from pathlib import Path

import pytest

from autoreport.core.tools.file_tools import (
    EditFileTool,
    ReadTool,
    WriteFileTool,
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
async def test_write_file(temp_workspace):
    """Test writing a file."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()

    tool = WriteFileTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    result = await tool(
        path="output/test.txt",
        content="Test content",
        create_backup=False,
    )

    assert result["success"] is True
    assert (write_dir / "test.txt").exists()
    assert (write_dir / "test.txt").read_text(encoding="utf-8") == "Test content"


@pytest.mark.asyncio
async def test_write_file_permission_denied(temp_workspace):
    """Test that write permission is enforced."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()

    # Create another directory that's not allowed
    other_dir = temp_workspace / "other"
    other_dir.mkdir()

    tool = WriteFileTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    # Try to write in workspace but outside allowed directory
    with pytest.raises(PermissionError):
        await tool(
            path="other/unauthorized.txt",
            content="Should fail",
        )


@pytest.mark.asyncio
async def test_write_file_path_traversal_blocked(temp_workspace):
    """Test that path traversal is blocked."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()

    tool = WriteFileTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    # Try to use path traversal
    with pytest.raises(ValueError, match="Path traversal"):
        await tool(
            path="../unauthorized.txt",
            content="Should fail",
        )


@pytest.mark.asyncio
async def test_edit_file(temp_workspace):
    """Test editing a file."""
    write_dir = temp_workspace / "output"
    write_dir.mkdir()

    # Create initial file
    test_file = write_dir / "test.txt"
    test_file.write_text("Hello World", encoding="utf-8")

    tool = EditFileTool(
        workspace=temp_workspace,
        write_allowed_dir=write_dir,
    )

    result = await tool(
        path="output/test.txt",
        old_text="World",
        new_text="Universe",
    )

    assert Path(result["path"]) == test_file.resolve()
    assert result["replacements_made"] == 1
    assert test_file.read_text(encoding="utf-8") == "Hello Universe"


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
