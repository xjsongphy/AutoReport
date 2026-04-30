"""Tests for shell and Python execution tools."""

import pytest

from autoreport.core.tools.exec_tools import (
    ALLOWED_COMMANDS,
    BLOCKED_PYTHON_MODULES,
    ExecTool,
    PythonExecTool,
)


@pytest.fixture
def temp_dir():
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ── ExecTool tests ──────────────────────────────────────────────────────


def test_allowed_commands_contains_expected():
    assert "python" in ALLOWED_COMMANDS
    assert "python3" in ALLOWED_COMMANDS
    assert "xelatex" in ALLOWED_COMMANDS
    assert "git" in ALLOWED_COMMANDS


@pytest.mark.asyncio
async def test_exec_tool_rejects_unknown_command(temp_dir):
    tool = ExecTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="not allowed"):
        await tool("curl http://example.com")


@pytest.mark.asyncio
async def test_exec_tool_rejects_dangerous_rm(temp_dir):
    tool = ExecTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="system directory"):
        await tool("rm -rf /usr")


@pytest.mark.asyncio
async def test_exec_tool_rejects_path_traversal_in_rm(temp_dir):
    tool = ExecTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="Path traversal"):
        await tool("rm -rf ../..")


@pytest.mark.asyncio
async def test_exec_tool_runs_allowed_command(temp_dir):
    tool = ExecTool(working_dir=temp_dir)
    result = await tool("echo hello")
    assert result["returncode"] == 0
    assert "hello" in result["stdout"]
    assert result["timed_out"] is False


@pytest.mark.asyncio
async def test_exec_tool_captures_stderr(temp_dir):
    tool = ExecTool(working_dir=temp_dir)
    result = await tool("echo error >&2")
    assert result["returncode"] == 0
    assert "error" in result["stderr"]


@pytest.mark.asyncio
async def test_exec_tool_timeout(temp_dir):
    tool = ExecTool(working_dir=temp_dir, timeout=1)
    result = await tool("python -c \"import time; time.sleep(10)\"")
    assert result["timed_out"] is True
    assert result["returncode"] == -1


@pytest.mark.asyncio
async def test_exec_tool_returns_nonzero_exit(temp_dir):
    tool = ExecTool(working_dir=temp_dir)
    result = await tool("python -c \"exit(42)\"")
    assert result["returncode"] == 42


# ── PythonExecTool tests ────────────────────────────────────────────────


def test_blocked_modules_include_dangerous():
    assert "os" in BLOCKED_PYTHON_MODULES
    assert "sys" in BLOCKED_PYTHON_MODULES
    assert "subprocess" in BLOCKED_PYTHON_MODULES
    assert "socket" in BLOCKED_PYTHON_MODULES


@pytest.mark.asyncio
async def test_python_exec_basic(temp_dir):
    tool = PythonExecTool(working_dir=temp_dir)
    result = await tool("print('hello from python')")
    assert "hello from python" in result["output"]
    assert result["error"] is None


@pytest.mark.asyncio
async def test_python_exec_math(temp_dir):
    tool = PythonExecTool(working_dir=temp_dir)
    result = await tool("x = sum(range(10)); print(x)")
    assert "45" in result["output"]


@pytest.mark.asyncio
async def test_python_exec_blocked_os(temp_dir):
    tool = PythonExecTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="not allowed"):
        await tool("import os")


@pytest.mark.asyncio
async def test_python_exec_blocked_subprocess(temp_dir):
    tool = PythonExecTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="not allowed"):
        await tool("import subprocess")


@pytest.mark.asyncio
async def test_python_exec_blocked_from_import(temp_dir):
    tool = PythonExecTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="not allowed"):
        await tool("from os import path")


@pytest.mark.asyncio
async def test_python_exec_captures_error(temp_dir):
    tool = PythonExecTool(working_dir=temp_dir)
    result = await tool("1/0")
    assert result["error"] is not None
    assert "ZeroDivisionError" in result["error"]


@pytest.mark.asyncio
async def test_python_exec_returns_execution_time(temp_dir):
    tool = PythonExecTool(working_dir=temp_dir)
    result = await tool("x = 1 + 1")
    assert result["execution_time"] is not None
    assert result["execution_time"] >= 0
