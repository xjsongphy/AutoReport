"""Built-in template access tool for Report Agent.

This tool provides read-only access to built-in LaTeX templates stored in
autoreport/templates/reports/. Only available to Report Agent.
"""

import importlib.resources
from pathlib import Path

from loguru import logger

from ..tools.registry import Tool


class BuiltinTemplateTool(Tool):
    """Read-only access to built-in report templates.

    Allows Report Agent to list and read built-in LaTeX templates without
    needing them to be in the project directory.
    """

    name = "builtin_template"
    description = (
        "Access built-in LaTeX report templates. "
        "Use action='list' to show all available templates, "
        "or action='read' with filename to read a specific template file."
    )

    def __init__(self):
        super().__init__()
        self._template_root = importlib.resources.files("autoreport.templates.reports")

    async def __call__(self, action: str, filename: str = "") -> dict:
        """Execute the builtin_template tool.

        Args:
            action: Operation to perform on built-in templates.
            filename: Template filename (required when action='read').

        @enum action: list, read

        Returns:
            dict with templates list or file content
        """
        return await self.execute(action, filename)

    async def execute(self, action: str, filename: str = "") -> dict:
        """Execute the builtin_template tool.

        Args:
            action: "list" to show all templates, "read" to read a specific file
            filename: Template filename (required for read action)

        Returns:
            dict with templates list or file content
        """
        if action == "list":
            return await self._handle_list()
        elif action == "read":
            return await self._handle_read(filename)
        else:
            return {"error": f"Unknown action: {action}"}

    async def _handle_list(self) -> dict:
        """List all available built-in templates."""
        try:
            templates = []
            for path in self._template_root.iterdir():
                if path.is_file():
                    templates.append({
                        "name": path.name,
                        "size": path.stat().st_size,
                        "description": _get_template_description(path.name),
                    })

            return {
                "templates": sorted(templates, key=lambda x: x["name"]),
                "count": len(templates),
                "usage": (
                    "Use builtin_template(action='read', filename='<name>') "
                    "to read any template listed above. "
                    "Do NOT use the generic read tool — these files are inside "
                    "the Python package, not in the project directory."
                ),
            }
        except Exception as e:
            logger.error("Failed to list built-in templates: {}", e)
            return {"error": f"Failed to list templates: {e}"}

    async def _handle_read(self, filename: str) -> dict:
        """Read a specific built-in template file.

        Args:
            filename: Name of the template file to read

        Returns:
            dict with file content
        """
        if not filename:
            return {"error": "filename is required for read action"}

        # Sanitize filename to prevent directory traversal
        safe_name = Path(filename).name
        if safe_name != filename:
            return {"error": "Invalid filename"}
        filename = safe_name

        try:
            file_path = self._template_root / filename
            if not file_path.is_file():
                available = [p.name for p in self._template_root.iterdir() if p.is_file()]
                return {
                    "error": f"Template not found: {filename}",
                    "available_files": available,
                }

            content = file_path.read_text(encoding="utf-8")
            return {
                "filename": filename,
                "content": content,
                "size": len(content),
            }
        except Exception as e:
            logger.error("Failed to read built-in template {}: {}", filename, e)
            return {"error": f"Failed to read template: {e}"}


def _get_template_description(filename: str) -> str:
    """Get human-readable description for a template file."""
    descriptions = {
        "template_mpl.tex": "PKUMpLtX-based physics experiment report template (Peking University)",
        "template_genernal.tex": "General LaTeX report template",
        "requirements.md": "Report writing requirements and guidelines",
        "README.md": "Template documentation and usage instructions",
    }
    return descriptions.get(filename, "")
