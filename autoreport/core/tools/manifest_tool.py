"""Manifest tool for agent-local file visibility and notes."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from .registry import Tool


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

    def _default_manifest(self, agent_type: str) -> dict[str, Any]:
        return {
            "agent_type": agent_type,
            "updated_at": self.now(),
            "files": [],
            "notes": "",
        }

    async def load(self, agent_type: str) -> dict[str, Any]:
        if agent_type in self._cache:
            return self._cache[agent_type]

        path = self.manifest_path(agent_type)
        try:
            text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, dict):
                return self._default_manifest(agent_type)
            data.setdefault("agent_type", agent_type)
            data.setdefault("files", [])
            data.setdefault("notes", "")
            self._cache[agent_type] = data
            return data
        except FileNotFoundError:
            return self._default_manifest(agent_type)
        except Exception as e:
            logger.warning("Failed to load manifest {}: {}", path, e)
            return self._default_manifest(agent_type)

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

    async def touch_files(self, agent_type: str, paths: list[str]) -> None:
        if not paths:
            return
        manifest = await self.load(agent_type)
        now = self.now()
        file_map = {item.get("path"): item for item in manifest.get("files", []) if item.get("path")}
        for rel_path in paths:
            item = file_map.get(rel_path)
            if item is None:
                item = {
                    "path": rel_path,
                    "description": "",
                    "file_updated_at": now,
                }
                manifest.setdefault("files", []).append(item)
                file_map[rel_path] = item
            else:
                item["file_updated_at"] = now
        await self.save(agent_type, manifest)

    async def remove_files(self, agent_type: str, paths: list[str]) -> None:
        if not paths:
            return
        manifest = await self.load(agent_type)
        current = manifest.get("files", [])
        path_set = set(paths)
        manifest["files"] = [item for item in current if item.get("path") not in path_set]
        await self.save(agent_type, manifest)


class ManifestTool(Tool):
    """Read or update the local manifest for an agent.

    The structured file list is program-maintained except for descriptions,
    while notes are free-form and agent-written.
    """

    name = "manifest"
    description = (
        "Read or update the local manifest for this agent. "
        "Use it to inspect available files, update short file descriptions, "
        "and add free-form notes about file relationships or context."
    )

    def __init__(self, manifest_manager: ManifestManager, agent_type: str):
        self._manifest_manager = manifest_manager
        self._agent_type = agent_type

    async def __call__(
        self,
        action: str = "read",
        files: list[dict[str, Any]] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Read or update the manifest.

        Args:
            action: One of: read, update.
            files: Optional list of file records. Each record may include:
                path, description. Only description is agent-editable.
            notes: Optional free-form notes for file relationships or context.

        Returns:
            Manifest content or update status.
        """
        action = (action or "read").lower()
        if action == "read":
            return await self._manifest_manager.load(self._agent_type)

        if action != "update":
            return {"status": "error", "error": f"Unknown action: {action}"}

        manifest = await self._manifest_manager.load(self._agent_type)
        now = self._manifest_manager.now()
        file_map = {item.get("path"): item for item in manifest.get("files", []) if item.get("path")}
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
        await self._manifest_manager.save(self._agent_type, manifest)
        return {"status": "ok", "manifest": manifest}
