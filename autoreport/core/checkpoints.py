"""Per-agent checkpoint management for independent rollback.

Each of the 5 agents maintains its own checkpoint timeline under
.checkpoints/{agent_type}/.  A checkpoint is created before every message
is processed so the agent can always undo to the pre-message state.

Design follows VS Code Copilot Chat:
- Sentinel checkpoints mark request boundaries (pre-message state)
- Each checkpoint stores file states only for the agent's write directory
- Checkpoint IDs include agent_type to prevent cross-agent mixing
"""

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class FileState:
    """State of a single file at a checkpoint."""

    path: str           # relative posix path from workspace root
    hash: str           # SHA256 hex digest
    size: int           # bytes
    mtime: float        # file modification time
    is_binary: bool = False
    content: str | None = None  # text content snapshot (None for binary)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileState":
        return cls(**data)


@dataclass
class CheckpointData:
    """A single checkpoint in an agent's timeline."""

    id: str                 # unique checkpoint ID
    agent_type: str         # which agent owns this checkpoint
    timestamp: str          # ISO 8601 timestamp
    epoch: int              # monotonically increasing counter per agent
    description: str        # human-readable label
    source: str             # "pre_message" | "manual" | "rollback"
    file_states: dict[str, FileState] = field(default_factory=dict)
    conversation_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "timestamp": self.timestamp,
            "epoch": self.epoch,
            "description": self.description,
            "source": self.source,
            "file_states": {
                path: state.to_dict()
                for path, state in self.file_states.items()
            },
            "conversation_history": self.conversation_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointData":
        return cls(
            id=data["id"],
            agent_type=data.get("agent_type", "main"),
            timestamp=data["timestamp"],
            epoch=data.get("epoch", 0),
            description=data["description"],
            source=data.get("source", "manual"),
            file_states={
                path: FileState.from_dict(state)
                for path, state in data.get("file_states", {}).items()
            },
            conversation_history=data.get("conversation_history", []),
        )


# Write directories per agent type (relative to workspace root)
_AGENT_WRITE_DIRS: dict[str, list[str]] = {
    "main": ["data", "data/processed", "references", "theory", "code", "tex"],
    "data_analysis": ["data/processed"],
    "plotting": ["code"],
    "theory": ["theory"],
    "report": ["tex"],
}


