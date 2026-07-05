"""Per-agent checkpoint management using diff-based storage.

Each of the 5 agents maintains its own checkpoint timeline under
.checkpoints/{agent_type}/.  A checkpoint is created before every message
is processed so the workspace can always be rolled back.

Storage design (similar to Git's delta approach):
- First checkpoint stores full file contents (baseline)
- Subsequent checkpoints only store diffs (unified diff format) relative
  to the immediate previous checkpoint
- Rollback applies diffs in sequence: forward or reverse to reach target
"""

import asyncio
import difflib
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger


# ==== Diff-based file state representation ====


@dataclass
class FileDiff:
    """Represents a single file's change between two checkpoints."""

    path: str           # relative posix path from workspace root
    operation: str      # "added" | "modified" | "deleted"
    sha256_before: str  # SHA256 before the change (empty for "added")
    sha256_after: str   # SHA256 after the change (empty for "deleted")
    unified_diff: str | None = None  # unified diff text (None for add/delete)


@dataclass
class CheckpointData:
    """A single checkpoint in an agent's timeline.

    The first checkpoint (epoch=1) stores full baseline content via
    ``file_states``.  Subsequent checkpoints store only ``file_diffs``
    against the previous checkpoint.
    """

    id: str
    agent_type: str
    timestamp: str          # ISO 8601
    epoch: int
    description: str
    source: str             # "pre_message" | "manual" | "rollback"
    message_id: str | None = None  # The message that triggered this checkpoint

    # Full file states — only populated for the baseline checkpoint (epoch=1)
    file_states: dict[str, "FileState"] = field(default_factory=dict)

    # Diffs — populated for all checkpoints (baseline has empty diffs)
    file_diffs: dict[str, FileDiff] = field(default_factory=dict)

    # Previous checkpoint ID for diff chain
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
            "file_states": {
                path: state.to_dict()
                for path, state in self.file_states.items()
            },
            "file_diffs": {
                path: asdict(d)
                for path, d in self.file_diffs.items()
            },
            "parent_id": self.parent_id,
            "conversation_history": self.conversation_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointData":
        file_states = {
            path: FileState.from_dict(state)
            for path, state in data.get("file_states", {}).items()
            if isinstance(state, dict)
        }

        file_diffs = {
            path: FileDiff(**d)
            for path, d in data.get("file_diffs", {}).items()
            if isinstance(d, dict)
        }

        return cls(
            id=data["id"],
            agent_type=data.get("agent_type", "main"),
            timestamp=data["timestamp"],
            epoch=data.get("epoch", 0),
            description=data["description"],
            source=data.get("source", "manual"),
            message_id=data.get("message_id"),
            file_states=file_states,
            file_diffs=file_diffs,
            parent_id=data.get("parent_id"),
            conversation_history=data.get("conversation_history", []),
        )


@dataclass
class FileState:
    """Full state of a single file (used for baseline checkpoint only)."""

    path: str
    hash: str
    size: int
    mtime: float
    is_binary: bool = False
    content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileState":
        return cls(**data)


# ==== Agent write directories ====

_AGENT_WRITE_DIRS: dict[str, list[str]] = {
    "main": ["Data", "Data/Processed", "References", "Theory", "Code", "Tex"],
    "data_analysis": ["Data/Processed"],
    "plotting": ["Code"],
    "theory": ["Theory"],
    "report": ["Tex"],
}


# ==== Checkpoint Manager ====


