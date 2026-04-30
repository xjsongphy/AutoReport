"""Tests for tool registry."""

import pytest
from pathlib import Path
import tempfile
import shutil

from autoreport.core.tools.registry import ToolRegistry, Tool
from autoreport.core.tools.file_tools import ReadFileTool, WriteFileTool


class DummyTool(Tool):
    """Dummy tool for testing."""

    name = "dummy_tool"
    description = "A dummy tool for testing"

    async def __call__(self, **kwargs):
        return {"result": "dummy"}


@pytest.mark.asyncio
async def test_tool_registry_register():
    """Test registering tools."""
    registry = ToolRegistry()
    tool = DummyTool()

    registry.register(tool)

    assert registry.get("dummy_tool") is tool
    assert registry.get("nonexistent") is None


@pytest.mark.asyncio
async def test_tool_registry_unregister():
    """Test unregistering tools."""
    registry = ToolRegistry()
    tool = DummyTool()

    registry.register(tool)
    assert registry.get("dummy_tool") is tool

    registry.unregister("dummy_tool")
    assert registry.get("dummy_tool") is None


@pytest.mark.asyncio
async def test_tool_registry_get_all():
    """Test getting all tools."""
    registry = ToolRegistry()

    tool1 = DummyTool()
    tool1.name = "tool1"
    tool1.description = "First tool"

    tool2 = DummyTool()
    tool2.name = "tool2"
    tool2.description = "Second tool"

    registry.register(tool1)
    registry.register(tool2)

    all_tools = registry.get_all()

    assert len(all_tools) == 2
    assert "tool1" in all_tools
    assert "tool2" in all_tools


@pytest.mark.asyncio
async def test_tool_registry_get_definitions():
    """Test getting tool definitions for LLM."""
    registry = ToolRegistry()

    # Register file tools
    workspace = Path(tempfile.mkdtemp())
    registry.register(ReadFileTool(workspace=workspace))
    registry.register(WriteFileTool(workspace=workspace))

    definitions = registry.get_definitions()

    assert len(definitions) == 2

    # Check structure
    for definition in definitions:
        assert "name" in definition
        assert "description" in definition
        assert "input_schema" in definition


@pytest.mark.asyncio
async def test_tool_call():
    """Test calling a tool through registry."""
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)

    retrieved_tool = registry.get("dummy_tool")
    result = await retrieved_tool()

    assert result["result"] == "dummy"
