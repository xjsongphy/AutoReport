"""Execution tools for shell commands and Python code."""

import asyncio
import os
from pathlib import Path
from typing import Any

from loguru import logger

from ..tools.registry import Tool

# Dangerous commands that should be blocked
DANGEROUS_COMMANDS = {
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero",
    ":(){ :|:& };:",  # Fork bomb
    "chmod 000",  # Locking files
}


class ExecTool(Tool):
    """Tool for executing shell commands."""

    name = "exec"
    description = "Execute a shell command. Supports data analysis and LaTeX compilation."

    def __init__(
        self,
        working_dir: Path,
        timeout: int = 120,
        allowed_env_keys: list[str] | None = None,
    ):
        """Initialize shell executor.

        Args:
            working_dir: Working directory for command execution.
            timeout: Command timeout in seconds.
            allowed_env_keys: List of allowed environment variable keys to pass.
        """
        self.working_dir = Path(working_dir).resolve()
        self.timeout = timeout
        self.allowed_env_keys = allowed_env_keys or []

    async def __call__(self, command: str) -> dict[str, Any]:
        """Execute a shell command.

        Args:
            command: Command string to execute

        Returns:
            Dictionary with stdout, stderr, returncode, and timed_out
        """
        # Check for dangerous commands
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous in command:
                raise ValueError(f"Dangerous command blocked: {dangerous}")

        logger.debug("Executing command: {} (in {})", command, self.working_dir)

        # Prepare environment
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
                    "stdout": "",
                    "stderr": f"Command timed out after {self.timeout} seconds",
                    "returncode": -1,
                    "timed_out": True,
                }

            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "returncode": process.returncode,
                "timed_out": False,
            }
        except Exception as e:
            logger.error("Failed to execute command: {}", e)
            raise


class PythonExecTool(Tool):
    """Tool for executing Python code."""

    name = "python_exec"
    description = "Execute Python code for data analysis and plotting."

    def __init__(self, working_dir: Path, timeout: int = 60):
        """Initialize Python executor.

        Args:
            working_dir: Working directory for execution.
            timeout: Execution timeout in seconds.
        """
        self.working_dir = Path(working_dir).resolve()
        self.timeout = timeout

    async def __call__(self, code: str) -> dict[str, Any]:
        """Execute Python code.

        Args:
            code: Python code to execute

        Returns:
            Dictionary with output, error, and execution_time
        """
        import sys
        import time
        from io import StringIO

        logger.debug("Executing Python code ({} chars)", len(code))

        # Capture stdout
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        start_time = time.time()
        error = None

        try:
            # Prepare execution environment
            exec_globals = {
                "__name__": "__exec__",
                "__builtins__": __builtins__,
            }

            # Execute with timeout
            exec_task = asyncio.to_thread(
                exec,
                code,
                exec_globals,
            )
            await asyncio.wait_for(exec_task, timeout=self.timeout)

            exec_time = time.time() - start_time

        except asyncio.TimeoutError:
            error = f"Execution timed out after {self.timeout} seconds"
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()

        return {
            "output": output,
            "stderr": stderr_output,
            "error": error,
            "execution_time": exec_time if error is None else None,
        }
