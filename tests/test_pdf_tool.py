"""Tests for PDF parsing tool."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from autoreport.core.tools.pdf_tool import PDFParseTool


@pytest.fixture
def workspace():
    ws = Path(tempfile.mkdtemp())
    (ws / "References").mkdir()
    yield ws
    import shutil
    shutil.rmtree(ws, ignore_errors=True)


def test_is_available_when_not_installed():
    with patch("shutil.which", return_value=None):
        assert PDFParseTool.is_available() is False


def test_is_available_when_installed():
    with patch("shutil.which", return_value="/usr/bin/mineru-open-api"):
        assert PDFParseTool.is_available() is True


@pytest.mark.asyncio
async def test_parse_raises_when_not_available(workspace):
    tool = PDFParseTool(workspace=workspace)
    with patch.object(PDFParseTool, "is_available", return_value=False):
        with pytest.raises(RuntimeError, match="not installed"):
            await tool(file_paths="References/test.pdf")


@pytest.mark.asyncio
async def test_parse_file_not_found(workspace):
    tool = PDFParseTool(workspace=workspace)
    with patch.object(PDFParseTool, "is_available", return_value=True):
        with pytest.raises(RuntimeError, match="file not found"):
            await tool(file_paths="References/nonexistent.pdf")


@pytest.mark.asyncio
async def test_parse_normalizes_string_to_list(workspace):
    tool = PDFParseTool(workspace=workspace)
    with patch.object(PDFParseTool, "is_available", return_value=False):
        with pytest.raises(RuntimeError):
            await tool(file_paths="test.pdf")


@pytest.mark.asyncio
async def test_parse_accepts_list(workspace):
    tool = PDFParseTool(workspace=workspace)
    with patch.object(PDFParseTool, "is_available", return_value=False):
        with pytest.raises(RuntimeError):
            await tool(file_paths=["test.pdf", "test2.pdf"])


@pytest.mark.asyncio
async def test_parse_single_success(workspace):
    tool = PDFParseTool(workspace=workspace)
    src_file = workspace / "References" / "test.pdf"
    src_file.write_bytes(b"%PDF-1.4 fake")

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0

    with (
        patch.object(PDFParseTool, "is_available", return_value=True),
        patch("autoreport.core.tools.pdf_tool.asyncio.create_subprocess_exec", return_value=mock_proc),
        patch("pathlib.Path.rglob", return_value=[workspace / "References" / "test.md"]),
    ):
        # Create the expected output
        (workspace / "References" / "test.md").write_text("# Parsed content", encoding="utf-8")

        result = await tool(file_paths="References/test.pdf")
        assert result["total"] == 1
        assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_parse_batch_with_errors(workspace):
    tool = PDFParseTool(workspace=workspace)

    with patch.object(PDFParseTool, "is_available", return_value=True):
        with pytest.raises(RuntimeError, match="missing1.pdf: file not found"):
            await tool(file_paths=["missing1.pdf", "missing2.pdf"])


@pytest.mark.asyncio
async def test_parse_surfaces_auth_failure_with_actionable_hint(workspace):
    tool = PDFParseTool(workspace=workspace)
    src_file = workspace / "References" / "auth.pdf"
    src_file.write_bytes(b"%PDF-1.4 fake")

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (
        b"",
        b'HTTP 401, body: {"detail":"user authenticate failed"}',
    )
    mock_proc.returncode = 1

    with (
        patch.object(PDFParseTool, "is_available", return_value=True),
        patch("autoreport.core.tools.pdf_tool.asyncio.create_subprocess_exec", return_value=mock_proc),
    ):
        with pytest.raises(RuntimeError, match="mineru-open-api auth"):
            await tool(file_paths="References/auth.pdf")
