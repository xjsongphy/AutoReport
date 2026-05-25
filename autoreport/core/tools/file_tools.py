"""File operation tools."""

import asyncio
import difflib
import re
from pathlib import Path
from typing import Any

from loguru import logger

from ..tools.registry import Tool
from .file_state import FileStateManager
from .manifest_tool import ManifestManager
from .path_utils import resolve_and_validate_path, suggest_canonical_path


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

    def _is_internal_metadata_path(self, file_path: Path) -> bool:
        """Check if path is in internal metadata directories (.autoreport, .checkpoints)."""
        try:
            rel = file_path.relative_to(self.workspace)
        except ValueError:
            return False
        return rel.parts and rel.parts[0] in {".autoreport", ".checkpoints"}

    def _check_write_permission(self, file_path: Path, action: str = "Write") -> None:
        if self._is_internal_metadata_path(file_path):
            raise PermissionError(
                f"{action} not allowed in internal metadata directories (.autoreport, .checkpoints). Attempted: {file_path}"
            )

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

    def __init__(self, workspace: Path, file_state_manager: FileStateManager | None = None):
        self.workspace = Path(workspace).resolve()
        self._file_state_manager = file_state_manager

    def _is_internal_metadata_path(self, file_path: Path) -> bool:
        """Check if path is in internal metadata directories (.autoreport, .checkpoints)."""
        try:
            rel = file_path.relative_to(self.workspace)
        except ValueError:
            return False
        return rel.parts and rel.parts[0] in {".autoreport", ".checkpoints"}

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

        if self._is_internal_metadata_path(file_path):
            raise PermissionError("Access to internal metadata under .autoreport is not allowed.")

        if not file_path.exists():
            suggestion = suggest_canonical_path(path)
            hint = f" Did you mean '{suggestion}'?" if suggestion and suggestion != path else ""
            raise FileNotFoundError(f"File not found: {file_path}.{hint}")

        if file_path.suffix.lower() == ".pdf":
            raise ValueError(
                f"read_file does not support PDF files: {file_path.name}. "
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
                         f"The read_file tool only supports UTF-8 text files. If you need to work with this file type, "
                         f"please use a different approach (e.g., bash for file analysis).",
                "path": str(file_path),
                "is_binary": True,
                "detected_type": detected_type,
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

        # Check read-before-write safety for existing files
        if file_path.exists():
            safety = self._check_file_safety(file_path)
            if safety and safety["warning"]:
                logger.warning("File safety warning suppressed write: {}", safety["warning"])
                return safety

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
    """Tool for editing files by text replacement with fuzzy matching fallback."""

    name = "edit_file"
    description = (
        "Replace text in a file. Finds old_text and replaces with new_text. "
        "Always use read_file first to get the exact content before editing. "
        "If exact match fails, the tool will attempt fuzzy matching and show a diff of the closest match."
    )

    def _normalize_quotes(self, text: str) -> str:
        """Normalize various quote styles to ASCII double quotes for matching."""
        return (
            text.replace("'", '"')
            .replace("`", '"')
            .replace("\u2018", '"')   # '
            .replace("\u2019", '"')   # '
            .replace("\u201c", '"')   # "
            .replace("\u201d", '"')   # "
            .replace("\u00b4", '"')   # ´
            .replace("\u02bc", '"')   # ʼ
        )

    def _strip_line_whitespace(self, text: str) -> str:
        """Strip leading/trailing whitespace from each line."""
        return "\n".join(line.strip() for line in text.splitlines())

    def _sliding_window_search(self, content_lines, old_lines, match_fn) -> int | None:
        """Slide a window over content_lines looking for the best match."""
        n_old = len(old_lines)
        if n_old == 0 or n_old > len(content_lines):
            return None

        # Collect all windows with their match score
        candidates = []
        for i in range(len(content_lines) - n_old + 1):
            window = content_lines[i:i + n_old]
            window_text = "\n".join(window)
            old_text = "\n".join(old_lines)
            try:
                match = match_fn(window_text, old_text)
                if match:
                    score = difflib.SequenceMatcher(None, window_text, old_text).ratio()
                    candidates.append((score, i, window_text))
            except (ValueError, TypeError):
                continue

        if not candidates:
            return None

        # Return the best match position
        candidates.sort(key=lambda x: -x[0])
        best_score = candidates[0][0]
        if best_score >= 0.6:  # Require at least 60% similarity
            return candidates[0][1]
        return None

    def _try_exact_match(self, content: str, old_text: str) -> int | None:
        """Level 1: Exact match."""
        idx = content.find(old_text)
        if idx >= 0:
            return idx
        return None

    def _try_strip_window_match(self, content: str, old_text: str) -> tuple[int | None, str | None]:
        """Level 2: Strip whitespace from each line, then sliding window match.

        Returns:
            (position_in_content, matched_text) or (None, None)
        """
        content_lines = content.splitlines(keepends=False)
        old_lines = old_text.splitlines(keepends=False)

        stripped_content = self._strip_line_whitespace(content)
        stripped_old = self._strip_line_whitespace(old_text)
        stripped_content_lines = stripped_content.splitlines(keepends=False)
        stripped_old_lines = stripped_old.splitlines(keepends=False)

        idx = self._sliding_window_search(
            content_lines,
            old_lines,
            lambda w, o: self._strip_line_whitespace(w) == self._strip_line_whitespace(o),
        )
        if idx is not None:
            matched_text = "\n".join(content_lines[idx:idx + len(old_lines)])
            # Determine character position
            char_pos = sum(len(line) + 1 for line in content_lines[:idx])
            return char_pos, matched_text
        return None, None

    def _try_quote_normalize_match(self, content: str, old_text: str) -> tuple[int | None, str | None]:
        """Level 3: Normalize quotes, then sliding window."""
        content_lines = content.splitlines(keepends=False)
        old_lines = old_text.splitlines(keepends=False)

        idx = self._sliding_window_search(
            content_lines,
            old_lines,
            lambda w, o: self._normalize_quotes(w) == self._normalize_quotes(o),
        )
        if idx is not None:
            matched_text = "\n".join(content_lines[idx:idx + len(old_lines)])
            char_pos = sum(len(line) + 1 for line in content_lines[:idx])
            return char_pos, matched_text
        return None, None

    def _try_quote_normalize_strip_window(self, content: str, old_text: str) -> tuple[int | None, str | None]:
        """Level 4: Normalize quotes AND strip whitespace, then sliding window.

        This catches the combination of quote style + whitespace differences.
        """
        content_lines = content.splitlines(keepends=False)
        old_lines = old_text.splitlines(keepends=False)

        idx = self._sliding_window_search(
            content_lines,
            old_lines,
            lambda w, o: (
                self._normalize_quotes(self._strip_line_whitespace(w))
                == self._normalize_quotes(self._strip_line_whitespace(o))
            ),
        )
        if idx is not None:
            matched_text = "\n".join(content_lines[idx:idx + len(old_lines)])
            char_pos = sum(len(line) + 1 for line in content_lines[:idx])
            return char_pos, matched_text
        return None, None

    def _make_diff_feedback(self, file_path: Path, old_text: str, matched_text: str) -> str:
        """Generate unified diff between what the agent wanted and what was found.

        This helps the agent correct its edit request.
        """
        old_lines = old_text.splitlines(keepends=True)
        matched_lines = matched_text.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            matched_lines,
            fromfile="your edit (old_text)",
            tofile=f"file content ({file_path.name})",
            lineterm="\n",
        )
        return "".join(diff)

    async def __call__(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
    ) -> dict[str, Any]:
        """Edit a file by replacing text, with fuzzy matching fallback.

        Args:
            path: Path to file (relative to workspace)
            old_text: Text to find and replace
            new_text: Replacement text
            replace_all: Replace all occurrences (default: False, replaces first only)

        Returns:
            Dictionary with path and replacements_made, or warning + diff feedback.

        Raises:
            ValueError: If path is outside workspace or contains path traversal.
            PermissionError: If write not allowed in target directory.
        """
        file_path = resolve_and_validate_path(path, self.workspace)
        logger.debug("Editing file: {}", file_path)

        self._check_write_permission(file_path)

        # Check read-before-edit safety
        safety = self._check_file_safety(file_path)
        if safety and safety["warning"]:
            logger.warning("File safety warning suppressed edit: {}", safety["warning"])
            return safety

        if not old_text:
            raise ValueError("old_text must be non-empty")

        try:
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("Binary file detected (not UTF-8): {}", file_path)
            return {
                "error": f"Cannot edit '{file_path.name}' as text: it appears to be a binary file (not UTF-8 encoded). "
                         f"The edit_file tool only supports UTF-8 text files.",
                "path": str(file_path),
                "is_binary": True,
            }
        except FileNotFoundError:
            return {"error": f"File not found: {file_path}", "path": str(file_path)}

        # --- Attempt matching in order of strictness ---

        # Level 1: Exact match (fast path)
        pos = self._try_exact_match(content, old_text)
        matched_text = old_text

        if pos is None:
            # Level 2: Strip whitespace + sliding window
            pos, matched_text = self._try_strip_window_match(content, old_text)

        if pos is None:
            # Level 3: Quote normalization + sliding window
            pos, matched_text = self._try_quote_normalize_match(content, old_text)

        if pos is None:
            # Level 4: Quote normalization + strip whitespace + sliding window
            pos, matched_text = self._try_quote_normalize_strip_window(content, old_text)

        if pos is None:
            # All levels failed — show diff feedback of the closest match
            content_lines = content.splitlines(keepends=False)
            old_lines = old_text.splitlines(keepends=False)
            # Find the single best-scoring window for feedback
            best_score = 0
            best_window = None
            for i in range(len(content_lines) - len(old_lines) + 1 if len(old_lines) <= len(content_lines) else 0):
                window = "\n".join(content_lines[i:i + len(old_lines)])
                score = difflib.SequenceMatcher(None, window, old_text).ratio()
                if score > best_score:
                    best_score = score
                    best_window = window

            feedback = ""
            if best_window and best_score > 0:
                diff_text = self._make_diff_feedback(file_path, old_text, best_window)
                feedback = (
                    f"\n\n--- Closest match (similarity: {best_score:.0%}) ---\n"
                    f"{diff_text}\n"
                    f"--- End diff ---\n"
                )

            return {
                "error": (
                    f"old_text not found in file after trying 4 levels of fuzzy matching "
                    f"(exact, whitespace-tolerant, quote-normalized, combined). "
                    f"Use read_file to get the current file content, then provide exact old_text.\n"
                    f"Tip: edit_file uses SEARCH/REPLACE — copy-paste the exact lines from read_file output."
                ),
                "path": str(file_path),
                "fuzzy_match_failed": True,
                "diff_feedback": feedback,
            }

        # We have a match — perform the replacement
        end_pos = pos + len(matched_text)
        if replace_all:
            # For replace_all, we need to replace ALL occurrences of the matched text
            new_content = content.replace(matched_text, new_text)
            replacements = content.count(matched_text)
        else:
            new_content = content[:pos] + new_text + content[end_pos:]
            replacements = 1

        # Check if this is a no-op (nothing changed)
        if content == new_content:
            return {
                "path": str(file_path),
                "replacements_made": 0,
                "info": "old_text and new_text are identical — no changes made.",
            }

        await asyncio.to_thread(file_path.write_text, new_content, encoding="utf-8")
        await self._touch_manifest(file_path)

        # Record new file state after edit
        if self._file_state_manager:
            self._file_state_manager.record_read(file_path)

        return {
            "path": str(file_path),
            "replacements_made": replacements,
            "fuzzy_matched": matched_text != old_text,
        }


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

    def _is_internal_metadata_rel(self, rel_posix: str) -> bool:
        """Check if relative path is in internal metadata directories."""
        return (rel_posix in {".autoreport", ".checkpoints"} or
                rel_posix.startswith(".autoreport/") or
                rel_posix.startswith(".checkpoints/"))

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
            suggestion = suggest_canonical_path(path)
            hint = f" Did you mean '{suggestion}'?" if suggestion and suggestion != path else ""
            raise FileNotFoundError(f"Directory not found: {dir_path}.{hint}")

        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        try:
            directories = []
            files = []

            if recursive:
                for item in sorted(dir_path.rglob("*")):
                    rel = item.relative_to(dir_path).as_posix()
                    if self._is_internal_metadata_rel(rel):
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
                "directories": directories,
                "files": files,
                "count": len(directories) + len(files),
            }
        except Exception as e:
            logger.error("Failed to list directory {}: {}", dir_path, e)
            raise
