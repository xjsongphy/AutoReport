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
from ..utils.editor_context import parse_editor_context, user_visible_content

_AGENT_TYPES = ["main", "data_analysis", "plotting", "theory", "report"]


def _user_visible_content_or_empty(content: str) -> str:
    text = str(content or "")
    visible = user_visible_content(text).strip()
    if text.startswith("Editor context: ") and visible == text:
        return ""
    return visible


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
        self._load_sessions_without_creating()

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
                agent_dir = self._dir / t
                if agent_dir.exists():
                    jsonl_files = sorted(agent_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if jsonl_files:
                        self._current_session_ids[t] = jsonl_files[0].stem
                    else:
                        self._current_session_ids[t] = sessions[0]["id"]
                else:
                    self._current_session_ids[t] = sessions[0]["id"]

    def _load_sessions_without_creating(self) -> None:
        """Load session IDs without auto-creating new ones.

        Session IDs are lazily created on first append_message call.
        No sessions.json is written on startup.
        """
        sessions = self._load_sessions_metadata()
        if not sessions:
            return  # No sessions yet — will be created lazily on first message
        # Load latest session for each agent type
        for t in _AGENT_TYPES:
            agent_dir = self._dir / t
            if agent_dir.exists():
                jsonl_files = sorted(agent_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
                if jsonl_files:
                    self._current_session_ids[t] = jsonl_files[0].stem
            # If no files for this agent, leave unset (will be lazily created)

    def _ensure_session(self, agent_type: str) -> None:
        """Lazily create an in-memory session id for the agent.

        Metadata is persisted only on first actual write.
        """
        if agent_type in self._current_session_ids and self._current_session_ids[agent_type]:
            return
        self._current_session_ids[agent_type] = str(uuid.uuid4())

    def _load_sessions_metadata(self) -> list[dict]:
        if not self._sessions_file.exists():
            return []
        try:
            with open(self._sessions_file, "r", encoding="utf-8", errors="replace") as f:
                sessions = json.load(f)
            sessions.sort(key=lambda s: s.get("timestamp", ""), reverse=True)
            return sessions
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
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

    def _session_user_texts(self, session_id: str, agent_type: str | None = None) -> list[str]:
        texts: list[str] = []
        for agent_type in ([agent_type] if agent_type else _AGENT_TYPES):
            jsonl_path = self._dir / agent_type / f"{session_id}.jsonl"
            if not jsonl_path.exists():
                continue
            try:
                with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if record.get("role") != "user":
                            continue
                        visible = _user_visible_content_or_empty(record.get("content", ""))
                        if visible:
                            texts.append(visible)
            except (OSError, UnicodeDecodeError):
                continue
        return texts

    def get_sessions(self, agent_type: str | None = None) -> list[dict]:
        """Return session metadata ordered newest first, excluding empty sessions.

        When *agent_type* is given, only sessions in which that specific agent
        has at least one message are returned — this is what the per-agent
        history dropdown uses so each agent only sees its own conversations.
        When *agent_type* is None (default) a session is included if ANY agent
        has messages. Name/preview are likewise derived only from the given
        agent's messages when scoped, so the list never mixes agents.
        """
        sessions = self._load_sessions_metadata()
        non_empty = []
        check_agents = [agent_type] if agent_type else _AGENT_TYPES

        for s in sessions:
            session_id = s.get("id")
            has_messages = False
            for at in check_agents:
                jsonl_path = self._dir / at / f"{session_id}.jsonl"
                if jsonl_path.exists() and jsonl_path.stat().st_size > 0:
                    has_messages = True
                    break

            if has_messages:
                item = dict(s)
                user_texts = self._session_user_texts(str(session_id), agent_type)
                visible_name = _user_visible_content_or_empty(item.get("name", ""))
                visible_preview = _user_visible_content_or_empty(item.get("preview", ""))
                if not visible_name or visible_name in ("新对话", "未命名对话", "???"):
                    visible_name = user_texts[0].splitlines()[0][:30] if user_texts else visible_name
                if not visible_preview:
                    visible_preview = user_texts[-1].splitlines()[0][:100] if user_texts else ""
                item["name"] = visible_name or "新对话"
                item["preview"] = visible_preview
                non_empty.append(item)

        return non_empty

    def get_current_session_id(self, agent_type: str = "main") -> str:
        self._ensure_session(agent_type)
        return self._current_session_ids[agent_type]

    def switch_session(self, session_id: str, agent_type: str = "main") -> bool:
        sessions = self._load_sessions_metadata()
        for s in sessions:
            if s["id"] == session_id:
                self._current_session_ids[agent_type] = session_id
                return True
        return False

    def new_session(self, name: str = "新对话", agent_type: str = "main") -> str:
        session_id = str(uuid.uuid4())
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

        # Clear the session from all agent tracking — share one new session
        new_sid = None
        for agent_type in self._current_session_ids:
            if self._current_session_ids[agent_type] == session_id:
                if sessions:
                    self._current_session_ids[agent_type] = sessions[0]["id"]
                else:
                    if new_sid is None:
                        new_sid = str(uuid.uuid4())
                    self._current_session_ids[agent_type] = new_sid
        return True

    def update_session_preview(self, agent_type: str, content: str) -> None:
        session_id = self.get_current_session_id(agent_type)
        sessions = self._load_sessions_metadata()
        for s in sessions:
            if s["id"] == session_id:
                visible_content = _user_visible_content_or_empty(content)
                preview = visible_content.split("\n")[0][:100]
                s["preview"] = preview
                self._save_sessions_metadata(sessions)
                break

    def rename_current_session_from_first_message(self, agent_type: str, content: str) -> None:
        """Auto-name the session from the first user message (max 30 chars)."""
        session_id = self.get_current_session_id(agent_type)
        sessions = self._load_sessions_metadata()
        for s in sessions:
            if s["id"] == session_id and s["name"] in ("新对话", "未命名对话"):
                name = _user_visible_content_or_empty(content).strip()[:30]
                if name:
                    s["name"] = name
                    self._save_sessions_metadata(sessions)
                break

    # ---- Write ----

    def append_message(
        self, agent_type: str, role: str, content: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._ensure_session(agent_type)
        session_id = self._current_session_ids[agent_type]
        path = self._dir / agent_type / f"{session_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save session metadata on first write when this session id is new.
        is_new = not path.exists()
        if is_new:
            sessions = self._load_sessions_metadata()
            if not any(s.get("id") == session_id for s in sessions):
                timestamp = datetime.now().isoformat(timespec="seconds")
                sessions.insert(0, {"id": session_id, "name": "新对话", "timestamp": timestamp, "preview": ""})
                self._save_sessions_metadata(sessions)

        record: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "role": role,
            "content": content,
        }
        if role == "user":
            parsed = parse_editor_context(content)
            if parsed.get("has_context"):
                record["content"] = str(parsed.get("bubble_text") or "")
                context = parsed.get("context")
                if isinstance(context, dict):
                    record["editor_context"] = context
        if extra:
            record.update(extra)

        # Auto-name only from the main panel's first direct user message.
        if role == "user" and agent_type == "main":
            self.rename_current_session_from_first_message(agent_type, content)
            self.update_session_preview(agent_type, content)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to append conversation: {}", e)

    def append_tool_call(
        self,
        agent_type: str,
        tool_name: str,
        arguments: dict,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"arguments": arguments}
        if extra:
            payload.update(extra)
        self.append_message(agent_type, "tool_call", tool_name, payload)

    def append_tool_result(
        self, agent_type: str, tool_name: str,
        result: str | None = None, error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"tool": tool_name}
        if error:
            payload["error"] = error
        elif result:
            payload["result"] = result[:2000]
        if extra:
            payload.update(extra)
        self.append_message(agent_type, "tool_result", tool_name, payload)

    # ---- Read ----

    def load_messages(self, agent_type: str, limit: int = 500) -> list[dict[str, Any]]:
        path = self._get_session_file_path(agent_type)
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except (OSError, UnicodeDecodeError) as e:
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
