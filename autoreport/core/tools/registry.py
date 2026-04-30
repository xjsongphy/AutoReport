"""Tool registry for agent tools."""

from typing import Any, Callable, Type
from loguru import logger


class Tool:
    """Base class for agent tools."""

    name: str = "base_tool"
    description: str = "Base tool"

    async def __call__(self, **kwargs) -> Any:
        """Execute the tool."""
        raise NotImplementedError


class ToolRegistry:
    """Registry for agent tools."""

    def __init__(self) -> None:
        """Initialize tool registry."""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: {}", tool.name)

    def unregister(self, name: str) -> None:
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            logger.debug("Unregistered tool: {}", name)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all(self) -> dict[str, Tool]:
        """Get all tools."""
        return self._tools.copy()

    def get_definitions(self) -> list[dict]:
        """Get tool definitions for LLM function calling."""
        definitions = []
        for tool in self._tools.values():
            definitions.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": self._get_input_schema(tool),
            })
        return definitions

    def _get_input_schema(self, tool: Tool) -> dict:
        """Get input schema for a tool."""
        # Default schema - tools should override this
        return {
            "type": "object",
            "properties": {},
        }