class CheckpointManager:
    """Per-agent checkpoint manager with diff-based storage.

    :class:`CheckpointManager` stores each agent's checkpoints under
    ``.checkpoints/{agent_type}/`` as individual JSON files.  The first
    checkpoint for each agent is a full baseline; subsequent checkpoints
    store only the unified diff of changed files.
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
        message_id: str | None = None,
    ) -> str:
        """Create a checkpoint for *agent_type*.

        If this is the first checkpoint for the agent, captures full file
        states.  Otherwise, computes and stores only the diffs against the
        previous checkpoint.

        Args:
            agent_type: Agent type string.
            description: Human-readable description.
            source: Source of checkpoint creation.
            conversation_history: Conversation history snapshot.
            message_id: The message that triggered this checkpoint (if any).

        Returns the checkpoint ID.
        """
        epoch = self._next_epoch(agent_type)
        checkpoint_id = _make_checkpoint_id(agent_type, epoch)
        timestamp = datetime.now(timezone.utc).isoformat()

        dirs = _AGENT_WRITE_DIRS.get(agent_type, [])
        prev_cp = self.get_latest(agent_type)

        cp = CheckpointData(
            id=checkpoint_id,
            agent_type=agent_type,
            timestamp=timestamp,
            epoch=epoch,
            description=description or f"Checkpoint {agent_type}#{epoch}",
            source=source,
            message_id=message_id,
            conversation_history=conversation_history or [],
        )

        if prev_cp is None:
            # First checkpoint: store full file states
            file_states = await self._capture_file_states(dirs)
            cp.file_states = file_states
            cp.file_diffs = {}
            cp.parent_id = None
        else:
            # Subsequent checkpoint: compute diffs against previous
            current_states = await self._capture_file_states(dirs)
            cp.file_diffs = await self._compute_diffs(prev_cp, current_states)
            cp.file_states = {}
            cp.parent_id = prev_cp.id

        await self._save(cp)

        bucket = self._checkpoints.setdefault(agent_type, {})
        bucket[checkpoint_id] = cp

        if prev_cp is None:
            logger.info(
                "{} baseline checkpoint {} — {} files captured",
                agent_type, checkpoint_id, len(cp.file_states),
            )
        else:
            logger.info(
                "{} checkpoint {} — {} files changed",
                agent_type, checkpoint_id, len(cp.file_diffs),
            )
        return checkpoint_id

    async def rollback(self, agent_type: str, checkpoint_id: str) -> int:
        """Rollback *agent_type* to a specific checkpoint.

        Restores file content by walking the diff chain:
        - Finds the closest full baseline
        - Applies diffs forward/backward to reach the target checkpoint

        Returns the number of files restored.
        """
        bucket = self._checkpoints.get(agent_type, {})
        target = bucket.get(checkpoint_id)
        if target is None:
            raise ValueError(
                f"Checkpoint not found: {checkpoint_id} for agent {agent_type}"
            )

        # Walk the chain to assemble full file content at target
        restored_content = await self._assemble_state(agent_type, target)

        # Write restored files to disk
        count = 0
        for rel, content in restored_content.items():
            fp = self.workspace / rel
            if content is not None:
                fp.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(fp.write_text, content, encoding="utf-8")
                count += 1
            elif fp.exists():
                # File was deleted at this checkpoint
                fp.unlink(missing_ok=True)
                count += 1

        logger.info("Rolled back {} to {} — {} files restored", agent_type, checkpoint_id, count)
        return count

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

        The baseline checkpoint (parent_id is None) is never deleted so the
        diff chain always remains reconstructable.

        Returns the number of checkpoints removed.
        """
        bucket = self._checkpoints.get(agent_type, {})
        if len(bucket) <= keep:
            return 0

        sorted_cps = sorted(bucket.values(), key=lambda c: c.epoch, reverse=True)
        removed = 0
        for cp in sorted_cps[keep:]:
            # Never delete the baseline (parent_id is None)
            if cp.parent_id is None:
                continue
            self._delete_one(cp)
            removed += 1

        logger.info("Cleared {} old checkpoints for {}, kept {}", removed, agent_type, keep)
        return removed

    # ------------------------------------------------------------------
    # Internal: Load / Save
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
    # Internal: File state capture
    # ------------------------------------------------------------------

    async def _capture_file_states(self, dirs: list[str]) -> dict[str, "FileState"]:
        """Capture full file states for the given workspace-relative directories."""
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

    # ------------------------------------------------------------------
    # Internal: Diff computation and state assembly
    # ------------------------------------------------------------------

    async def _compute_diffs(
        self,
        prev_cp: CheckpointData,
        current_states: dict[str, "FileState"],
    ) -> dict[str, FileDiff]:
        """Compute diffs between the previous checkpoint and current file states.

        We reconstruct the full file content at *prev_cp* by assembling
        its baseline + diffs, then diff against *current_states*.
        """
        # Reconstruct previous state's file content
        prev_content = await self._assemble_state(
            prev_cp.agent_type, prev_cp
        )

        diffs: dict[str, FileDiff] = {}
        prev_paths = set(prev_content.keys())
        curr_paths = set(current_states.keys())

        # Deleted files — compute SHA256 of content being deleted
        for path in prev_paths - curr_paths:
            old_text = prev_content.get(path, "")
            diffs[path] = FileDiff(
                path=path,
                operation="deleted",
                sha256_before=await _sha256_of_string(old_text),
                sha256_after="",
                unified_diff=None,
            )

        # Added files — generate diff against empty string for rollback
        for path in curr_paths - prev_paths:
            state = current_states[path]
            curr_text = state.content or ""
            # Generate unified diff from empty to current content
            udiff = "\n".join(difflib.unified_diff(
                [],  # empty file
                curr_text.splitlines(),
                fromfile="/dev/null",
                tofile=path,
                lineterm="",
            ))
            diffs[path] = FileDiff(
                path=path,
                operation="added",
                sha256_before="",
                sha256_after=state.hash,
                unified_diff=udiff,
            )

        # Modified files
        for path in prev_paths & curr_paths:
            state = current_states[path]
            prev_text = prev_content.get(path, "")
            if prev_text is None:
                prev_text = ""
            curr_text = state.content or ""
            if prev_text != curr_text:
                udiff = "\n".join(difflib.unified_diff(
                    prev_text.splitlines(),
                    curr_text.splitlines(),
                    fromfile=path,
                    tofile=path,
                    lineterm="",
                ))
                diffs[path] = FileDiff(
                    path=path,
                    operation="modified",
                    sha256_before=await _sha256_of_string(prev_text),
                    sha256_after=state.hash,
                    unified_diff=udiff,
                )

        return diffs

    async def _assemble_state(
        self,
        agent_type: str,
        target: CheckpointData,
    ) -> dict[str, str]:
        """Reconstruct full file content at a given checkpoint.

        Walks back to find the closest full baseline, then applies diffs
        forward to reach *target*.
        """
        bucket = self._checkpoints.get(agent_type, {})
        chain: list[CheckpointData] = []

        # Walk back to baseline — identified by parent_id being None,
        # NOT by file_states being non-empty (empty write dirs are valid).
        cp = target
        while cp is not None and cp.parent_id is not None:
            chain.append(cp)
            cp = bucket.get(cp.parent_id) if cp.parent_id else None

        if cp is None:
            raise ValueError(
                f"Cannot find baseline checkpoint for {target.id}"
            )

        baseline = cp

        # Start with baseline content
        result: dict[str, str] = {}
        for path, state in baseline.file_states.items():
            if state.content is not None:
                result[path] = state.content

        # Apply diffs forward
        for cp_node in reversed(chain):
            for path, diff in cp_node.file_diffs.items():
                if diff.operation == "added":
                    # Apply diff to empty string to get new file content
                    result[path] = _apply_unified_diff("", diff.unified_diff)
                elif diff.operation == "modified":
                    old_content = result.get(path, "")
                    result[path] = _apply_unified_diff(old_content, diff.unified_diff) if diff.unified_diff else old_content
                elif diff.operation == "deleted":
                    result.pop(path, None)

        return result


