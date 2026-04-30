"""Execution tools for shell commands and Python code."""

import asyncio
import os
from pathlib import Path
from typing import Any

from loguru import logger

from ..tools.registry import Tool

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
    "mineru-open-api",
}

# Allowed Python modules for PythonExecTool
ALLOWED_PYTHON_MODULES = {
    # Math and data analysis
    "math", "cmath", "statistics", "random",
    "decimal", "fractions", "itertools", "collections",
    "numpy", "np",  # numpy and its common alias
    "pandas", "pd",  # pandas and its common alias
    "scipy", "sympy",
    # Plotting
    "matplotlib", "matplotlib.pyplot", "plt",  # matplotlib and common alias
    "plotly",
    # File I/O (within working directory)
    "pathlib", "Path",
    "json", "csv", "yaml",
    # Standard utilities
    "datetime", "time", "re", "string", "textwrap",
    # Type hints
    "typing",
}

# Blocked Python modules (high-risk)
BLOCKED_PYTHON_MODULES = {
    "os", "sys", "subprocess", "shutil", "commands",
    "pty", "fcntl", "signal", "socket",
    "http", "urllib", "requests", "httpx",
    "eval", "exec", "compile", "__import__",
    "globals", "locals", "vars", "dir",
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

        Raises:
            ValueError: If command is not in the allowlist or contains dangerous patterns.
        """
        # Extract the base command (first word)
        import shlex
        try:
            tokens = shlex.split(command.strip())
            if not tokens:
                raise ValueError("Empty command")
            base_command = tokens[0]
        except ValueError:
            # If shlex fails, try simple split
            base_command = command.strip().split()[0] if command.strip() else ""

        # Check if base command is allowed
        if base_command not in ALLOWED_COMMANDS:
            raise ValueError(
                f"Command '{base_command}' is not allowed. "
                f"Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}"
            )

        # Additional safety checks for certain commands
        if base_command in ("rm", "rmdir"):
            # Block deletion of root or system directories
            for arg in tokens[1:]:
                if arg.startswith("/") and arg in ("/", "/home", "/usr", "/etc", "/var", "/root"):
                    raise ValueError(f"Cannot delete system directory: {arg}")
                if ".." in arg:
                    raise ValueError("Path traversal with '..' is not allowed")

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

        Raises:
            ValueError: If code attempts to import blocked modules.
        """
        import sys
        import time
        from io import StringIO

        logger.debug("Executing Python code ({} chars)", len(code))

        # Check for blocked module imports
        code_lower = code.lower()
        for blocked in BLOCKED_PYTHON_MODULES:
            # Check for import statements
            if f"import {blocked}" in code_lower or f"from {blocked}" in code_lower:
                raise ValueError(f"Module '{blocked}' is not allowed for security reasons")

        # Capture stdout
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        start_time = time.time()
        exec_time = None  # Initialize to avoid UnboundLocalError
        error = None

        try:
            # Prepare restricted execution environment
            exec_globals = {
                "__name__": "__exec__",
                "__builtins__": {
                    # Safe builtins
                    "abs": abs,
                    "all": all,
                    "any": any,
                    "bin": bin,
                    "bool": bool,
                    "bytearray": bytearray,
                    "bytes": bytes,
                    "chr": chr,
                    "complex": complex,
                    "dict": dict,
                    "divmod": divmod,
                    "enumerate": enumerate,
                    "filter": filter,
                    "float": float,
                    "format": format,
                    "frozenset": frozenset,
                    "hex": hex,
                    "int": int,
                    "isinstance": isinstance,
                    "issubclass": issubclass,
                    "iter": iter,
                    "len": len,
                    "list": list,
                    "map": map,
                    "max": max,
                    "min": min,
                    "next": next,
                    "oct": oct,
                    "ord": ord,
                    "pow": pow,
                    "print": print,
                    "range": range,
                    "reversed": reversed,
                    "round": round,
                    "set": set,
                    "slice": slice,
                    "sorted": sorted,
                    "str": str,
                    "sum": sum,
                    "tuple": tuple,
                    "zip": zip,
                    # Constants
                    "True": True,
                    "False": False,
                    "None": None,
                },
                # Add allowed modules (will be populated on first import)
                "__imported_modules": {},
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
            "execution_time": exec_time,
        }
