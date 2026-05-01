"""Per-project conversation persistence using JSONL.

Stores agent conversations under ``workspace/.autoreport/conversations/``
with subdirectories per agent type and one JSONL file per session.
Supports multiple conversation sessions (Cline-style) with session metadata.

Inspired by Codex's rollout JSONL and nanobot's session manager.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

_AGENT_TYPES = ["main", "data_analysis", "plotting", "theory", "report"]


class ConversationStore:
    """Manage conversation persistence for a project workspace.

    Layout::

        workspace/.autoreport/
        └── conversations/
            ├── sessions.json          # Session metadata
            ├── main/
            │   ├── {session_id}.jsonl
            │   └── ...
            ├── data_analysis/
            │   └── ...
            └── ...
    """

    def __init__(self, workspace: Path):
        self._dir = Path(workspace).resolve() / ".autoreport" / "conversations"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._sessions_file = self._dir / "sessions.json"
        self._current_session_ids: dict[str, str] = {}  # per-agent session tracking
        self._migrate_old_files()
        self._load_or_create_sessions()

    # ---- Migration ----

    def _migrate_old_files(self) -> None:
        """Migrate old flat .jsonl files into session-based subdirectories."""
        old_files = [self._dir / f"{t}.jsonl" for t in _AGENT_TYPES]
        existing = [f for f in old_files if f.exists()]
        if not existing:
            return

        # Check if sessions.json already exists (already migrated)
        if self._sessions_file.exists():
            return

        # Create a session for the old content
        session_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat(timespec="seconds")

        for old_file in existing:
            agent_type = old_file.stem
            agent_dir = self._dir / agent_type
            agent_dir.mkdir(parents=True, exist_ok=True)
            new_file = agent_dir / f"{session_id}.jsonl"
            old_file.rename(new_file)
            logger.info("Migrated {} -> {}", old_file.name, new_file)

        sessions = [{"id": session_id, "name": "历史对话", "timestamp": timestamp, "preview": ""}]
        self._save_sessions_metadata(sessions)

    # ---- Session Management ----

    def _load_or_create_sessions(self) -> None:
        """Initialize session IDs for all agent types independently."""
        sessions = self._load_sessions_metadata()
        if not sessions:
            # Create initial session for all agents
            session_id = self._create_new_session("新对话")
            for t in _AGENT_TYPES:
                self._current_session_ids[t] = session_id
        else:
            # Each agent gets its own latest session (or first available)
            for t in _AGENT_TYPES:
                # Try to find an existing session file for this agent
                agent_dir = self._dir / t
                if agent_dir.exists():
                    jsonl_files = sorted(agent_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if jsonl_files:
                        self._current_session_ids[t] = jsonl_files[0].stem
                    else:
                        self._current_session_ids[t] = sessions[0]["id"]
                else:
                    self._current_session_ids[t] = sessions[0]["id"]

    def _load_sessions_metadata(self) -> list[dict]:
        if not self._sessions_file.exists():
            return []
        try:
            with open(self._sessions_file, "r", encoding="utf-8") as f:
                sessions = json.load(f)
            sessions.sort(key=lambda s: s.get("timestamp", ""), reverse=True)
            return sessions
        except (json.JSONDecodeError, OSError):
            return []

    def _save_sessions_metadata(self, sessions: list[dict]) -> None:
        try:
            with open(self._sessions_file, "w", encoding="utf-8") as f:
                json.dump(sessions, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("Failed to save sessions metadata: {}", e)

    def _create_new_session(self, name: str = "新对话") -> str:
        session_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat(timespec="seconds")
        sessions = self._load_sessions_metadata()
        sessions.insert(0, {"id": session_id, "name": name, "timestamp": timestamp, "preview": ""})
        self._save_sessions_metadata(sessions)
        return session_id

    def _get_session_file_path(self, agent_type: str) -> Path:
        session_id = self.get_current_session_id(agent_type)
        agent_dir = self._dir / agent_type
        agent_dir.mkdir(parents=True, exist_ok=True)
        return agent_dir / f"{session_id}.jsonl"

    def get_sessions(self) -> list[dict]:
        return self._load_sessions_metadata()

    def get_current_session_id(self, agent_type: str = "main") -> str:
        if agent_type not in self._current_session_ids:
            self._current_session_ids[agent_type] = self._create_new_session()
        return self._current_session_ids[agent_type]

    def switch_session(self, session_id: str, agent_type: str = "main") -> bool:
        sessions = self._load_sessions_metadata()
        for s in sessions:
            if s["id"] == session_id:
                self._current_session_ids[agent_type] = session_id
                return True
        return False

    def new_session(self, name: str = "新对话", agent_type: str = "main") -> str:
        session_id = self._create_new_session(name)
        self._current_session_ids[agent_type] = session_id
        return session_id

    def rename_session(self, session_id: str, new_name: str) -> bool:
        sessions = self._load_sessions_metadata()
        for s in sessions:
            if s["id"] == session_id:
                s["name"] = new_name
                self._save_sessions_metadata(sessions)
                return True
        return False

    def delete_session(self, session_id: str) -> bool:
        sessions = self._load_sessions_metadata()
        sessions = [s for s in sessions if s["id"] != session_id]
        self._save_sessions_metadata(sessions)

        for agent_type in _AGENT_TYPES:
            f = self._dir / agent_type / f"{session_id}.jsonl"
            if f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass

        # Clear the session from all agent tracking
        for agent_type in self._current_session_ids:
            if self._current_session_ids[agent_type] == session_id:
                if sessions:
                    self._current_session_ids[agent_type] = sessions[0]["id"]
                else:
                    self._current_session_ids[agent_type] = self._create_new_session()
        return True

    def update_session_preview(self, agent_type: str, content: str) -> None:
        session_id = self.get_current_session_id(agent_type)
        sessions = self._load_sessions_metadata()
        for s in sessions:
            if s["id"] == session_id:
                preview = content.split("\n")[0][:100]
                s["preview"] = preview
                self._save_sessions_metadata(sessions)
                break

    def rename_current_session_from_first_message(self, agent_type: str, content: str) -> None:
        """Auto-name the session from the first user message (max 30 chars)."""
        session_id = self.get_current_session_id(agent_type)
        sessions = self._load_sessions_metadata()
        for s in sessions:
            if s["id"] == session_id and s["name"] in ("新对话", "未命名对话"):
                name = content.strip()[:30]
                if name:
                    s["name"] = name
                    self._save_sessions_metadata(sessions)
                break

    # ---- Write ----

    def append_message(
        self, agent_type: str, role: str, content: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "role": role,
            "content": content,
        }
        if extra:
            record.update(extra)

        # Auto-name session from first user message to main agent
        if agent_type == "main" and role == "user":
            self.rename_current_session_from_first_message(agent_type, content)
            self.update_session_preview(agent_type, content)

        path = self._get_session_file_path(agent_type)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to append conversation: {}", e)

    def append_tool_call(self, agent_type: str, tool_name: str, arguments: dict) -> None:
        self.append_message(agent_type, "tool_call", tool_name, {"arguments": arguments})

    def append_tool_result(
        self, agent_type: str, tool_name: str,
        result: str | None = None, error: str | None = None,
    ) -> None:
        extra: dict[str, Any] = {"tool": tool_name}
        if error:
            extra["error"] = error
        elif result:
            extra["result"] = result[:2000]
        self.append_message(agent_type, "tool_result", tool_name, extra)

    # ---- Read ----

    def load_messages(self, agent_type: str, limit: int = 500) -> list[dict[str, Any]]:
        path = self._get_session_file_path(agent_type)
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError as e:
            logger.warning("Failed to load conversation: {}", e)
            return []
        if len(records) > limit:
            records = records[-limit:]
        return records

    def get_last_user_message(self, agent_type: str) -> str | None:
        records = self.load_messages(agent_type, limit=20)
        for rec in reversed(records):
            if rec.get("role") == "user":
                return rec.get("content")
        return None

    # ---- Lifecycle ----

    def clear_current_session(self) -> None:
        """Clear message files for all current sessions across all agent types."""
        for agent_type in _AGENT_TYPES:
            session_id = self._current_session_ids.get(agent_type)
            if session_id:
                f = self._dir / agent_type / f"{session_id}.jsonl"
                if f.exists():
                    f.unlink()

    def clear(self, agent_type: str) -> None:
        path = self._get_session_file_path(agent_type)
        if path.exists():
            path.unlink()
            logger.debug("Cleared conversation for {}", agent_type)

    def get_agent_types_with_history(self) -> list[str]:
        result = []
        for agent_type in _AGENT_TYPES:
            session_id = self._current_session_ids.get(agent_type)
            if session_id:
                f = self._dir / agent_type / f"{session_id}.jsonl"
                if f.exists():
                    result.append(agent_type)
        return result
