"""Per-project conversation persistence using JSONL.

Stores agent conversations under ``workspace/.autoreport/conversations/``
with one JSONL file per agent type. Each line is a JSON object representing
a single message or event, enabling append-only writes and easy replay.

Inspired by Codex's rollout JSONL and nanobot's session manager.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class ConversationStore:
    """Manage conversation persistence for a project workspace.

    Layout::

        workspace/.autoreport/
        └── conversations/
            ├── main.jsonl
            ├── data_analysis.jsonl
            ├── plotting.jsonl
            ├── theory.jsonl
            └── report.jsonl
    """

    def __init__(self, workspace: Path):
        self._dir = Path(workspace).resolve() / ".autoreport" / "conversations"
        self._dir.mkdir(parents=True, exist_ok=True)

    # ---- Write ----

    def append_message(
        self,
        agent_type: str,
        role: str,
        content: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Append a message to an agent's conversation file.

        Args:
            agent_type: Agent identifier (main, data_analysis, etc.).
            role: Message role (user, agent, tool_call, tool_result, error).
            content: Message content.
            extra: Optional extra fields.
        """
        record: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "role": role,
            "content": content,
        }
        if extra:
            record.update(extra)

        path = self._dir / f"{agent_type}.jsonl"
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
    ) -> None:
        """Append a tool call record."""
        self.append_message(
            agent_type,
            "tool_call",
            tool_name,
            {"arguments": arguments},
        )

    def append_tool_result(
        self,
        agent_type: str,
        tool_name: str,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        """Append a tool result record."""
        extra: dict[str, Any] = {"tool": tool_name}
        if error:
            extra["error"] = error
        elif result:
            extra["result"] = result[:2000]  # Truncate large results
        self.append_message(agent_type, "tool_result", tool_name, extra)

    # ---- Read ----

    def load_messages(
        self,
        agent_type: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Load conversation history for an agent.

        Args:
            agent_type: Agent identifier.
            limit: Maximum number of records to return (most recent).

        Returns:
            List of message dicts, oldest first.
        """
        path = self._dir / f"{agent_type}.jsonl"
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

        # Return most recent records
        if len(records) > limit:
            records = records[-limit:]
        return records

    def get_last_user_message(self, agent_type: str) -> str | None:
        """Get the last user message for an agent (for preview)."""
        records = self.load_messages(agent_type, limit=20)
        for rec in reversed(records):
            if rec.get("role") == "user":
                return rec.get("content")
        return None

    # ---- Lifecycle ----

    def clear(self, agent_type: str) -> None:
        """Clear conversation history for an agent."""
        path = self._dir / f"{agent_type}.jsonl"
        if path.exists():
            path.unlink()
            logger.debug("Cleared conversation for {}", agent_type)

    def get_agent_types_with_history(self) -> list[str]:
        """List agent types that have conversation files."""
        if not self._dir.exists():
            return []
        return [
            p.stem
            for p in self._dir.glob("*.jsonl")
            if p.stem != ""
        ]
