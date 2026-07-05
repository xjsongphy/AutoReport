"""Recent projects cache service (VSCode-style).

Stores recently opened workspaces in a JSON file for quick access.
"""

import json
from datetime import datetime
from pathlib import Path

from loguru import logger


class RecentProjects:
    """Manage recently opened projects cache."""

    MAX_ENTRIES = 10
    STORAGE_FILE = Path.home() / ".autoreport" / "recent_projects.json"

    def __init__(self) -> None:
        """Initialize recent projects manager."""
        self._storage_dir = self.STORAGE_FILE.parent
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: list[dict] = self._load()

    def _load(self) -> list[dict]:
        """Load recent projects from storage."""
        if not self.STORAGE_FILE.exists():
            return []

        try:
            data = json.loads(self.STORAGE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as e:
            logger.warning("Failed to load recent projects: {}", e)

        return []

    def _save(self) -> None:
        """Save recent projects to storage."""
        try:
            self.STORAGE_FILE.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save recent projects: {}", e)

    def add(self, path: Path) -> None:
        """Add a project to recent list.

        Args:
            path: Project workspace path.
        """
        path_str = str(path.resolve())

        # Remove existing entry if present (will be re-added at top)
        self._cache = [e for e in self._cache if e.get("path") != path_str]

        # Add new entry at the beginning
        entry = {
            "path": path_str,
            "name": path.name,
            "last_opened": datetime.now().isoformat(),
        }
        self._cache.insert(0, entry)

        # Limit to MAX_ENTRIES
        if len(self._cache) > self.MAX_ENTRIES:
            self._cache = self._cache[: self.MAX_ENTRIES]

        self._save()
        logger.debug("Added to recent projects: {}", path_str)

    def remove(self, path: Path) -> None:
        """Remove a project from recent list.

        Args:
            path: Project workspace path.
        """
        path_str = str(path.resolve())
        before = len(self._cache)
        self._cache = [e for e in self._cache if e.get("path") != path_str]
        if len(self._cache) < before:
            self._save()
            logger.debug("Removed from recent projects: {}", path_str)

    def get_all(self) -> list[Path]:
        """Get all recent projects.

        Returns:
            List of project paths, most recent first.
        """
        result = []
        for entry in self._cache:
            path_str = entry.get("path")
            if path_str:
                path = Path(path_str)
                if path.exists():
                    result.append(path)

        # Update cache to remove non-existent paths
        if len(result) < len(self._cache):
            self._cache = [
                e for e in self._cache
                if Path(e.get("path", "")).exists()
            ]
            self._save()

        return result

    def clear(self) -> None:
        """Clear all recent projects."""
        self._cache = []
        self._save()
        logger.info("Cleared recent projects")
