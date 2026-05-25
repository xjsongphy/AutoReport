"""Execution tool for shell commands."""

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any

from loguru import logger

from ..tools.registry import Tool

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
    "mineru-open-api",
}


class BashTool(Tool):
    """Tool for executing shell commands."""

    name = "bash"
    description = (
        "Execute a shell command. "
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

            return {
                "command": command,
                "command_description": command_description,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "returncode": process.returncode,
                "timed_out": False,
            }
        except Exception as e:
            logger.error("Failed to execute bash command: {}", e)
            raise
