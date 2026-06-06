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
    "which", "sed",  # Standard Unix tools for cross-platform bash usage
}


class BashTool(Tool):
    """Tool for executing shell commands."""

    name = "bash"
    description = (
        "Execute a command in a Bash shell (NOT Windows cmd.exe or PowerShell). "
        "The working directory is the project root. "
        "All commands must use valid bash/Linux syntax:\n"
        "- Use 'which' not 'where'\n"
        "- Use 'cp' not 'copy'\n"
        '- Use \'echo "" >> file\' not \'echo.>> file\'\n'
        "- Paths use forward slashes, not backslashes\n"
        "Commands that generate files must specify output paths explicitly. "
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
        """Filter .autoreport and .checkpoints from ls command output.

        This prevents agents from discovering internal metadata directories
        through commands like 'ls -a' that list hidden files.
        """
        lines = output.splitlines()
        filtered = []
        for line in lines:
            # Filter out lines that are exactly our protected directories
            # or contain them as path components
            should_filter = False
            for protected in (".autoreport", ".checkpoints"):
                # Check if line is exactly the directory name (ls -a format)
                if line.strip() == protected:
                    should_filter = True
                    break
                # Check if line contains protected/ (e.g., ".autoreport/file")
                if f"{protected}/" in line.replace("\\", "/"):
                    should_filter = True
                    break
                # Check if line ends with the protected directory name (ls -la format)
                # The line format is: permissions links user group size date time name
                # So we check if the last word is the protected directory name
                parts = line.strip().split()
                if parts and parts[-1] == protected:
                    should_filter = True
                    break
                # Also check if last part is a symlink to protected directory
                if parts and parts[-1].endswith(f" -> {protected}"):
                    should_filter = True
                    break
            if not should_filter:
                filtered.append(line)
        return "\n".join(filtered)

    def _filter_find_output(self, output: str) -> str:
        """Filter .autoreport and .checkpoints from find command output.

        The find command outputs paths like "./.autoreport" or "./.checkpoints/file".
        We need to filter these out.
        """
        lines = output.splitlines()
        filtered = []
        for line in lines:
            should_filter = False
            normalized = line.strip().replace("\\", "/")
            for protected in (".autoreport", ".checkpoints"):
                # Check for patterns like:
                # ./.autoreport
                # ./.autoreport/
                # ./.autoreport/file
                if (normalized == f"./{protected}" or
                    normalized == f"./{protected}/" or
                    normalized.startswith(f"./{protected}/") or
                    normalized == protected or
                    normalized.startswith(f"{protected}/")):
                    should_filter = True
                    break
            if not should_filter:
                filtered.append(line)
        return "\n".join(filtered)
