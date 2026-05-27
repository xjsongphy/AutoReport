"""Execution tool for shell commands."""

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any

from loguru import logger

from ..tools.registry import Tool
from .path_utils import is_internal_metadata_rel

# Allowed commands for BashTool (allowlist approach)
ALLOWED_COMMANDS = {
    "python", "python3", "pip", "pip3",
    "xelatex", "lualatex", "pdflatex",
    "bibtex", "makeindex",
    "ls", "dir", "cd", "pwd",
    "cat", "head", "tail", "grep", "find",
    "cp", "mv", "rm", "mkdir", "touch", "rmdir",
    "chmod", "chown",
    "git",
    "echo", "printf",
    "wc", "sort", "uniq", "cut",
    "fc-list",
    "mineru-open-api",
}


class BashTool(Tool):
    """Tool for executing shell commands."""

    name = "bash"
    description = (
        "Execute a shell command in the project root directory. "
        "Commands that generate files must specify output paths explicitly—no output files allowed in the project root. "
        "You must provide both command and a short command_description."
    )

    def __init__(
        self,
        working_dir: Path,
        timeout: int = 120,
        allowed_env_keys: list[str] | None = None,
    ):
        self.working_dir = Path(working_dir).resolve()
        self.timeout = timeout
        self.allowed_env_keys = allowed_env_keys or []

    def _check_blocked_paths_in_command(self, command: str, tokens: list[str]) -> None:
        """Check if command attempts to access internal metadata directories."""
        # Check each token for blocked directory access
        for token in tokens:
            # Normalize path separators and check
            normalized = token.replace("\\", "/")
            if is_internal_metadata_rel(normalized):
                raise ValueError(
                    f"Access to internal metadata directories (.autoreport, .checkpoints) is not allowed."
                )

        # Also check the raw command string for patterns
        for prefix in (".autoreport", ".checkpoints"):
            patterns = [
                f" {prefix}",  # space before prefix
                f"{prefix}/",  # prefix with slash
                f'"{prefix}',  # quoted prefix
                f"'{prefix}",  # quoted prefix
            ]
            if any(pattern in command for pattern in patterns):
                raise ValueError(
                    f"Access to internal metadata directories (.autoreport, .checkpoints) is not allowed."
                )

    async def __call__(self, command: str, command_description: str) -> dict[str, Any]:
        """Execute a shell command.

        Args:
            command: Command string to execute.
            command_description: Short human-readable command description.
        """
        if not str(command_description or "").strip():
            raise ValueError("command_description is required")

        try:
            tokens = shlex.split(command.strip())
            if not tokens:
                raise ValueError("Empty command")
            base_command = tokens[0]
        except ValueError:
            base_command = command.strip().split()[0] if command.strip() else ""
            tokens = command.strip().split()

        if base_command not in ALLOWED_COMMANDS:
            raise ValueError(
                f"Command '{base_command}' is not allowed. "
                f"Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}"
            )

        # Block access to internal metadata directories
        self._check_blocked_paths_in_command(command, tokens)

        if base_command in ("rm", "rmdir"):
            for arg in tokens[1:]:
                if arg.startswith("/") and arg in ("/", "/home", "/usr", "/etc", "/var", "/root"):
                    raise ValueError(f"Cannot delete system directory: {arg}")
                if ".." in arg:
                    raise ValueError("Path traversal with '..' is not allowed")

        logger.debug("Executing bash command: {} (in {})", command, self.working_dir)

        env = {}
        for key in self.allowed_env_keys:
            if key in os.environ:
                env[key] = os.environ[key]

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env or None,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "command": command,
                    "command_description": command_description,
                    "stdout": "",
                    "stderr": f"Command timed out after {self.timeout} seconds",
                    "returncode": -1,
                    "timed_out": True,
                }

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Post-process: filter internal metadata directories from output
            if base_command == "ls":
                stdout_str = self._filter_ls_output(stdout_str)
            elif base_command == "find":
                stdout_str = self._filter_find_output(stdout_str)

            return {
                "command": command,
                "command_description": command_description,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "returncode": process.returncode,
                "timed_out": False,
            }
        except Exception as e:
            logger.error("Failed to execute bash command: {}", e)
            raise

    def _filter_ls_output(self, output: str) -> str:
        """Filter .autoreport and .checkpoints from ls command output."""
        lines = output.splitlines()
        filtered = []
        for line in lines:
            stripped = line.strip()
            parts = stripped.split()
            last = parts[-1] if parts else ""
            if any(
                stripped == p
                or f"{p}/" in line.replace("\\", "/")
                or last == p
                or last.endswith(f" -> {p}")
                for p in (".autoreport", ".checkpoints")
            ):
                continue
            filtered.append(line)
        return "\n".join(filtered)

    def _filter_find_output(self, output: str) -> str:
        """Filter .autoreport and .checkpoints from find command output."""
        lines = output.splitlines()
        filtered = []
        for line in lines:
            normalized = line.strip().replace("\\", "/")
            if any(
                normalized == f"./{p}"
                or normalized == f"./{p}/"
                or normalized.startswith(f"./{p}/")
                or normalized == p
                or normalized.startswith(f"{p}/")
                for p in (".autoreport", ".checkpoints")
            ):
                continue
            filtered.append(line)
        return "\n".join(filtered)
