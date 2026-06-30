"""File state tracker: enforces read-before-edit and detects stale files.

Tracks which files an agent has read, along with the file's mtime and SHA-256
hash at the time of reading. Write tools can then check whether the file has
been read and whether it has changed since the last read.
"""

import hashlib
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from loguru import logger


class FileState:
    """Snapshot of a file's state at the time it was read."""

    __slots__ = ("mtime", "size", "hash", "read_at")

    def __init__(self, mtime: float, size: int, hash: str, read_at: float | None = None):
        self.mtime = mtime
        self.size = size
        self.hash = hash
        self.read_at = read_at if read_at is not None else time.time()

    @classmethod
    def from_file(cls, path: Path) -> "FileState":
        """Capture current state of a file on disk."""
        stat = path.stat()
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return cls(
            mtime=stat.st_mtime_ns if hasattr(stat, "st_mtime_ns") else stat.st_mtime,
            size=stat.st_size,
            hash=sha256.hexdigest(),
        )

    def matches_current(self, path: Path) -> Tuple[bool, "FileState"]:
        """Check if the file on disk still matches this recorded state.

        Returns:
            (is_match, current_state)
        """
        try:
            current = FileState.from_file(path)
        except FileNotFoundError:
            return False, None

        match = (self.mtime == current.mtime and self.size == current.size and self.hash == current.hash)
        return match, current


class FileStateManager:
    """Manages file read-state tracking per agent session."""

    def __init__(self, workspace: Path | None = None):
        self.workspace = Path(workspace).resolve() if workspace is not None else None
        self._states: Dict[str, FileState] = {}

    def _display_path(self, file_path: Path) -> str:
        """Return a tool-friendly relative path when workspace is known."""
        if self.workspace is not None:
            try:
                return file_path.relative_to(self.workspace).as_posix()
            except ValueError:
                pass
        return file_path.name

    def record_read(self, file_path: Path) -> None:
        """Record the current state of a file after reading it.

        Args:
            file_path: Absolute path to the file that was read.
        """
        try:
            state = FileState.from_file(file_path)
            self._states[str(file_path)] = state
            logger.debug("FileState recorded: {} (hash={}..., mtime={})",
                         file_path.name, state.hash[:12], state.mtime)
        except FileNotFoundError:
            pass

    def get_state(self, file_path: Path) -> Optional[FileState]:
        """Get recorded state for a file, if any.

        Args:
            file_path: Absolute path to the file.

        Returns:
            FileState or None if never read.
        """
        return self._states.get(str(file_path))

    def check_read_before_write(self, file_path: Path) -> Dict:
        """Check whether a file has been read and whether it has gone stale.

        Returns a dict with:
            - has_read: bool — whether the file was read before
            - is_stale: bool — whether the file has changed since last read
            - warning: str | None — human-readable warning message for the agent
            - state: FileState | None — recorded state if any
        """
        key = str(file_path)
        recorded = self._states.get(key)

        if recorded is None:
            display_path = self._display_path(file_path)
            return {
                "has_read": False,
                "is_stale": False,
                "warning": (
                    f"⚠️ You are about to modify '{file_path.name}' without having read it first. "
                    f"Use read('{display_path}') first to "
                    f"see the current content and avoid accidentally overwriting changes."
                ),
                "state": None,
            }

        try:
            match, current = recorded.matches_current(file_path)
            if not match:
                return {
                    "has_read": True,
                    "is_stale": True,
                    "warning": (
                        f"⚠️ '{file_path.name}' has changed since you last read it "
                        f"(mtime or content hash differ). "
                        f"Use read to see the latest version before editing."
                    ),
                    "state": recorded,
                }
        except FileNotFoundError:
            return {
                "has_read": True,
                "is_stale": True,
                "warning": (
                    f"⚠️ '{file_path.name}' no longer exists on disk since you read it. "
                    f"Use read to verify current state."
                ),
                "state": recorded,
            }

        return {
            "has_read": True,
            "is_stale": False,
            "warning": None,
            "state": recorded,
        }

    def clear(self) -> None:
        """Clear all tracked file states."""
        self._states.clear()
        logger.debug("FileStateManager cleared all states")
