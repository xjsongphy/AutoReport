"""PDF parsing tool using mineru-open-api."""

from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from ..tools.registry import Tool


class PDFParseTool(Tool):
    """Tool for parsing PDF files using mineru-open-api."""

    name = "parse_pdf"
    description = "Parse PDF file and convert to Markdown using mineru-open-api."

    def __init__(self, api_url: str | None = None):
        """Initialize PDF parser.

        Args:
            api_url: URL for mineru-open-api service.
                    If None, uses default http://localhost:9999.
        """
        self.api_url = api_url or "http://localhost:9999"
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout

    async def __call__(
        self,
        pdf_path: str,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Parse a PDF file.

        Args:
            pdf_path: Path to PDF file
            output_path: Optional path to save Markdown output

        Returns:
            Dictionary with markdown_content, page_count, and output_path
        """
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.debug("Parsing PDF: {}", pdf_path)

        try:
            # Prepare the request
            files = {"file": (pdf_file.name, pdf_file.read_bytes())}
            data = {}
            if output_path:
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
            if output_path and "markdown" in result:
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(result["markdown"], encoding="utf-8")
                saved_path = str(output_file)

            return {
                "markdown_content": result.get("markdown", ""),
                "page_count": result.get("page_count", 0),
                "output_path": saved_path,
                "pdf_path": str(pdf_path),
            }
        except httpx.HTTPError as e:
            logger.error("HTTP error parsing PDF: {}", e)
            raise RuntimeError(f"Failed to parse PDF: {e}")
        except Exception as e:
            logger.error("Failed to parse PDF {}: {}", pdf_path, e)
            raise
