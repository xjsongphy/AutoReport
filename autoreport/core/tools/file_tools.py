"""File operation tools."""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from ..tools.registry import Tool
from .manifest_tool import ManifestManager
from .path_utils import resolve_and_validate_path


class WriteEnabledTool(Tool):
    """Base for tools that modify files — provides write-permission checking and manifest integration."""

    def __init__(
        self,
        workspace: Path,
        write_allowed_dir: Path | None = None,
        manifest_manager: ManifestManager | None = None,
        agent_type: str | None = None,
    ):
        if (manifest_manager is None) != (agent_type is None):
            raise ValueError(
                "manifest_manager and agent_type must be both set or both None"
            )
        self.workspace = Path(workspace).resolve()
        self.write_allowed_dir = Path(write_allowed_dir).resolve() if write_allowed_dir else None
        self._manifest_manager = manifest_manager
        self._agent_type = agent_type

    def _check_write_permission(self, file_path: Path, action: str = "Write") -> None:
        if not self.write_allowed_dir:
            return
        try:
            file_path.relative_to(self.write_allowed_dir)
        except ValueError:
            raise PermissionError(
                f"{action} not allowed outside {self.write_allowed_dir}. Attempted: {file_path}"
            )

    async def _touch_manifest(self, file_path: Path) -> None:
        if self._manifest_manager:
            posix_path = file_path.relative_to(self.workspace).as_posix()
            await self._manifest_manager.touch_files(self._agent_type, [posix_path])

    async def _remove_from_manifest(self, file_path: Path) -> None:
        if self._manifest_manager:
            posix_path = file_path.relative_to(self.workspace).as_posix()
            await self._manifest_manager.remove_files(self._agent_type, [posix_path])


class ReadFileTool(Tool):
    """Tool for reading files."""

    name = "read_file"
    description = "Read the contents of a file. Supports line ranges."

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()

    async def __call__(
        self,
        path: str,
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Read a file.

        Args:
            path: Path to file (relative to workspace)
            offset: Optional starting line number (0-indexed)
            limit: Optional maximum number of lines to read

        Returns:
            Dictionary with content, line_count, and path

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
        """
        file_path = resolve_and_validate_path(path, self.workspace)
        logger.debug("Reading file: {}", file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            line_count = len(lines)

            if offset is not None:
                end = (offset + limit) if limit is not None else None
                lines = lines[offset:end]

            content = "".join(lines)

            return {
                "path": str(file_path),
                "content": content,
                "line_count": line_count,
                "lines_read": len(lines),
            }
        except Exception as e:
            logger.error("Failed to read file {}: {}", file_path, e)
            raise


class WriteFileTool(WriteEnabledTool):
    """Tool for writing files."""

    name = "write_file"
    description = "Write content to a file. Creates parent directories if needed."

    async def __call__(
        self,
        path: str,
        content: str,
        create_backup: bool = True,
    ) -> dict[str, Any]:
        """Write to a file.

        Args:
            path: Path to file (relative to workspace)
            content: Content to write
            create_backup: Whether to create backup before overwriting

        Returns:
            Dictionary with path and backup_path (if created)

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
            PermissionError: If write not allowed in target directory.
        """
        file_path = resolve_and_validate_path(path, self.workspace)
        logger.debug("Writing file: {}", file_path)

        self._check_write_permission(file_path)

        try:
            backup_path = None
            if create_backup:
                try:
                    backup_path = file_path.with_suffix(f"{file_path.suffix}.bak")
                    await asyncio.to_thread(backup_path.write_bytes, file_path.read_bytes())
                except FileNotFoundError:
                    pass

            file_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")

            result = {
                "path": str(file_path),
                "success": True,
            }
            if backup_path:
                result["backup_path"] = str(backup_path)
            await self._touch_manifest(file_path)

            return result
        except Exception as e:
            logger.error("Failed to write file {}: {}", file_path, e)
            raise


class EditFileTool(WriteEnabledTool):
    """Tool for editing files by text replacement."""

    name = "edit_file"
    description = "Replace text in a file. Finds old_text and replaces with new_text."

    async def __call__(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
    ) -> dict[str, Any]:
        """Edit a file by replacing text.

        Args:
            path: Path to file (relative to workspace)
            old_text: Text to find and replace
            new_text: Replacement text
            replace_all: Replace all occurrences (default: False, replaces first only)

        Returns:
            Dictionary with path and replacements_made

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
            PermissionError: If write not allowed in target directory.
        """
        file_path = resolve_and_validate_path(path, self.workspace)
        logger.debug("Editing file: {}", file_path)

        self._check_write_permission(file_path)

        try:
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")

            if not old_text:
                raise ValueError("old_text must be non-empty")

            if replace_all:
                new_content = content.replace(old_text, new_text)
                replacements = content.count(old_text)
            else:
                if old_text not in content:
                    raise ValueError(f"old_text not found in file: {file_path}")
                new_content = content.replace(old_text, new_text, 1)
                replacements = 1

            await asyncio.to_thread(file_path.write_text, new_content, encoding="utf-8")
            await self._touch_manifest(file_path)

            return {
                "path": str(file_path),
                "replacements_made": replacements,
            }
        except Exception as e:
            logger.error("Failed to edit file {}: {}", file_path, e)
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
            existed = True
            try:
                await asyncio.to_thread(file_path.unlink)
            except FileNotFoundError:
                existed = False

            await self._remove_from_manifest(file_path)
            return {"path": str(file_path), "deleted": existed}
        except Exception as e:
            logger.error("Failed to delete file {}: {}", file_path, e)
            raise


class ListDirTool(Tool):
    """Tool for listing directory contents."""

    name = "list_dir"
    description = "List contents of a directory."

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()

    async def __call__(
        self,
        path: str = ".",
        recursive: bool = False,
    ) -> dict[str, Any]:
        """List directory contents.

        Args:
            path: Path to directory (relative to workspace)
            recursive: Whether to list recursively

        Returns:
            Dictionary with directories, files, and path

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
        """
        dir_path = resolve_and_validate_path(path, self.workspace)
        logger.debug("Listing directory: {}", dir_path)

        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {dir_path}")

        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        try:
            directories = []
            files = []

            if recursive:
                for item in sorted(dir_path.rglob("*")):
                    if item.is_dir():
                        directories.append(item.relative_to(dir_path).as_posix())
                    else:
                        files.append(item.relative_to(dir_path).as_posix())
            else:
                for item in sorted(dir_path.iterdir()):
                    if item.is_dir():
                        directories.append(item.name)
                    else:
                        files.append(item.name)

            return {
                "path": str(dir_path),
                "directories": directories,
                "files": files,
                "count": len(directories) + len(files),
            }
        except Exception as e:
            logger.error("Failed to list directory {}: {}", dir_path, e)
            raise
