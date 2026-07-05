"""Tests for bash execution tool."""

import pytest

from autoreport.core.tools.exec_tools import ALLOWED_COMMANDS, BashTool


@pytest.fixture
def temp_dir():
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_allowed_commands_contains_expected():
    assert "python" in ALLOWED_COMMANDS
    assert "python3" in ALLOWED_COMMANDS
    assert "xelatex" in ALLOWED_COMMANDS
    assert "git" in ALLOWED_COMMANDS


@pytest.mark.asyncio
async def test_bash_rejects_unknown_command(temp_dir):
    tool = BashTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="not allowed"):
        await tool(command="curl http://example.com", command_description="Fetch URL")


@pytest.mark.asyncio
async def test_bash_requires_description(temp_dir):
    tool = BashTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="command_description is required"):
        await tool(command="echo ok", command_description="")


@pytest.mark.asyncio
async def test_bash_runs_allowed_command(temp_dir):
    tool = BashTool(working_dir=temp_dir)
    result = await tool(command="echo hello", command_description="Show greeting")
    assert result["returncode"] == 0
    assert "hello" in result["stdout"]
    assert result["timed_out"] is False

