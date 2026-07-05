"""Per-agent checkpoint management using an operation log (codex-style).

Each of the 5 agents maintains its own checkpoint timeline under
``.checkpoints/{agent_type}/``. A checkpoint is created before every message
is processed; the file mutations performed by tools during that message
(``apply_patch`` / ``delete_file``) are recorded into the checkpoint as
structured, reversible :class:`FileOperation` records. Rollback replays the
inverse of those operations.

Why an operation log (instead of full snapshots + diff chains):

- File changes are captured **at the moment a tool makes them**, so the record
  is exact and self-contained — no diff generation, no reconstruction, no
  accumulation of round-trip errors.
- ``apply_patch`` is text-only, so binary files (PDFs, images, generated
  plots) are never tracked → rollback never destroys them.
- Only changed files are stored; rollback only touches files the agent
  actually edited. Files mutated out-of-band (shell ``rm``, Python scripts,
  external edits) are intentionally not recorded and are left untouched by
  rollback.

Legacy checkpoints (the old ``file_states`` / ``file_diffs`` format) are
detected on load and skipped — start fresh.
"""

import asyncio
import base64
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# ==== Operation-based file change record ====


@dataclass
class FileOperation:
    """One reversible file mutation performed by a tool.

    - ``add``:    file did not exist before; ``after`` is the new content.
    - ``modify``: file existed; ``before`` → ``after`` (text content).
    - ``delete``: file removed; ``before`` holds the prior content.

    All content is UTF-8 text (apply_patch is text-only). For a ``delete`` of a
    binary file, ``before_binary_b64`` carries the base64-encoded bytes and
    ``before`` stays None.
    """

    path: str
    kind: str  # "add" | "modify" | "delete"
    before: str | None = None
    after: str | None = None
    before_binary_b64: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileOperation":
        return cls(
            path=data["path"],
            kind=data["kind"],
            before=data.get("before"),
            after=data.get("after"),
            before_binary_b64=data.get("before_binary_b64"),
        )


@dataclass
class CheckpointData:
    """A single checkpoint in an agent's timeline.

    Stores the list of file operations performed by tools during the bubble
    this checkpoint represents. The chain is fully reversible from the
    operations alone — no baseline snapshot is required.
    """

    id: str
    agent_type: str
    timestamp: str
    epoch: int
    description: str
    source: str  # "pre_message" | "manual" | "rollback"
    message_id: str | None = None
    operations: list[FileOperation] = field(default_factory=list)
    parent_id: str | None = None
    conversation_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "timestamp": self.timestamp,
            "epoch": self.epoch,
            "description": self.description,
            "source": self.source,
            "message_id": self.message_id,
            "operations": [op.to_dict() for op in self.operations],
            "parent_id": self.parent_id,
            "conversation_history": self.conversation_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointData":
        operations = [
            FileOperation.from_dict(op)
            for op in data.get("operations", [])
            if isinstance(op, dict)
        ]
        return cls(
            id=data["id"],
            agent_type=data.get("agent_type", "main"),
            timestamp=data["timestamp"],
            epoch=data.get("epoch", 0),
            description=data.get("description", ""),
            source=data.get("source", "manual"),
            message_id=data.get("message_id"),
            operations=operations,
            parent_id=data.get("parent_id"),
            conversation_history=data.get("conversation_history", []),
        )


# ==== Checkpoint Manager ====


