"""PDF parsing tool using mineru-open-api."""

import asyncio
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from ..tools.registry import Tool


class PDFParseTool(Tool):
    """Tool for parsing PDF files using mineru-open-api."""

    name = "parse_pdf"
    description = "Parse PDF file and convert to Markdown using mineru-open-api."

    def __init__(self, workspace: Path, api_url: str | None = None):
        """Initialize PDF parser.

        Args:
            workspace: Base workspace directory for path validation.
            api_url: URL for mineru-open-api service.
                    If None, uses default http://localhost:9999.
        """
        self.workspace = Path(workspace).resolve()
        self.api_url = api_url or "http://localhost:9999"
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout

    async def __call__(
        self,
        pdf_path: str,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Parse a PDF file.

        Args:
            pdf_path: Path to PDF file (relative to workspace)
            output_path: Optional path to save Markdown output (relative to workspace)

        Returns:
            Dictionary with markdown_content, page_count, and output_path

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
            FileNotFoundError: If PDF file not found.
        """
        pdf_file = self._resolve_and_validate_path(pdf_path)

        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        output_file = None
        if output_path:
            output_file = self._resolve_and_validate_path(output_path)

        logger.debug("Parsing PDF: {}", pdf_path)

        try:
            # Read PDF file asynchronously
            pdf_bytes = await asyncio.to_thread(pdf_file.read_bytes)

            # Prepare the request
            files = {"file": (pdf_file.name, pdf_bytes)}
            data = {}
            if output_file:
                data["output_format"] = "markdown"

            # Call mineru-open-api
            response = await self.client.post(
                f"{self.api_url}/parse",
                files=files,
                data=data,
            )
            response.raise_for_status()

            result = response.json()

            # Save to file if output_path specified
            saved_path = None
            if output_file and "markdown" in result:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(
                    output_file.write_text,
                    result["markdown"],
                    encoding="utf-8"
                )
                saved_path = str(output_file)

            return {
                "markdown_content": result.get("markdown", ""),
                "page_count": result.get("page_count", 0),
                "output_path": saved_path,
                "pdf_path": str(pdf_file),
            }
        except httpx.HTTPError as e:
            logger.error("HTTP error parsing PDF: {}", e)
            raise RuntimeError(f"Failed to parse PDF: {e}")
        except Exception as e:
            logger.error("Failed to parse PDF {}: {}", pdf_file, e)
            raise

    def _resolve_and_validate_path(self, path: str) -> Path:
        """Resolve and validate a path is within workspace.

        Args:
            path: Path to resolve and validate.

        Returns:
            Resolved absolute path.

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
        """
        # Reject absolute paths for security
        path_obj = Path(path)
        if path_obj.is_absolute():
            raise ValueError(
                f"Absolute paths are not allowed: {path}. "
                "Please use paths relative to the workspace."
            )

        # Reject path traversal attempts
        if ".." in path_obj.parts:
            raise ValueError(
                f"Path traversal with '..' is not allowed: {path}"
            )

        # Resolve relative to workspace
        resolved = (self.workspace / path_obj).resolve()

        # Verify the resolved path is within workspace
        try:
            resolved.relative_to(self.workspace)
        except ValueError:
            raise ValueError(
                f"Resolved path is outside workspace: {resolved}"
            )

        return resolved
