"""File search manager for @ file references."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable

from loguru import logger


@dataclass
class FileMatch:
    """File search result match."""

    path: Path
    score: int
    indices: list[int] | None = None


class FuzzyMatcher:
    """Simple fuzzy string matcher."""

    @staticmethod
    def match(text: str, query: str) -> tuple[int, list[int] | None]:
        """Match query against text with fuzzy matching.

        Args:
            text: Text to search in.
            query: Query string to match.

        Returns:
            Tuple of (score, matched_indices) or ( -1, None) if no match.
        """
        if not query:
            return 0, None

        text_lower = text.lower()
        query_lower = query.lower()

        # Exact match gets highest score
        if query_lower == text_lower:
            return 1000, list(range(len(query)))

        # Start of string match
        if text_lower.startswith(query_lower):
            return 800, list(range(len(query)))

        # Contains match
        if query_lower in text_lower:
            start = text_lower.index(query_lower)
            indices = list(range(start, start + len(query)))
            return 600, indices

        # Character-by-character fuzzy match
        # Find characters in order anywhere in text
        text_idx = 0
        query_idx = 0
        indices = []
        score = 0

        while query_idx < len(query_lower) and text_idx < len(text_lower):
            if query_lower[query_idx] == text_lower[text_idx]:
                indices.append(text_idx)
                # Bonus for consecutive matches
                if indices and indices[-1] == text_idx - 1:
                    score += 2
                else:
                    score += 1
                query_idx += 1
            text_idx += 1

        if query_idx == len(query_lower):
            # All query characters found
            # Penalize gaps
            gap_penalty = sum(
                1
                for i in range(1, len(indices))
                if indices[i] - indices[i - 1] > 1
            )
            score = max(score - gap_penalty, 1)
            return score, indices

        return -1, None


class FileSearchManager:
    """Manager for file search operations.

    Orchestrates file search sessions with debouncing and async execution.
    Based on Codex's FileSearchManager pattern.
    """

    def __init__(self, workspace: Path):
        """Initialize file search manager.

        Args:
            workspace: Project workspace directory.
        """
        self.workspace = Path(workspace).resolve()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._current_task: asyncio.Task | None = None
        self._file_cache: list[Path] | None = None

    async def search(
        self, query: str, callback: Callable[[list[FileMatch]], Awaitable[None] | None]
    ) -> None:
        """Execute file search with debouncing.

        Args:
            query: Search query string.
            callback: Async callback to receive results.
        """
        # Cancel any pending search
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

        # Create new search task
        self._current_task = asyncio.create_task(self._execute_search(query, callback))

    async def _execute_search(
        self, query: str, callback: Callable[[list[FileMatch]], Awaitable[None] | None]
    ) -> None:
        """Execute file search in thread pool.

        Args:
            query: Search query string.
            callback: Async callback to receive results.
        """
        try:
            # Run search in thread pool to avoid blocking
            matches = await asyncio.get_event_loop().run_in_executor(
                self._executor, self._do_search, query
            )

            # Call callback with results
            if asyncio.iscoroutinefunction(callback):
                await callback(matches)
            else:
                callback(matches)

        except asyncio.CancelledError:
            logger.debug("File search cancelled for query: {}", query)
        except Exception as e:
            logger.error("File search error: {}", e)

    def _do_search(self, query: str) -> list[FileMatch]:
        """Perform synchronous file search.

        Args:
            query: Search query string.

        Returns:
            List of file matches sorted by score.
        """
        # Build file cache if needed
        if self._file_cache is None:
            self._file_cache = self._build_file_cache()

        if not query:
            return []

        matches: list[tuple[int, FileMatch]] = []

        for file_path in self._file_cache:
            # Get relative path for display
            try:
                rel_path = file_path.relative_to(self.workspace)
            except ValueError:
                # File not under workspace (shouldn't happen)
                continue

            path_str = str(rel_path)

            # Match against filename and full path
            filename = file_path.name
            score, indices = FuzzyMatcher.match(filename, query)

            if score < 0:
                # Try full path match
                score, indices = FuzzyMatcher.match(path_str, query)

            if score > 0:
                # Adjust indices to be relative to full path string
                if indices:
                    full_indices = self._adjust_indices(path_str, indices)
                else:
                    full_indices = None

                matches.append(
                    (
                        score,
                        FileMatch(path=file_path, score=score, indices=full_indices),
                    )
                )

        # Sort by score descending
        matches.sort(key=lambda x: x[0], reverse=True)

        # Return top 50 matches
        return [m for _, m in matches[:50]]

    def _build_file_cache(self) -> list[Path]:
        """Build cache of all files in workspace.

        Returns:
            List of all file paths.
        """
        files: list[Path] = []
        max_depth = 5  # Limit depth for performance

        try:
            for item in self.workspace.rglob("*"):
                if item.is_file():
                    # Check depth
                    try:
                        rel_path = item.relative_to(self.workspace)
                        depth = len(rel_path.parts)
                        if depth <= max_depth:
                            # Skip common ignore patterns
                            if not self._should_ignore(item):
                                files.append(item)
                    except ValueError:
                        continue
        except PermissionError as e:
            logger.warning("Permission error scanning workspace: {}", e)

        return files

    def _should_ignore(self, path: Path) -> bool:
        """Check if file should be ignored.

        Args:
            path: File path to check.

        Returns:
            True if file should be ignored.
        """
        # Common ignore patterns
        ignore_patterns = [
            "*.pyc",
            "__pycache__",
            ".git",
            ".DS_Store",
            "*.tmp",
            "*.swp",
            "*.o",
            "*.so",
            "*.dylib",
            "*.dll",
            "*.exe",
        ]

        path_str = str(path)
        for pattern in ignore_patterns:
            if fnmatch(path.name, pattern) or pattern in path_str:
                return True

        return False

    @staticmethod
    def _adjust_indices(path_str: str, filename_indices: list[int]) -> list[int] | None:
        """Adjust indices from filename match to full path indices.

        Args:
            path_str: Full path string.
            filename_indices: Indices matched in filename portion.

        Returns:
            Adjusted indices for full path string.
        """
        if not filename_indices:
            return None

        # Find where filename starts in path
        filename_start = path_str.rfind("/") + 1
        if filename_start < 0:
            filename_start = path_str.rfind("\\") + 1

        return [filename_start + i for i in filename_indices]

    def invalidate_cache(self) -> None:
        """Invalidate file cache (force rebuild on next search)."""
        self._file_cache = None

    def cancel(self) -> None:
        """Cancel current search."""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
