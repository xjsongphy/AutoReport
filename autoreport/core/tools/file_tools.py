"""File operation tools."""

import asyncio
import base64
import re
from pathlib import Path
from typing import Any

from loguru import logger

from ..checkpoints import CheckpointManager, FileOperation, _is_binary
from ..tools.registry import Tool
from .file_state import FileStateManager
from .manifest_tool import ManifestManager
from .patch_engine import ApplyResult, apply_patch_to_text
from .path_utils import (
    is_internal_metadata_path,
    is_internal_metadata_rel,
    resolve_and_validate_path,
    suggest_canonical_path,
)


class FileSafetyMixin:
    """Mixin providing file state checking for write operations.

    Subclasses must set self._file_state_manager and self._agent_type.
    """

    def _check_file_safety(self, file_path: Path) -> dict | None:
        """Check read-before-write safety. Returns a warning dict or None if safe."""
        if self._file_state_manager is None:
            return None
        result = self._file_state_manager.check_read_before_write(file_path)
        if result["warning"]:
            logger.warning("File safety check: {} - {}", file_path.name, result["warning"])
            return {
                "warning": result["warning"],
                "has_read": result["has_read"],
                "is_stale": result["is_stale"],
            }
        return None


class WriteEnabledTool(Tool, FileSafetyMixin):
    """Base for tools that modify files — provides write-permission checking and manifest integration."""

    def __init__(
        self,
        workspace: Path,
        write_allowed_dir: Path | None = None,
        manifest_manager: ManifestManager | None = None,
        agent_type: str | None = None,
        file_state_manager: FileStateManager | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ):
        if (manifest_manager is None) != (agent_type is None):
            raise ValueError(
                "manifest_manager and agent_type must be both set or both None"
            )
        self.workspace = Path(workspace).resolve()
        self.write_allowed_dir = Path(write_allowed_dir).resolve() if write_allowed_dir else None
        self._manifest_manager = manifest_manager
        self._agent_type = agent_type
        self._file_state_manager = file_state_manager
        self._checkpoint_manager = checkpoint_manager

    def _check_write_permission(self, file_path: Path, action: str = "Write") -> None:
        if is_internal_metadata_path(file_path, self.workspace):
            raise PermissionError(
                f"{action} not allowed in internal metadata directories (.autoreport, .checkpoints). Attempted: {file_path}"
            )

        if not self.write_allowed_dir:
            return
        try:
            file_path.relative_to(self.write_allowed_dir)
        except ValueError:
            rel_dir = self.write_allowed_dir.relative_to(self.workspace) if self.write_allowed_dir.is_relative_to(self.workspace) else str(self.write_allowed_dir)
            raise PermissionError(
                f"{action} not allowed to {file_path.relative_to(self.workspace) if file_path.is_relative_to(self.workspace) else file_path}. "
                f"Your allowed write directory is: {rel_dir}/. "
                f"Please write your output files under {rel_dir}/ instead."
            )

    async def _record_checkpoint_op(self, op: FileOperation) -> None:
        """Record a file mutation into the agent's current checkpoint (if any)."""
        if self._checkpoint_manager is not None and self._agent_type:
            await self._checkpoint_manager.record_operations(self._agent_type, [op])