class CheckpointManager:
    """Per-agent checkpoint manager.

    Checkpoints are stored in .checkpoints/{agent_type}/ as individual JSON
    files.  Each agent has its own epoch counter and only captures files
    within its write directory.
    """

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self._base_dir = self.workspace / ".checkpoints"
        self._base_dir.mkdir(parents=True, exist_ok=True)

        # Per-agent in-memory state
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
    ) -> str:
        """Create a checkpoint for *agent_type* capturing current file states.

        Returns the checkpoint ID.
        """
        epoch = self._next_epoch(agent_type)
        checkpoint_id = _make_checkpoint_id(agent_type, epoch)
        timestamp = datetime.now(timezone.utc).isoformat()

        dirs = _AGENT_WRITE_DIRS.get(agent_type, [])
        file_states = await self._capture_file_states(dirs)

        cp = CheckpointData(
            id=checkpoint_id,
            agent_type=agent_type,
            timestamp=timestamp,
            epoch=epoch,
            description=description or f"Checkpoint {agent_type}#{epoch}",
            source=source,
            file_states=file_states,
            conversation_history=conversation_history or [],
        )

        await self._save(cp)

        bucket = self._checkpoints.setdefault(agent_type, {})
        bucket[checkpoint_id] = cp

        logger.info(
            "{} checkpoint {} — {} files captured",
            agent_type, checkpoint_id, len(file_states),
        )
        return checkpoint_id

    async def rollback(self, agent_type: str, checkpoint_id: str) -> int:
        """Rollback *agent_type* to a specific checkpoint by restoring file content.

        Returns the number of files restored.
        """
        bucket = self._checkpoints.get(agent_type, {})
        cp = bucket.get(checkpoint_id)
        if cp is None:
            raise ValueError(
                f"Checkpoint not found: {checkpoint_id} for agent {agent_type}"
            )

        logger.info("Rolling back {} to checkpoint {}", agent_type, checkpoint_id)
        restored = await self._restore_files(cp)
        logger.info("Rollback complete — {} files restored", restored)
        return restored

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
    # Internal
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        """Load all existing checkpoints from disk."""
        if not self._base_dir.exists():
            return

        for agent_dir in self._base_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            agent_type = agent_dir.name
            for f in agent_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    cp = CheckpointData.from_dict(data)
                    self._checkpoints.setdefault(agent_type, {})[cp.id] = cp
                except Exception:
                    logger.warning("Failed to load checkpoint {}", f)

            # Restore highest epoch
            bucket = self._checkpoints.get(agent_type, {})
            if bucket:
                self._epochs[agent_type] = max(c.epoch for c in bucket.values())
                logger.info(
                    "Loaded {} checkpoints for {} (epoch={})",
                    len(bucket), agent_type, self._epochs[agent_type],
                )

    async def _capture_file_states(self, dirs: list[str]) -> dict[str, FileState]:
        """Capture file states for the given workspace-relative directories."""
        states: dict[str, FileState] = {}

        for rel_dir in dirs:
            d = self.workspace / rel_dir
            if not d.exists():
                continue
            for fp in d.rglob("*"):
                if not fp.is_file():
                    continue
                if ".checkpoints" in fp.parts:
                    continue

                try:
                    h = await _sha256(fp)
                    st = fp.stat()
                    rel = fp.relative_to(self.workspace).as_posix()
                    is_bin = await _is_binary(fp)
                    content = None
                    if not is_bin and st.st_size < 1_000_000:
                        try:
                            content = await asyncio.to_thread(
                                fp.read_text, encoding="utf-8"
                            )
                        except (UnicodeDecodeError, OSError):
                            content = None
                    states[rel] = FileState(
                        path=rel, hash=h, size=st.st_size,
                        mtime=st.st_mtime, is_binary=is_bin, content=content,
                    )
                except OSError:
                    pass

        return states

    async def _restore_files(self, checkpoint: CheckpointData) -> int:
        """Restore files from checkpoint content snapshots."""
        count = 0
        for rel, state in checkpoint.file_states.items():
            fp = self.workspace / rel
            if state.content is not None:
                fp.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(fp.write_text, state.content, encoding="utf-8")
                count += 1
            elif not fp.exists():
                logger.warning("Cannot restore binary file without snapshot: {}", rel)
        return count

    async def _save(self, cp: CheckpointData) -> None:
        agent_dir = self._base_dir / cp.agent_type
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / f"{cp.id}.json").write_text(
            json.dumps(cp.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _delete_one(self, cp: CheckpointData) -> None:
        bucket = self._checkpoints.get(cp.agent_type, {})
        bucket.pop(cp.id, None)
        f = self._base_dir / cp.agent_type / f"{cp.id}.json"
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass

    def _next_epoch(self, agent_type: str) -> int:
        epoch = self._epochs.get(agent_type, 0) + 1
        self._epochs[agent_type] = epoch
        return epoch


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _sha256(fp: Path) -> str:
    import aiofiles

    h = hashlib.sha256()
    async with aiofiles.open(fp, "rb") as fh:
        while chunk := await fh.read(8192):
            h.update(chunk)
    return h.hexdigest()


async def _is_binary(fp: Path) -> bool:
    try:
        with open(fp, "rb") as fh:
            return b"\x00" in fh.read(1024)
    except Exception:
        return True


def _make_checkpoint_id(agent_type: str, epoch: int) -> str:
    """Generate a unique checkpoint ID.

    Format: cp_{agent_type}_{epoch:04d}_{timestamp}
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"cp_{agent_type}_{epoch:04d}_{ts}"
