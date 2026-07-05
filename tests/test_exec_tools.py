"""Tests for bash execution tool."""

import pytest

from autoreport.core.tools.exec_tools import ALLOWED_COMMANDS, ExecTool


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
    tool = ExecTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="not allowed"):
        await tool(command="curl http://example.com", command_description="Fetch URL")


@pytest.mark.asyncio
async def test_bash_requires_description(temp_dir):
    tool = ExecTool(working_dir=temp_dir)
    with pytest.raises(ValueError, match="command_description is required"):
        await tool(command="echo ok", command_description="")


@pytest.mark.asyncio
async def test_bash_runs_allowed_command(temp_dir):
    tool = ExecTool(working_dir=temp_dir)
    result = await tool(command="echo hello", command_description="Show greeting")
    assert result["returncode"] == 0
    assert "hello" in result["stdout"]
    assert result["timed_out"] is False


@pytest.mark.asyncio
async def test_ls_filters_internal_metadata_dirs(temp_dir):
    (temp_dir / ".autoreport").mkdir()
    (temp_dir / ".checkpoints").mkdir()
    (temp_dir / "data.csv").write_text("x")
    tool = ExecTool(working_dir=temp_dir)
    result = await tool(command="ls -a", command_description="List all")
    stdout = result["stdout"]
    assert "data.csv" in stdout
    assert ".autoreport" not in stdout.split()
    assert ".checkpoints" not in stdout.split()


@pytest.mark.asyncio
async def test_ls_long_format_filters_internal_metadata(temp_dir):
    (temp_dir / ".autoreport").mkdir()
    (temp_dir / "keep.txt").write_text("x")
    tool = ExecTool(working_dir=temp_dir)
    result = await tool(command="ls -la", command_description="List long")
    lines = [l for l in result["stdout"].splitlines() if l.strip()]
    names = {l.split()[-1].split(" -> ")[0] for l in lines}
    assert "keep.txt" in names
    assert ".autoreport" not in names


@pytest.mark.asyncio
async def test_ls_filters_symlink_into_metadata(temp_dir):
    (temp_dir / ".autoreport").mkdir()
    (temp_dir / "sneaky").symlink_to(temp_dir / ".autoreport")
    (temp_dir / "real.csv").write_text("x")
    tool = ExecTool(working_dir=temp_dir)
    result = await tool(command="ls -la", command_description="List long")
    names = {l.split()[-1].split(" -> ")[0] for l in result["stdout"].splitlines() if l.strip()}
    assert "real.csv" in names
    assert "sneaky" not in names


@pytest.mark.asyncio
async def test_find_filters_internal_metadata(temp_dir):
    (temp_dir / ".autoreport").mkdir()
    (temp_dir / ".autoreport" / "secret.json").write_text("{}")
    (temp_dir / "keep.txt").write_text("x")
    tool = ExecTool(working_dir=temp_dir)
    result = await tool(command="find .", command_description="Find all")
    stdout = result["stdout"]
    assert "keep.txt" in stdout
    assert ".autoreport" not in stdout