class ReadTool(Tool):
    """Tool for reading files or inspecting directories."""

    name = "read"
    description = (
        "Read a UTF-8 text file or inspect a directory. "
        "If path is a file, returns file contents. "
        "If path is a directory, returns child directories and files. "
        "Supports line ranges for files and optional recursive traversal for directories."
    )

    def __init__(self, workspace: Path, file_state_manager: FileStateManager | None = None):
        self.workspace = Path(workspace).resolve()
        self._file_state_manager = file_state_manager

    async def __call__(
        self,
        path: str,
        offset: int | None = None,
        limit: int | None = None,
        recursive: bool = False,
    ) -> dict[str, Any]:
        """Read a file or directory.

        Args:
            path: Path to file or directory (relative to workspace)
            offset: Optional starting line number (0-indexed) for files
            limit: Optional maximum number of lines to read from files
            recursive: Whether to list directories recursively

        Returns:
            Dictionary with file contents or directory listing metadata

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
        """
        file_path = resolve_and_validate_path(path, self.workspace)
        logger.debug("Reading path: {}", file_path)

        if is_internal_metadata_path(file_path, self.workspace):
            raise PermissionError("Access to internal metadata under .autoreport is not allowed.")

        if not file_path.exists():
            suggestion = suggest_canonical_path(path)
            hint = f" Did you mean '{suggestion}'?" if suggestion and suggestion != path else ""
            raise FileNotFoundError(f"File not found: {file_path}.{hint}")

        if file_path.is_dir():
            return await self._read_directory(file_path, recursive=recursive)

        if file_path.suffix.lower() == ".pdf":
            raise ValueError(
                f"read does not support PDF files: {file_path.name}. "
                "Use parse_pdf to extract content first."
            )

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            line_count = len(lines)

            if offset is not None:
                end = (offset + limit) if limit is not None else None
                lines = lines[offset:end]

            content = "".join(lines)

            # Record file state after successful read
            if self._file_state_manager:
                self._file_state_manager.record_read(file_path)

            return {
                "path": str(file_path),
                "content": content,
                "line_count": line_count,
                "lines_read": len(lines),
            }
        except UnicodeDecodeError:
            logger.warning("Binary file detected (not UTF-8): {}", file_path)
            # Detect common binary file extensions for a helpful message
            ext = file_path.suffix.lower()
            binary_exts = {
                ".png": "image",
                ".jpg": "image",
                ".jpeg": "image",
                ".gif": "image",
                ".bmp": "image",
                ".ico": "image",
                ".svg": "image",
                ".webp": "image",
                ".pdf": "PDF document",
                ".pyc": "Python bytecode",
                ".pyd": "Python DLL",
                ".so": "shared library",
                ".dll": "DLL",
                ".exe": "executable",
                ".bin": "binary",
                ".zip": "archive",
                ".tar": "archive",
                ".gz": "archive",
                ".rar": "archive",
                ".7z": "archive",
                ".mp3": "audio",
                ".mp4": "video",
                ".wav": "audio",
                ".avi": "video",
                ".mov": "video",
                ".ttf": "font",
                ".otf": "font",
                ".woff": "font",
                ".woff2": "font",
            }
            detected_type = binary_exts.get(ext, "binary")
            return {
                "error": f"Cannot read '{file_path.name}' as text: it appears to be a {detected_type} file (not UTF-8 encoded text). "
                         f"The read tool only supports UTF-8 text files. If you need to work with this file type, "
                         f"please use a different approach (e.g., exec for file analysis).",
                "path": str(file_path),
                "is_binary": True,
                "detected_type": detected_type,
            }
        except Exception as e:
            logger.error("Failed to read file {}: {}", file_path, e)
            raise

    async def _read_directory(self, dir_path: Path, recursive: bool) -> dict[str, Any]:
        try:
            directories = []
            files = []

            if recursive:
                for item in sorted(dir_path.rglob("*")):
                    rel = item.relative_to(dir_path).as_posix()
                    if is_internal_metadata_rel(rel):
                        continue
                    if item.is_dir():
                        directories.append(rel)
                    else:
                        files.append(rel)
            else:
                for item in sorted(dir_path.iterdir()):
                    if item.name in {".autoreport", ".checkpoints"}:
                        continue
                    if item.is_dir():
                        directories.append(item.name)
                    else:
                        files.append(item.name)

            return {
                "path": str(dir_path),
                "is_directory": True,
                "directories": directories,
                "files": files,
                "count": len(directories) + len(files),
            }
        except Exception as e:
            logger.error("Failed to read directory {}: {}", dir_path, e)
            raise


