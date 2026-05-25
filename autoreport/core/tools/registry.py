"""Tool registry for agent tools."""

import inspect
import re
from typing import Any, Union, get_type_hints

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
        self._schema_cache: dict[str, dict] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        # Generate and cache schema
        self._schema_cache[tool.name] = self._generate_input_schema(tool)
        logger.debug("Registered tool: {}", tool.name)

    def unregister(self, name: str) -> None:
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            if name in self._schema_cache:
                del self._schema_cache[name]
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
                "input_schema": self._schema_cache.get(tool.name, self._get_empty_schema()),
            })
        return definitions

    def _get_empty_schema(self) -> dict:
        """Get empty schema fallback."""
        return {
            "type": "object",
            "properties": {},
        }

    def _generate_input_schema(self, tool: Tool) -> dict:
        """Generate JSON Schema for tool input from __call__ signature.

        Args:
            tool: Tool instance.

        Returns:
            JSON Schema dictionary.
        """
        try:
            # Get the __call__ method signature
            sig = inspect.signature(tool.__call__)
            type_hints = get_type_hints(tool.__call__)

            # Get parameter descriptions and enum constraints from docstring
            docstring = tool.__call__.__doc__ or ""
            param_descriptions, param_enums = self._parse_param_descriptions(docstring)

            properties = {}
            required = []

            for param_name, param in sig.parameters.items():
                if param_name == "self" or param_name == "kwargs":
                    continue

                # Get type annotation
                param_type = type_hints.get(param_name, Any)

                # Generate schema for this parameter
                param_schema = self._type_to_json_schema(param_type)

                # Add description if available
                if param_name in param_descriptions:
                    param_schema["description"] = param_descriptions[param_name]

                # Add enum constraint if available
                if param_name in param_enums:
                    param_schema["enum"] = param_enums[param_name]

                # Check if parameter is required
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

                properties[param_name] = param_schema

            return {
                "type": "object",
                "properties": properties,
                "required": required if required else [],
            }

        except Exception as e:
            logger.warning("Failed to generate schema for {}: {}", tool.name, e)
            return self._get_empty_schema()

    def _type_to_json_schema(self, type_hint: Any) -> dict:
        """Convert Python type hint to JSON Schema.

        Args:
            type_hint: Python type annotation.

        Returns:
            JSON Schema type definition.
        """
        origin = getattr(type_hint, "__origin__", None)

        # Handle Optional types
        if origin is Union or str(type_hint).startswith("typing.Union") or str(type_hint).startswith("typing.Optional"):
            args = getattr(type_hint, "__args__", [])
            if args:
                # Get the non-None type
                for arg in args:
                    if arg is not type(None):
                        return self._type_to_json_schema(arg)
            return {"type": "string"}

        # Handle basic types
        type_map = {
            str: {"type": "string"},
            int: {"type": "integer"},
            float: {"type": "number"},
            bool: {"type": "boolean"},
            list: {"type": "array"},
            dict: {"type": "object"},
            Any: {"type": "string"},  # Default to string for Any
        }

        if type_hint in type_map:
            return type_map[type_hint].copy()

        # Handle | syntax (Python 3.10+ union)
        if origin is Union:
            return {"type": "string"}

        # Default to string
        return {"type": "string"}

    def _parse_param_descriptions(self, docstring: str) -> tuple[dict[str, str], dict[str, list[str]]]:
        """Parse parameter descriptions and enum constraints from docstring.

        Supports @enum directive:
            @enum param_name: value1, value2, value3

        Args:
            docstring: Method docstring.

        Returns:
            Tuple of (descriptions dict, enums dict).
        """
        descriptions = {}
        enums = {}

        # Extract @enum directives
        enum_pattern = r"@enum\s+(\w+):\s*([^\n]+)"
        for match in re.finditer(enum_pattern, docstring):
            param_name = match.group(1)
            enum_values = [v.strip() for v in match.group(2).split(",")]
            enums[param_name] = enum_values

        # Match Google-style docstring Args section
        # Example:
        #   Args:
        #       path: Path to file.
        #       offset: Starting line number.
        args_pattern = r"Args:\s*\n((?:\s+\w+:\s+[^\n]+\n?)*)"
        args_match = re.search(args_pattern, docstring)

        if args_match:
            args_text = args_match.group(1)
            # Match each parameter: "name: description"
            param_pattern = r"(\w+):\s+([^\n]+)"
            for match in re.finditer(param_pattern, args_text):
                param_name = match.group(1)
                description = match.group(2).strip()
                descriptions[param_name] = description

        return descriptions, enums
