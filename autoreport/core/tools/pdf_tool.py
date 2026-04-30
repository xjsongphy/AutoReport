"""Document parsing tool using mineru-open-api CLI.

Requires mineru-open-api to be installed globally and authenticated.
Install: https://github.com/opendatalab/MinerU
Auth:    mineru-open-api auth

Supported formats: PDF, images, DOCX, PPTX, XLSX (up to 200MB, 600 pages)
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from ..tools.registry import Tool
from .path_utils import resolve_and_validate_path


class PDFParseTool(Tool):
    """Tool for parsing documents using mineru-open-api CLI.

    Uses the authenticated ``extract`` command for high-quality extraction
    with full asset support (images, tables, formulas).
    """

    name = "parse_pdf"
    description = (
        "Parse PDF/image/DOCX/PPTX files and convert to Markdown "
        "using mineru-open-api (authenticated). Supports batch processing. "
        "Output .md is saved next to each source file. "
        "Supports up to 200MB and 600 pages per file."
    )

    def __init__(
        self,
        workspace: Path,
        timeout: int = 300,
    ):
        self.workspace = Path(workspace).resolve()
        self.timeout = timeout
        self._cli_name = "mineru-open-api"

    @staticmethod
    def is_available() -> bool:
        """Check whether mineru-open-api CLI is installed."""
        return shutil.which("mineru-open-api") is not None

    async def __call__(
        self,
        file_paths: str | list[str],
        output_dir: str | None = None,
        language: str = "ch",
    ) -> dict[str, Any]:
        """Parse one or more document files to Markdown.

        Args:
            file_paths: Single file path or list of paths (relative to workspace).
                        Supports PDF, images, DOCX, PPTX, XLSX.
            output_dir: Optional output directory (relative to workspace).
                        Defaults to the same directory as each source file.
            language: Document language hint, e.g. "ch" or "en".

        Returns:
            Dictionary with:
            - results: List of per-file results (source_path, output_path, content, size_bytes)
            - total: Number of files processed
            - errors: List of files that failed (None if all succeeded)
        """
        if isinstance(file_paths, str):
            paths = [file_paths]
        else:
            paths = list(file_paths)

        if not self.is_available():
            raise RuntimeError(
                "mineru-open-api is not installed. "
                "Install: https://github.com/opendatalab/MinerU"
            )

        # Resolve output directory
        if output_dir:
            out_base = resolve_and_validate_path(output_dir, self.workspace)
            out_base.mkdir(parents=True, exist_ok=True)
        else:
            out_base = None

        results: list[dict[str, Any]] = []
        errors: list[str] = []

        for raw_path in paths:
            try:
                src = resolve_and_validate_path(raw_path, self.workspace)
                if not src.exists():
                    errors.append(f"{raw_path}: file not found")
                    continue

                file_out_dir = out_base if out_base else src.parent

                result = await self._parse_single(src, file_out_dir, language)
                results.append(result)
                logger.info("Parsed {} -> {}", src.name, result["output_path"])

            except Exception as e:
                logger.error("Failed to parse {}: {}", raw_path, e)
                errors.append(f"{raw_path}: {e}")

        return {
            "results": results,
            "total": len(paths),
            "errors": errors if errors else None,
        }

    async def _parse_single(
        self,
        src: Path,
        out_dir: Path,
        language: str,
    ) -> dict[str, Any]:
        """Parse a single file using ``mineru-open-api extract``."""
        with tempfile.TemporaryDirectory(prefix="autoreport_pdf_") as tmp:
            tmp_dir = Path(tmp)

            cmd = [
                self._cli_name,
                "extract",
                str(src),
                "-o", str(tmp_dir),
                "-f", "md",
                "--language", language,
                "--timeout", str(self.timeout),
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout + 30,
            )

            if proc.returncode != 0:
                err_msg = stderr.decode(errors="replace").strip()
                raise RuntimeError(
                    f"mineru-open-api exited with code {proc.returncode}: {err_msg}"
                )

            # Locate generated .md file in temp output
            md_files = list(tmp_dir.rglob("*.md"))
            if not md_files:
                raise RuntimeError(
                    f"No .md output found for {src.name}. "
                    f"stderr: {stderr.decode(errors='replace')}"
                )

            md_file = md_files[0]
            content = md_file.read_text(encoding="utf-8")

            # Move md + images/ to final location
            final_md = out_dir / (src.stem + ".md")
            final_md.parent.mkdir(parents=True, exist_ok=True)
            final_md.write_text(content, encoding="utf-8")

            # Copy images directory if present (extract mode generates them)
            src_images = tmp_dir / "images"
            image_count = 0
            if src_images.is_dir():
                dst_images = out_dir / "images"
                dst_images.mkdir(parents=True, exist_ok=True)
                for img in src_images.iterdir():
                    if img.is_file():
                        dst = dst_images / img.name
                        dst.write_bytes(img.read_bytes())
                        image_count += 1

            return {
                "source_path": str(src.relative_to(self.workspace)),
                "output_path": str(final_md.relative_to(self.workspace)),
                "content": content,
                "size_bytes": len(content.encode("utf-8")),
                "image_count": image_count,
            }

    async def check_and_warn(self) -> None:
        """Check CLI availability and auth status, log warning if unusable."""
        if not self.is_available():
            logger.warning(
                "mineru-open-api is not installed. Document parsing will not work. "
                "Install: https://github.com/opendatalab/MinerU"
            )
            return

        # Verify auth by running extract --help (lightweight check)
        proc = await asyncio.create_subprocess_exec(
            self._cli_name, "auth", "--verify",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(
                "mineru-open-api is installed but not authenticated. "
                "Run: mineru-open-api auth"
            )
        else:
            logger.info("mineru-open-api is available and authenticated")