def _validate_plotting_script(content: str, workspace: Path) -> str | None:
    """Minimal validation for plotting scripts before saving.

    Only checks that are absolutely reliable (no regex guessing of Python semantics):
      1. unicode_minus — text match, 0% false positive
      2. plt.close pairing — count comparison, straightforward

    All other quality checks (x-monotonicity, data completeness, space utilization,
    curve overlap, discontinuities) are the Plotting Agent's own responsibility
    via the mandatory self-check protocol in its system prompt.
    """
    # Fast path: not a plotting script → skip all checks
    if "matplotlib" not in content and "savefig" not in content:
        return None

    errors: list[str] = []

    # 1. unicode_minus — Windows TNR fonts cannot render Unicode minus (U+2212)
    if "'axes.unicode_minus': False" not in content:
        errors.append(
            "Missing plt.rcParams['axes.unicode_minus'] = False — "
            "minus signs may display as boxes on Windows"
        )

    # 2. Every savefig should have a corresponding plt.close
    savefig_count = len(re.findall(r'\.savefig\(', content))
    close_count = len(re.findall(r'plt\.close\(', content))
    if savefig_count > close_count:
        errors.append(
            f"Found {savefig_count} savefig calls but only {close_count} plt.close calls — "
            "each fig.savefig() must be followed by plt.close(fig) to free memory"
        )

    if errors:
        header = f"Validation failed ({len(errors)} issue(s)):\n"
        return header + "\n".join(f"  [{i+1}] {e}" for i, e in enumerate(errors))
    return None


class ApplyPatchTool(WriteEnabledTool):
    """Edit or create a file with a line-based patch (codex apply_patch style).

    A patch is a line-oriented diff. Each hunk line is prefixed:
      ``' '`` (space) = context line (must match the file, used to disambiguate),
      ``'-'`` = line to remove (must match the file),
      ``'+'`` = line to add.
    A ``@@ <context>`` line optionally anchors a hunk: the engine locates that
    single line first, then searches for the hunk's removed/context lines strictly
    after it. Blank lines separate hunks.

    Matching is exact and whole-line. Repeated lines are disambiguated by the
    sequential cursor (each hunk searches forward from where the previous one
    ended) and by ``@@`` anchors. If a line cannot be located, nothing is written
    and the current content is returned so the agent can re-aim.

    If the file does not exist, a pure-addition patch creates it.
    """

    name = "apply_patch"
    description = (
        "Edit or create a file using a line-based patch. "
        "Prefix each hunk line: ' ' (context, must match), '-' (remove, must match), '+' (add). "
        "Use '@@ <line>' to anchor a hunk after a unique line (disambiguates repeats). "
        "Blank line separates hunks. Matching is exact, whole-line; read the file first. "
        "A pure-addition patch creates a new file."
    )

    def __init__(self, *, content_validator=None, **kwargs):
        super().__init__(**kwargs)
        self._content_validator = content_validator

    async def __call__(self, path: str, patch: str) -> dict[str, Any]:
        """Apply a line-based patch to ``path``.

        Args:
            path: Path to file (relative to workspace). Created if absent.
            patch: Patch body - hunks of ' '/'-'/'+' lines, optional '@@' anchors,
                blank-line-separated.

        Returns:
            Dictionary with path, replacements_applied, and backup_path when an
            existing file was backed up. On failure (lines not found / parse
            error) returns ``error`` plus ``current_content`` and writes nothing.

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
            PermissionError: If write not allowed in target directory.
        """
        file_path = resolve_and_validate_path(path, self.workspace)
        logger.debug("Applying patch: {}", file_path)

        self._check_write_permission(file_path)

        if not str(patch or "").strip():
            raise ValueError("patch must be non-empty")

        file_exists = file_path.exists()

        # read-before-edit safety only applies to existing files
        if file_exists:
            safety = self._check_file_safety(file_path)
            if safety and safety["warning"]:
                logger.warning("File safety warning suppressed patch: {}", safety["warning"])
                return safety

        try:
            if file_exists:
                content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
            else:
                content = ""
        except UnicodeDecodeError:
            logger.warning("Binary file detected (not UTF-8): {}", file_path)
            return {
                "error": f"Cannot patch '{file_path.name}': it appears to be a binary file (not UTF-8 encoded).",
                "path": str(file_path),
                "is_binary": True,
            }

        try:
            result: ApplyResult = apply_patch_to_text(content, patch)
        except Exception as e:
            return {
                "error": f"Failed to parse patch: {e}",
                "path": str(file_path),
                "current_content": content,
            }

        if result.error:
            return {
                "error": result.error,
                "path": str(file_path),
                "current_content": content,
            }

        new_content = result.new_lines[0] if result.new_lines else ""

        # No-op: nothing changed.
        if new_content == content:
            return {
                "path": str(file_path),
                "replacements_applied": 0,
                "info": "Patch produced no changes.",
            }

        # Content validation for plotting scripts (full resulting content).
        if self._content_validator and file_path.suffix == '.py':
            error = self._content_validator(new_content, self.workspace)
            if error:
                logger.warning("Plotting script validation failed: {}", error)
                return {"error": error, "path": str(file_path), "validation_failed": True}

        try:
            backup_path = None
            if file_exists:
                try:
                    backup_path = file_path.with_suffix(f"{file_path.suffix}.bak")
                    await asyncio.to_thread(backup_path.write_bytes, file_path.read_bytes())
                except FileNotFoundError:
                    pass

            file_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(file_path.write_text, new_content, encoding="utf-8")

            # Record new file state after successful apply.
            if self._file_state_manager:
                self._file_state_manager.record_read(file_path)

            # Record the mutation for checkpoint rollback (text-only, reversible).
            rel_path = file_path.relative_to(self.workspace).as_posix() if file_path.is_relative_to(self.workspace) else str(file_path)
            await self._record_checkpoint_op(FileOperation(
                path=rel_path,
                kind="add" if not file_exists else "modify",
                before=content if file_exists else None,
                after=new_content,
            ))

            out: dict[str, Any] = {
                "path": str(file_path),
                "replacements_applied": len(result.replacements),
                "created": not file_exists,
            }
            if backup_path:
                out["backup_path"] = str(backup_path)
            return out
        except Exception as e:
            logger.error("Failed to write patched file {}: {}", file_path, e)
            raise


