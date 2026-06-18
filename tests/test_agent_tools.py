"""Tool execution tests — tests the tool registry and execution pipeline.

These tests do NOT require API keys. They test:
- Tool registration and schema generation
- Tool execution (read, write_file, bash, etc.)
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from autoreport.core.tools.exec_tools import ExecTool
from autoreport.core.tools.file_tools import ReadTool, WriteFileTool
from autoreport.core.tools.registry import ToolRegistry


def _workspace():
    """Create a temp workspace (no tmp_path to avoid pytest-qt permission issue)."""
    tmpdir = tempfile.mkdtemp()
    ws = Path(tmpdir) / "project"
    ws.mkdir()
    for d in ["data", "data/processed", "references", "theory", "code", "tex"]:
        (ws / d).mkdir(parents=True)
    (ws / "data" / "sample.csv").write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
    (ws / "data" / "test.txt").write_text("Hello World\nLine 2\nLine 3\nLine 4\nLine 5\n", encoding="utf-8")
    return ws


class TestToolRegistry:
    """Tool registration and lookup."""

    def test_register_and_get(self):
        reg = ToolRegistry()
        ws = _workspace()
        tool = ReadTool(workspace=ws)
        reg.register(tool)
        assert reg.get("read") is not None

    def test_get_nonexistent(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent_tool") is None

    def test_get_definitions(self):
        reg = ToolRegistry()
        ws = _workspace()
        reg.register(ReadTool(workspace=ws))
        defs = reg.get_definitions()
        assert len(defs) > 0

    def test_register_multiple(self):
        reg = ToolRegistry()
        ws = _workspace()
        reg.register(ReadTool(workspace=ws))
        assert reg.get("read") is not None

    def test_unregister(self):
        reg = ToolRegistry()
        ws = _workspace()
        reg.register(ReadTool(workspace=ws))
        reg.unregister("read")
        assert reg.get("read") is None


class TestRead:
    """read tool tests."""

    @pytest.mark.asyncio
    async def test_read_existing_file(self):
        ws = _workspace()
        tool = ReadTool(workspace=ws)
        result = await tool(path="data/test.txt")
        text = result.get("content", str(result)) if isinstance(result, dict) else str(result)
        assert "Hello World" in text

    @pytest.mark.asyncio
    async def test_read_with_line_range(self):
        ws = _workspace()
        tool = ReadTool(workspace=ws)
        result = await tool(path="data/test.txt", offset=1, limit=3)
        text = result.get("content", str(result)) if isinstance(result, dict) else str(result)
        assert "Line 2" in text

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        ws = _workspace()
        tool = ReadTool(workspace=ws)
        with pytest.raises(FileNotFoundError):
            await tool(path="nonexistent.txt")


    @pytest.mark.asyncio
    async def test_read_directory(self):
        ws = _workspace()
        tool = ReadTool(workspace=ws)
        result = await tool(path="data")
        text = result if isinstance(result, str) else str(result)
        assert "sample.csv" in text
        assert "test.txt" in text

    @pytest.mark.asyncio
    async def test_read_empty_directory(self):
        ws = _workspace()
        tool = ReadTool(workspace=ws)
        result = await tool(path="theory")
        assert result is not None


class TestWriteFile:
    """write_file tool tests."""

    @pytest.mark.asyncio
    async def test_write_new_file(self):
        ws = _workspace()
        tool = WriteFileTool(workspace=ws, write_allowed_dir=ws)
        result = await tool(path="code/new_file.py", content="print('hello')")
        assert result is not None
        assert (ws / "code" / "new_file.py").read_text() == "print('hello')"


class TestBashTool:
    """bash tool tests."""

    @pytest.mark.asyncio
    async def test_simple_calculation(self):
        ws = _workspace()
        tool = ExecTool(working_dir=ws)
        result = await tool(command="python -c \"print(2+2)\"", command_description="Show simple calculation")
        output = result.get("stdout", str(result)) if isinstance(result, dict) else str(result)
        assert "4" in output

    @pytest.mark.asyncio
    async def test_git_command_runs(self):
        ws = _workspace()
        tool = ExecTool(working_dir=ws)
        result = await tool(command="pwd", command_description="Show current directory")
        text = result.get("stdout", "") if isinstance(result, dict) else str(result)
        assert str(ws) in text

    @pytest.mark.asyncio
    async def test_nonzero_exit(self):
        ws = _workspace()
        tool = ExecTool(working_dir=ws)
        result = await tool(command="python -c \"exit(2)\"", command_description="Exit with nonzero code")
        assert result.get("returncode") == 2

    @pytest.mark.asyncio
    async def test_missing_description(self):
        ws = _workspace()
        tool = ExecTool(working_dir=ws)
        with pytest.raises(ValueError):
            await tool(command="echo hi", command_description="")
