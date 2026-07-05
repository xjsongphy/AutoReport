"""Manifest tool for agent-local file visibility and notes."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from loguru import logger

from .registry import Tool


# File patterns to ignore in manifests
IGNORED_PATTERNS = [
    # Tex compilation intermediates
    "*.aux", "*.log", "*.out", "*.toc", "*.lof", "*.lot",
    "*.fls", "*.fdb_latexmk", "*.synctex.gz", "*.synctex.gz(busy)",
    "*.bbl", "*.blg", "*.brf", "*.cb", "*.cb2", "*.bcf",
    "*.dvi", "*.ps", "*.idx", "*.ilg", "*.ind",
    "*.nav", "*.snm", "*.vrb",
    # Common junk files
    ".DS_Store", "Thumbs.db", "*.bak", "*.tmp", "*~",
    "*.swp", "*.swo", ".#*",
    # Python cache
    "__pycache__", "*.pyc", "*.pyo",
    # Git metadata (shouldn't appear but just in case)
    ".git", ".gitignore",
]
IGNORED_DIRS = {".git", "__pycache__", ".autoreport", ".checkpoints"}

AGENT_DIRECTORIES = {
    "data_analysis": ["Data", "Data/Processed"],
    "plotting": ["Data", "Data/fig", "Code"],
    "theory": ["Theory"],
    "report": ["Tex", "Data/fig", "References"],
    "main": ["Data", "Theory", "Code", "Tex", "References"],
}


def should_ignore_file(file_name: str) -> bool:
    """Check if a file should be ignored based on patterns."""
    return any(fnmatch(file_name, pattern) for pattern in IGNORED_PATTERNS)


def should_ignore_dir(dir_name: str) -> bool:
    """Check if a directory should be ignored."""
    return dir_name in IGNORED_DIRS


def _parse_json_param(value: Any) -> Any:
    """Parse JSON string parameters to Python objects.

    LLMs often serialize complex types (lists, dicts) as JSON strings.
    This helper detects and parses them when needed.
    """
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


class ManifestManager:
    """Persist and update agent manifest files.

    Manifest structure:
    - files: structured file list (program-maintained timestamps, agent-editable descriptions)
    - notes: free-form text for relationships and extra context
    """

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self.base_dir = self.workspace / ".autoreport" / "manifests"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, Any]] = {}

    def manifest_path(self, agent_type: str) -> Path:
        return self.base_dir / f"{agent_type}.json"

    def now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    async def _sync_with_filesystem(self, agent_type: str, manifest: dict[str, Any]) -> dict[str, Any]:
        """Sync manifest with actual filesystem state.

        Scans directories for this agent type and updates file list with:
        - New files added
        - Deleted files removed
        - file_updated_at synced with actual file mtime
        - Existing descriptions preserved

        Args:
            agent_type: Agent type (determines which directories to scan)
            manifest: Current manifest data

        Returns:
            Updated manifest synced with filesystem
        """
        directories = AGENT_DIRECTORIES.get(agent_type, [])

        # Scan all directories for actual files
        actual_files = {}
        for dir_name in directories:
            dir_path = self.workspace / dir_name
            if not dir_path.exists():
                continue

            try:
                for root, dirs, filenames in dir_path.walk(top_down=True):
                    dirs[:] = [d for d in dirs if not should_ignore_dir(d)]
                    for file_name in filenames:
                        if should_ignore_file(file_name):
                            continue
                        item = root / file_name
                        rel_path = item.relative_to(self.workspace).as_posix()

                        try:
                            mtime_ns = item.stat().st_mtime_ns
                            mtime_iso = datetime.fromtimestamp(
                                mtime_ns / 1e9, tz=timezone.utc
                            ).isoformat(timespec="seconds")
                            actual_files[rel_path] = {
                                "path": rel_path,
                                "file_updated_at": mtime_iso,
                            }
                        except OSError:
                            pass
            except Exception as e:
                logger.warning("Error scanning directory {}: {}", dir_path, e)

        # Merge with existing manifest (preserve descriptions)
        existing_files = {f.get("path"): f for f in manifest.get("files", []) if f.get("path")}
        merged_files = []

        # Add/update files from actual filesystem
        for path, file_data in actual_files.items():
            existing = existing_files.get(path, {})
            merged_files.append({
                "path": path,
                "description": existing.get("description", ""),
                "description_updated_at": existing.get("description_updated_at"),
                "file_updated_at": file_data["file_updated_at"],
            })

        # Sort by path for consistency
        merged_files.sort(key=lambda f: f["path"])

        manifest["files"] = merged_files
        return manifest

    def _default_manifest(self, agent_type: str) -> dict[str, Any]:
        return {
            "agent_type": agent_type,
            "updated_at": self.now(),
            "files": [],
            "notes": "",
            "notes_updated_at": None,
        }

    async def load(self, agent_type: str) -> dict[str, Any]:
        # Load from cache/disk
        if agent_type in self._cache:
            manifest = self._cache[agent_type]
        else:
            path = self.manifest_path(agent_type)
            try:
                text = await asyncio.to_thread(path.read_text, encoding="utf-8")
                data = json.loads(text)
                if not isinstance(data, dict):
                    data = self._default_manifest(agent_type)
                data.setdefault("agent_type", agent_type)
                data.setdefault("files", [])
                data.setdefault("notes", "")
                data.setdefault("notes_updated_at", None)
                self._cache[agent_type] = data
                manifest = data
            except FileNotFoundError:
                manifest = self._default_manifest(agent_type)
                self._cache[agent_type] = manifest
            except Exception as e:
                logger.warning("Failed to load manifest {}: {}", path, e)
                manifest = self._default_manifest(agent_type)
                self._cache[agent_type] = manifest

        # Sync with actual filesystem (always on load)
        manifest = await self._sync_with_filesystem(agent_type, manifest)
        self._cache[agent_type] = manifest
        return manifest

    async def save(self, agent_type: str, manifest: dict[str, Any]) -> None:
        manifest["agent_type"] = agent_type
        manifest["updated_at"] = self.now()
        path = self.manifest_path(agent_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._cache[agent_type] = manifest
        await asyncio.to_thread(
            path.write_text,
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def clear(self, agent_type: str) -> None:
        """Reset one agent manifest to default content."""
        await self.save(agent_type, self._default_manifest(agent_type))

    async def touch_files(self, agent_type: str, paths: list[str]) -> dict[str, Any]:
        """Update file timestamps in manifest (testing/helper API)."""
        manifest = await self.load(agent_type)
        now = self.now()
        file_map = {item.get("path"): item for item in manifest.get("files", []) if item.get("path")}
        for raw_path in paths:
            path = str(raw_path or "").strip()
            if not path:
                continue
            item = file_map.get(path)
            if item is None:
                item = {
                    "path": path,
                    "description": "",
                    "description_updated_at": None,
                    "file_updated_at": now,
                }
                manifest.setdefault("files", []).append(item)
                file_map[path] = item
            else:
                item["file_updated_at"] = now
        manifest["files"].sort(key=lambda f: str(f.get("path", "")))
        await self.save(agent_type, manifest)
        return manifest


class ManifestTool(Tool):
    """Read or update the local manifest for an agent.

    The structured file list is program-maintained except for descriptions,
    while notes are free-form and agent-written.

    Cross-agent viewing: You can read other agents' manifests by specifying
    the agent parameter (e.g., agent="plotting"), but you can only update
    your own manifest.
    """

    name = "manifest"
    description = (
        "Read or update agent manifests. "
        "Use it to inspect available files (including other agents' files), "
        "update short file descriptions, and add free-form notes about file relationships. "
        "Cross-agent viewing: specify agent='data_analysis', 'plotting', 'theory', or 'report' to read their manifests."
    )

    # Valid agent types for cross-agent viewing
    VALID_AGENTS = ("main", "data_analysis", "plotting", "theory", "report")

    def __init__(self, manifest_manager: ManifestManager, agent_type: str):
        self._manifest_manager = manifest_manager
        self._agent_type = agent_type

    async def __call__(
        self,
        action: str = "read",
        agent: str | None = None,
        files: list[dict[str, Any]] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Read or update the manifest.

        Args:
            action: One of: read, update.
            agent: Optional agent type to read manifest from (e.g., 'data_analysis', 'plotting').
                Only applies to read action. Defaults to self (your own manifest).
                Cannot be specified for update action (can only update your own manifest).
            files: Optional list of file records. Each record may include:
                path, description. Only description is agent-editable.
            notes: Optional free-form notes for file relationships or context.

        Returns:
            Manifest content or update status.
        """
        action = (action or "read").lower()

        # Determine target agent type
        target_agent = agent if agent else self._agent_type

        # Validate agent parameter
        if action == "read":
            if target_agent not in self.VALID_AGENTS:
                return {
                    "status": "error",
                    "error": f"Unknown agent type: {target_agent}. Valid agents: {', '.join(self.VALID_AGENTS)}"
                }
            return await self._manifest_manager.load(target_agent)

        if action != "update":
            return {"status": "error", "error": f"Unknown action: {action}"}

        # Update action: can only update own manifest
        if agent and agent != self._agent_type:
            return {
                "status": "error",
                "error": f"Cannot update other agent's manifest. You can only update your own manifest ({self._agent_type})."
            }

        manifest = await self._manifest_manager.load(self._agent_type)
        now = self._manifest_manager.now()
        file_map = {item.get("path"): item for item in manifest.get("files", []) if item.get("path")}

        # Parse JSON string parameters (LLMs may serialize complex types as strings)
        files = _parse_json_param(files)
        notes = _parse_json_param(notes)

        if files:
            for record in files:
                path = str(record.get("path", "")).strip()
                if not path:
                    continue
                item = file_map.get(path)
                if item is None:
                    item = {
                        "path": path,
                        "description": "",
                        "description_updated_at": now,
                        "file_updated_at": now,
                    }
                    manifest.setdefault("files", []).append(item)
                    file_map[path] = item
                desc = record.get("description")
                if desc is not None:
                    item["description"] = str(desc)
                    item["description_updated_at"] = now
        if notes is not None:
            manifest["notes"] = str(notes)
            manifest["notes_updated_at"] = now
        await self._manifest_manager.save(self._agent_type, manifest)
        return {"status": "ok", "manifest": manifest}