class DeleteFileTool(WriteEnabledTool):
    """Tool for deleting files."""

    name = "delete_file"
    description = "Delete a file from the workspace."

    async def __call__(self, path: str) -> dict[str, Any]:
        """Delete a file.

        Args:
            path: Path to file (relative to workspace)

        Returns:
            Dictionary with path and deleted status.
        """
        file_path = resolve_and_validate_path(path, self.workspace)
        logger.debug("Deleting file: {}", file_path)

        self._check_write_permission(file_path, action="Delete")

        try:
            existed = file_path.exists()
            before_text: str | None = None
            before_b64: str | None = None
            if existed:
                try:
                    if _is_binary(file_path):
                        before_b64 = base64.b64encode(
                            file_path.read_bytes()
                        ).decode("ascii")
                    else:
                        before_text = await asyncio.to_thread(
                            file_path.read_text, encoding="utf-8"
                        )
                except (UnicodeDecodeError, OSError):
                    # Best effort: record deletion without restorable content.
                    before_b64 = base64.b64encode(
                        file_path.read_bytes()
                    ).decode("ascii")

            await asyncio.to_thread(file_path.unlink)

            # Record deletion for checkpoint rollback (text or binary bytes).
            rel_path = file_path.relative_to(self.workspace).as_posix() if file_path.is_relative_to(self.workspace) else str(file_path)
            await self._record_checkpoint_op(FileOperation(
                path=rel_path,
                kind="delete",
                before=before_text,
                before_binary_b64=before_b64,
            ))

            return {"path": str(file_path), "deleted": existed}
        except FileNotFoundError:
            return {"path": str(file_path), "deleted": False}
        except Exception as e:
            logger.error("Failed to delete file {}: {}", file_path, e)
            raise


