"""PDF parsing tool using mineru-open-api.

MinerU OpenAPI Documentation:
- GitHub: https://github.com/opendatalab/MinerU
- API Docs: https://mineru.net/apiManage/docs

Supported formats: PDF, images, DOCX, PPTX, XLSX
"""

import asyncio
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from ..tools.registry import Tool


class PDFParseTool(Tool):
    """Tool for parsing PDF files using mineru-open-api.

    Features:
    - Converts PDF files to Markdown format
    - Extracts text, images, and tables
    - Supports multi-page documents
    - Asynchronous processing with configurable timeout
    - Health check for API availability
    """

    name = "parse_pdf"
    description = "Parse PDF file and convert to Markdown using mineru-open-api. Supports PDF, images, DOCX, PPTX, XLSX formats."

    def __init__(
        self,
        workspace: Path,
        api_url: str | None = None,
        timeout: int = 300,
    ):
        """Initialize PDF parser.

        Args:
            workspace: Base workspace directory for path validation.
            api_url: URL for mineru-open-api service.
                    If None, uses default http://localhost:9999.
            timeout: Request timeout in seconds (default: 300).
        """
        self.workspace = Path(workspace).resolve()
        self.api_url = api_url or "http://localhost:9999"
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=float(timeout))

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
            Dictionary with:
            - markdown_content: Extracted Markdown text
            - page_count: Number of pages processed
            - output_path: Path where output was saved (if specified)
            - pdf_path: Original PDF file path

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
            FileNotFoundError: If PDF file not found.
            RuntimeError: If API call fails.

        Example:
            >>> result = await parse_pdf("references/handout.pdf", "references/handout.md")
            >>> print(result["markdown_content"])
        """
        pdf_file = self._resolve_and_validate_path(pdf_path)

        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_file}")

        output_file = None
        if output_path:
            output_file = self._resolve_and_validate_path(output_path)

        logger.debug("Parsing PDF: {}", pdf_path)

        try:
            # Read PDF file asynchronously
            pdf_bytes = await asyncio.to_thread(pdf_file.read_bytes)

            # Prepare the request
            files = {"file": (pdf_file.name, pdf_bytes)}
            data = {"output_format": "markdown"}

            # Call mineru-open-api
            endpoint = f"{self.api_url}/parse"
            logger.debug("Sending request to: {}", endpoint)

            response = await self.client.post(
                endpoint,
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
                logger.info("Saved parsed content to: {}", saved_path)

            return {
                "markdown_content": result.get("markdown", ""),
                "page_count": result.get("page_count", 0),
                "output_path": saved_path,
                "pdf_path": str(pdf_file),
            }
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error parsing PDF: {}", e.response.status_code)
            raise RuntimeError(
                f"Failed to parse PDF: HTTP {e.response.status_code} - {e.response.text}"
            )
        except httpx.ConnectError as e:
            logger.error("Connection error to mineru-open-api: {}", e)
            raise RuntimeError(
                f"Failed to connect to mineru-open-api at {self.api_url}. "
                "Please ensure the service is running."
            )
        except httpx.TimeoutException:
            logger.error("Timeout parsing PDF after {} seconds", self.timeout)
            raise RuntimeError(
                f"PDF parsing timeout after {self.timeout} seconds. "
                "The file may be too large or the service may be overloaded."
            )
        except Exception as e:
            logger.error("Failed to parse PDF {}: {}", pdf_file, e)
            raise RuntimeError(f"Failed to parse PDF: {e}")

    async def health_check(self) -> dict[str, Any]:
        """Check if mineru-open-api service is available.

        Returns:
            Dictionary with:
            - available: True if service is reachable
            - url: API URL
            - error: Error message if unavailable

        Example:
            >>> health = await health_check()
            >>> if health["available"]:
            ...     print("Service is ready")
        """
        try:
            # Try to reach the service (many endpoints can be used for health check)
            # Using a simple GET request to the base URL
            response = await self.client.get(
                self.api_url,
                timeout=5.0  # Short timeout for health check
            )
            return {
                "available": True,
                "url": self.api_url,
                "status": response.status_code,
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "url": self.api_url,
                "error": "Connection refused - service may not be running",
            }
        except httpx.TimeoutException:
            return {
                "available": False,
                "url": self.api_url,
                "error": "Connection timeout - service may be overloaded",
            }
        except Exception as e:
            return {
                "available": False,
                "url": self.api_url,
                "error": str(e),
            }

    async def check_and_warn(self) -> None:
        """Check API availability and log warning if unavailable.

        This is useful for startup validation where we want to warn
        but not block application startup.
        """
        health = await self.health_check()
        if not health["available"]:
            logger.warning(
                "mineru-open-api unavailable at {}: {}",
                health["url"],
                health.get("error", "unknown error"),
            )
            logger.warning(
                "PDF parsing will not work until mineru-open-api is available. "
                "Install and start with: pip install mineru-open-api && mineru-open-api"
            )
        else:
            logger.info("mineru-open-api is available at {}", health["url"])

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

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
