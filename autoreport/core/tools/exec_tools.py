"""Execution tool for shell commands."""

import asyncio
import os
import platform
import shlex
from pathlib import Path
from typing import Any

from loguru import logger

from ..tools.registry import Tool
from .path_utils import is_internal_metadata_path, is_internal_metadata_rel


def _get_default_shell_name() -> str:
    """Detect the actual shell used by create_subprocess_shell().

    Returns:
        The detected shell name (e.g., '/bin/sh', '/bin/bash', 'cmd.exe').
    """
    system = platform.system()

    if system == "Windows":
        # On Windows, create_subprocess_shell() uses %COMSPEC% or defaults to cmd.exe
        return os.environ.get("COMSPEC", "cmd.exe")

    # On Unix systems (Linux, macOS, etc.), create_subprocess_shell() uses /bin/sh
    # /bin/sh is guaranteed to exist on POSIX-compliant systems
    try:
        sh_path = os.path.realpath("/bin/sh")
        if sh_path != "/bin/sh":
            # /bin/sh is a symlink, show where it points
            return f"/bin/sh → {sh_path}"
        return "/bin/sh"
    except (OSError, RuntimeError):
        # Fallback if /bin/sh doesn't exist or can't be read
        return "/bin/sh (unknown)"


# Global cache for detected shell info
_DETECTED_SHELL: str | None = None


def get_shell_info() -> str:
    """Get the detected shell information for this platform.

    This returns the actual shell that will be used by asyncio.create_subprocess_shell().
    Results are cached after first call.

    Returns:
        Human-readable shell description.
    """
    global _DETECTED_SHELL
    if _DETECTED_SHELL is None:
        _DETECTED_SHELL = _get_default_shell_name()
    return _DETECTED_SHELL

# Allowed commands for ExecTool (allowlist approach)
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
    "which", "sed",  # Standard Unix tools for cross-platform shell usage
}


class ExecTool(Tool):
    """Tool for executing shell commands."""

    name = "exec"

    @property
    def description(self) -> str:
        """Dynamic description based on detected shell."""
        shell_info = get_shell_info()
        return (
            f"Execute shell commands using {shell_info}. "
            f"The working directory is the project root. "
            "Commands that generate files must specify output paths explicitly. "
            "Provide both command and a short command_description. "
            "Arguments: command and command_description. "
            "Example: command='python script.py', command_description='Run plotting script'. "
            "Note: file changes made here (rm, cp, mv, python writing files, etc.) "
            "are NOT recorded by checkpoints and cannot be rolled back. Prefer "
            "delete_file / apply_patch for files you may need to restore; use rm "
            "only for bulk cleanup when necessary."
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
                    "Access to internal metadata directories (.autoreport, .checkpoints) is not allowed."
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
                    "Access to internal metadata directories (.autoreport, .checkpoints) is not allowed."
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

        logger.debug("Executing shell command: {} (in {})", command, self.working_dir)

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
            logger.error("Failed to execute shell command: {}", e)
            raise

    def _filter_ls_output(self, output: str) -> str:
        """Filter internal metadata directories (``.autoreport``/``.checkpoints``) from ``ls`` output.

        When stdout is a pipe (not a TTY), ``ls`` prints one entry per line,
        either as a bare name (``ls -a``) or in long format (``ls -la``).  We
        extract the entry name, resolve it against the working directory on the
        *filesystem*, and drop it iff it resolves into an internal metadata
        directory.  This is locale- and flag-independent: it does not parse the
        permissions/user/date fields and follows symlinks to their real target.
        """
        workspace = Path(self.working_dir)
        kept = []
        for line in output.splitlines():
            name = _ls_entry_name(line)
            if name is not None:
                resolved = (workspace / name).resolve()
                if is_internal_metadata_path(resolved, workspace):
                    continue
            kept.append(line)
        return "\n".join(kept)

    def _filter_find_output(self, output: str) -> str:
        """Filter internal metadata directories from ``find`` output.

        ``find`` prints one relative path per line (e.g. ``./.autoreport/file``).
        Normalize each to a POSIX relative path and drop it iff it falls under
        an internal metadata directory.
        """
        kept = []
        for line in output.splitlines():
            normalized = line.strip().replace("\\", "/")
            if normalized.startswith("./"):
                normalized = normalized[2:]
            normalized = normalized.rstrip("/")
            if normalized and is_internal_metadata_rel(normalized):
                continue
            kept.append(line)
        return "\n".join(kept)


def _ls_entry_name(line: str) -> str | None:
    """Extract the file/directory name from a single ``ls`` output line.

    Handles both bare names (``ls``/``ls -a``) and long-format lines
    (``ls -l``/``ls -la``), including symlink lines of the form
    ``... name -> target`` (returns ``name``, so the link is resolved on the
    filesystem to decide whether it points into a protected directory).
    """
    s = line.strip()
    if not s:
        return None
    if " -> " in s:
        s = s.split(" -> ", 1)[0]
    parts = s.split()
    return parts[-1] if parts else None