class CheckpointManager:
    """Per-agent, operation-log-based checkpoint manager.

    Checkpoints are stored under ``.checkpoints/{agent_type}/`` as individual
    JSON files. ``create_checkpoint`` makes an empty container for the current
    bubble; tools call :meth:`record_operations` to append each file mutation;
    :meth:`rollback` replays the inverse of recorded operations.
    """

    # Operations are only recorded for text mutations through our tools.
    # Legacy format detection: any checkpoint JSON lacking an "operations" key.
    _FORMAT_KEY = "operations"

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self._base_dir = self.workspace / ".checkpoints"
        self._base_dir.mkdir(parents=True, exist_ok=True)

        self._checkpoints: dict[str, dict[str, CheckpointData]] = {}
        self._epochs: dict[str, int] = {}

        self._load_all()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_checkpoint(
        self,
        agent_type: str,
        description: str = "",
        source: str = "pre_message",
        conversation_history: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
    ) -> str:
        """Create an empty checkpoint container for the current bubble.

        Tools will record their file mutations into this checkpoint during the
        turn via :meth:`record_operations`.
        """
        epoch = self._next_epoch(agent_type)
        checkpoint_id = _make_checkpoint_id(agent_type, epoch)
        latest = self.get_latest(agent_type)

        cp = CheckpointData(
            id=checkpoint_id,
            agent_type=agent_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            epoch=epoch,
            description=description or f"Checkpoint {agent_type}#{epoch}",
            source=source,
            message_id=message_id,
            operations=[],
            parent_id=latest.id if latest is not None else None,
            conversation_history=conversation_history or [],
        )
        await self._save(cp)
        self._checkpoints.setdefault(agent_type, {})[checkpoint_id] = cp
        logger.info("{} checkpoint {} created", agent_type, checkpoint_id)
        return checkpoint_id

    async def record_operations(
        self, agent_type: str, operations: list[FileOperation]
    ) -> None:
        """Append tool-performed file operations to the agent's current checkpoint.

        No-op (with a warning) if no checkpoint exists for the agent yet — tools
        should only mutate files during a turn, which always has a pre-message
        checkpoint.
        """
        if not operations:
            return
        latest = self.get_latest(agent_type)
        if latest is None:
            logger.warning(
                "record_operations: no active checkpoint for {} — {} ops not recorded",
                agent_type,
                len(operations),
            )
            return
        latest.operations.extend(operations)
        await self._save(latest)

    async def rollback(self, agent_type: str, checkpoint_id: str) -> int:
        """Rollback *agent_type* to the state before the target checkpoint.

        Reverses every recorded file operation in checkpoints with
        ``epoch >= target.epoch`` (i.e. the target's own bubble and everything
        after it), in descending epoch order, operations within each checkpoint
        applied in reverse (LIFO). Files never recorded are left untouched.

        Returns the number of operations reversed.
        """
        bucket = self._checkpoints.get(agent_type, {})
        target = bucket.get(checkpoint_id)
        if target is None:
            raise ValueError(
                f"Checkpoint not found: {checkpoint_id} for agent {agent_type}"
            )

        count = 0
        for cp in sorted(bucket.values(), key=lambda c: c.epoch, reverse=True):
            if cp.epoch < target.epoch:
                break
            for op in reversed(cp.operations):
                await self._reverse_op(op)
                count += 1

        logger.info(
            "Rolled back {} to {} — {} operations reversed",
            agent_type, checkpoint_id, count,
        )
        return count

    async def _reverse_op(self, op: FileOperation) -> None:
        """Apply the inverse of a single recorded file operation."""
        fp = self.workspace / op.path
        if op.kind == "add":
            # File was created by the agent → remove to undo.
            fp.unlink(missing_ok=True)
        elif op.kind == "delete":
            # Restore the prior content (text or binary bytes).
            fp.parent.mkdir(parents=True, exist_ok=True)
            if op.before_binary_b64:
                await asyncio.to_thread(
                    fp.write_bytes, base64.b64decode(op.before_binary_b64)
                )
            elif op.before is not None:
                await asyncio.to_thread(fp.write_text, op.before, encoding="utf-8")
        elif op.kind == "modify":
            if op.before is not None:
                fp.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(fp.write_text, op.before, encoding="utf-8")

    def get_checkpoint(self, agent_type: str, checkpoint_id: str) -> CheckpointData | None:
        """Get a single checkpoint by agent_type and ID."""
        return self._checkpoints.get(agent_type, {}).get(checkpoint_id)

    def list_checkpoints(self, agent_type: str) -> list[CheckpointData]:
        """Return all checkpoints for *agent_type*, sorted by epoch ascending."""
        bucket = self._checkpoints.get(agent_type, {})
        return sorted(bucket.values(), key=lambda c: c.epoch)

    def get_latest(self, agent_type: str) -> CheckpointData | None:
        """Return the most recent checkpoint for *agent_type*."""
        bucket = self._checkpoints.get(agent_type, {})
        if not bucket:
            return None
        return max(bucket.values(), key=lambda c: c.epoch)

    def clear_old(self, agent_type: str, keep: int = 20) -> int:
        """Remove old checkpoints for *agent_type*, keeping the most recent *keep*.

        Returns the number of checkpoints removed.
        """
        bucket = self._checkpoints.get(agent_type, {})
        if len(bucket) <= keep:
            return 0
        sorted_cps = sorted(bucket.values(), key=lambda c: c.epoch, reverse=True)
        removed = 0
        for cp in sorted_cps[keep:]:
            self._delete_one(cp)
            removed += 1
        logger.info("Cleared {} old checkpoints for {}, kept {}", removed, agent_type, keep)
        return removed

    # ------------------------------------------------------------------
    # Internal: Load / Save
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        """Load all existing checkpoints from disk, skipping legacy format."""
        if not self._base_dir.exists():
            return

        for agent_dir in self._base_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            agent_type = agent_dir.name
            for f in agent_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    logger.warning("Failed to load checkpoint {}", f)
                    continue
                # Skip legacy snapshots/diffs (no "operations" key).
                if not isinstance(data, dict) or self._FORMAT_KEY not in data:
                    logger.info(
                        "Skipping legacy checkpoint {} (old snapshot/diff format) "
                        "— not compatible with operation-log rollback.",
                        f.name,
                    )
                    continue
                try:
                    cp = CheckpointData.from_dict(data)
                except Exception:
                    logger.warning("Failed to parse checkpoint {}", f)
                    continue
                self._checkpoints.setdefault(agent_type, {})[cp.id] = cp

            bucket = self._checkpoints.get(agent_type, {})
            if bucket:
                self._epochs[agent_type] = max(c.epoch for c in bucket.values())
                logger.info(
                    "Loaded {} checkpoints for {} (epoch={})",
                    len(bucket), agent_type, self._epochs[agent_type],
                )

    async def _save(self, cp: CheckpointData) -> None:
        agent_dir = self._base_dir / cp.agent_type
        agent_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(cp.to_dict(), indent=2, ensure_ascii=False)
        await asyncio.to_thread(
            (agent_dir / f"{cp.id}.json").write_text, payload, encoding="utf-8"
        )

    def _delete_one(self, cp: CheckpointData) -> None:
        bucket = self._checkpoints.get(cp.agent_type, {})
        bucket.pop(cp.id, None)
        fp = self._base_dir / cp.agent_type / f"{cp.id}.json"
        try:
            fp.unlink(missing_ok=True)
        except OSError:
            pass

    def _next_epoch(self, agent_type: str) -> int:
        epoch = self._epochs.get(agent_type, 0) + 1
        self._epochs[agent_type] = epoch
        return epoch


# ==== Helpers ====


def _make_checkpoint_id(agent_type: str, epoch: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"cp_{agent_type}_{epoch:04d}_{ts}"


def _is_binary(fp: Path) -> bool:
    """Heuristic: a file is binary if its first 1KB contains a NUL byte."""
    try:
        with open(fp, "rb") as fh:
            return b"\x00" in fh.read(1024)
    except Exception:
        return True
