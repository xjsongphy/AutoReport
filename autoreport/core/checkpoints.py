"""Checkpoint management for rollback functionality."""

import asyncio
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from dataclasses import dataclass, asdict

from loguru import logger

from ...interfaces.types import Checkpoint, Message


@dataclass
class FileState:
    """State of a file at a checkpoint."""

    path: str
    hash: str
    size: int
    mtime: float
    is_binary: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileState":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class CheckpointData:
    """Checkpoint data."""

    id: str
    timestamp: str
    description: str
    file_states: dict[str, FileState]
    source: str  # "main_agent", "user_confirmation"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "description": self.description,
            "source": self.source,
            "file_states": {
                path: state.to_dict()
                for path, state in self.file_states.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointData":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            description=data["description"],
            source=data["source"],
            file_states={
                path: FileState.from_dict(state)
                for path, state in data["file_states"].items()
            },
        )


class CheckpointManager:
    """Manager for checkpoints and rollback."""

    def __init__(self, workspace: Path):
        """Initialize checkpoint manager.

        Args:
            workspace: Project workspace directory.
        """
        self.workspace = Path(workspace).resolve()
        self.checkpoints_dir = self.workspace / ".checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        self._checkpoints: dict[str, CheckpointData] = {}
        self._current_checkpoint: str | None = None

        # Load existing checkpoints
        self._load_checkpoints()

    def _load_checkpoints(self) -> None:
        """Load existing checkpoints from disk."""
        if not self.checkpoints_dir.exists():
            return

        for checkpoint_file in self.checkpoints_dir.glob("*.json"):
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    checkpoint = CheckpointData.from_dict(data)
                    self._checkpoints[checkpoint.id] = checkpoint
                    logger.debug("Loaded checkpoint: {}", checkpoint.id)
            except Exception as e:
                logger.warning("Failed to load checkpoint {}: {}", checkpoint_file, e)

        logger.info("Loaded {} checkpoints", len(self._checkpoints))

    async def create_checkpoint(
        self,
        description: str,
        source: str = "main_agent",
    ) -> str:
        """Create a checkpoint of current file states.

        Args:
            description: Description of the checkpoint.
            source: Source of the checkpoint (e.g., "main_agent", "user").

        Returns:
            Checkpoint ID.
        """
        checkpoint_id = self._generate_checkpoint_id()
        timestamp = datetime.now().isoformat()

        # Capture file states
        file_states = await self._capture_file_states()

        # Create checkpoint data
        checkpoint = CheckpointData(
            id=checkpoint_id,
            timestamp=timestamp,
            description=description,
            source=source,
            file_states=file_states,
        )

        # Save checkpoint
        await self._save_checkpoint(checkpoint)

        self._checkpoints[checkpoint_id] = checkpoint
        self._current_checkpoint = checkpoint_id

        logger.info(
            "Created checkpoint {}: {} ({} files)",
            checkpoint_id,
            description,
            len(file_states),
        )

        return checkpoint_id

    async def rollback_to_checkpoint(self, checkpoint_id: str) -> None:
        """Rollback to a specific checkpoint.

        Args:
            checkpoint_id: Checkpoint ID to rollback to.

        Raises:
            ValueError: If checkpoint not found.
        """
        if checkpoint_id not in self._checkpoints:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        checkpoint = self._checkpoints[checkpoint_id]

        logger.info(
            "Rolling back to checkpoint {}: {}",
            checkpoint_id,
            checkpoint.description,
        )

        # Restore files
        await self._restore_files(checkpoint)

        logger.info("Rollback complete")

    async def _capture_file_states(self) -> dict[str, FileState]:
        """Capture current file states.

        Returns:
            Dictionary mapping file paths to FileState objects.
        """
        file_states = {}

        # Track all relevant directories
        tracked_dirs = [
            self.workspace / "data",
            self.workspace / "data" / "processed",
            self.workspace / "references",
            self.workspace / "theory",
            self.workspace / "code",
            self.workspace / "tex",
        ]

        for dir_path in tracked_dirs:
            if not dir_path.exists():
                continue

            # Capture all files in directory
            for file_path in dir_path.rglob("*"):
                if not file_path.is_file():
                    continue

                # Skip checkpoints directory
                if ".checkpoints" in str(file_path):
                    continue

                # Calculate file hash
                file_hash = await self._calculate_file_hash(file_path)

                # Get file stats
                stat = file_path.stat()
                relative_path = file_path.relative_to(self.workspace)

                file_states[str(relative_path)] = FileState(
                    path=str(relative_path),
                    hash=file_hash,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    is_binary=await self._is_binary_file(file_path),
                )

        return file_states

    async def _save_checkpoint(self, checkpoint: CheckpointData) -> None:
        """Save checkpoint to disk.

        Args:
            checkpoint: Checkpoint data to save.
        """
        checkpoint_file = self.checkpoints_dir / f"{checkpoint.id}.json"

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, indent=2, ensure_ascii=False)

    async def _restore_files(self, checkpoint: CheckpointData) -> None:
        """Restore files to checkpoint state.

        Args:
            checkpoint: Checkpoint to restore.
        """
        # Note: This is a simplified implementation
        # A full implementation would need:
        # 1. Backup current state before restoring
        # 2. Handle files that didn't exist at checkpoint
        # 3. Handle files that exist now but didn't at checkpoint
        # 4. Handle file content restoration (would need to store actual content or use git)

        logger.warning(
            "File restoration not fully implemented. "
            "Checkpoint data saved but files not restored."
        )

        # For now, just verify that checkpoint files exist
        missing_files = []
        for relative_path, state in checkpoint.file_states.items():
            file_path = self.workspace / relative_path
            if not file_path.exists():
                missing_files.append(relative_path)
            else:
                # Verify hash
                current_hash = await self._calculate_file_hash(file_path)
                if current_hash != state.hash:
                    logger.debug(
                        "File modified since checkpoint: {} (expected {}, got {})",
                        relative_path,
                        state.hash,
                        current_hash,
                    )

        if missing_files:
            logger.warning("Missing files at checkpoint: {}", missing_files)

    async def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file.

        Args:
            file_path: Path to file.

        Returns:
            Hex string of hash.
        """
        import aiofiles

        sha256 = hashlib.sha256()

        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(8192):
                sha256.update(chunk)

        return sha256.hexdigest()

    async def _is_binary_file(self, file_path: Path) -> bool:
        """Check if a file is binary.

        Args:
            file_path: Path to file.

        Returns:
            True if file is binary.
        """
        # Simple check: read first 1024 bytes and look for null bytes
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                return b"\x00" in chunk
        except Exception:
            return True

    def _generate_checkpoint_id(self) -> str:
        """Generate a unique checkpoint ID.

        Returns:
            Checkpoint ID string.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        counter = len(self._checkpoints) + 1
        return f"cp_{timestamp}_{counter:04d}"

    def get_checkpoints(self) -> list[CheckpointData]:
        """Get all checkpoints.

        Returns:
            List of checkpoint data.
        """
        return list(self._checkpoints.values())

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointData | None:
        """Get a specific checkpoint.

        Args:
            checkpoint_id: Checkpoint ID.

        Returns:
            Checkpoint data or None if not found.
        """
        return self._checkpoints.get(checkpoint_id)

    def clear_old_checkpoints(self, keep: int = 10) -> None:
        """Clear old checkpoints, keeping only the most recent ones.

        Args:
            keep: Number of checkpoints to keep.
        """
        if len(self._checkpoints) <= keep:
            return

        # Sort checkpoints by timestamp
        sorted_checkpoints = sorted(
            self._checkpoints.values(),
            key=lambda cp: cp.timestamp,
            reverse=True,
        )

        # Remove oldest checkpoints
        to_remove = sorted_checkpoints[keep:]

        for checkpoint in to_remove:
            self._delete_checkpoint(checkpoint.id)

        logger.info("Cleared old checkpoints, kept {} most recent", keep)

    def _delete_checkpoint(self, checkpoint_id: str) -> None:
        """Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID to delete.
        """
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]

        checkpoint_file = self.checkpoints_dir / f"{checkpoint_id}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

        logger.debug("Deleted checkpoint: {}", checkpoint_id)