# ==== Helpers ====


async def _sha256(fp: Path) -> str:
    import aiofiles

    h = hashlib.sha256()
    async with aiofiles.open(fp, "rb") as fh:
        while chunk := await fh.read(8192):
            h.update(chunk)
    return h.hexdigest()


async def _sha256_of_string(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _is_binary(fp: Path) -> bool:
    try:
        with open(fp, "rb") as fh:
            return b"\x00" in fh.read(1024)
    except Exception:
        return True


def _make_checkpoint_id(agent_type: str, epoch: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"cp_{agent_type}_{epoch:04d}_{ts}"


def _apply_unified_diff(original: str, diff_text: str | None) -> str:
    """Apply a unified diff to *original* and return the result.

    If *diff_text* is None or empty, returns *original* unchanged.
    """
    if not diff_text:
        return original

    result_lines = list(original.splitlines(keepends=True))
    # Keep trailing newline if original had one
    has_trailing_newline = original.endswith("\n") if original else False

    diff_lines = diff_text.splitlines(keepends=True)
    # Parse unified diff and apply

    i = 0
    while i < len(diff_lines):
        line = diff_lines[i]
        # Parse hunk header: @@ -start,count +start,count @@
        if line.startswith("@@"):
            header = line
            parts = header.split()
            # Find the second @@
            if len(parts) >= 2:
                from_range = parts[1]  # e.g. -1,3
                to_range = parts[2] if len(parts) > 2 else "+0,0"

                # Parse from_range
                from_parts = from_range[1:].split(",")  # remove leading '-'
                from_start = int(from_parts[0])
                from_count = int(from_parts[1]) if len(from_parts) > 1 else 0

                # Read hunk body
                hunk_add: list[str] = []
                i += 1
                while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                    dl = diff_lines[i]
                    if dl.startswith("---") or dl.startswith("+++"):
                        i += 1
                        continue
                    if dl.startswith("-"):
                        pass  # removal line — strip handled by range below
                    elif dl.startswith("+"):
                        hunk_add.append(dl[1:])  # strip leading '+'
                    else:
                        # Context line - strip leading space before appending
                        hunk_add.append(dl[1:] if len(dl) > 0 else dl)
                    i += 1

                # Apply patch: remove from_start..from_start+from_count,
                # insert hunk_add at from_start-1 (0-indexed)
                start_idx = from_start - 1 if from_start > 0 else 0
                end_idx = start_idx + from_count
                # Ensure indices are within bounds
                start_idx = max(0, min(start_idx, len(result_lines)))
                end_idx = max(start_idx, min(end_idx, len(result_lines)))
                result_lines[start_idx:end_idx] = hunk_add
                continue
        i += 1

    result = "".join(result_lines)
    if has_trailing_newline and not result.endswith("\n"):
        result += "\n"
    return result