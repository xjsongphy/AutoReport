"""Shared path validation for workspace-scoped file tools."""

from pathlib import Path


def resolve_and_validate_path(path: str, workspace: Path) -> Path:
    """Resolve a relative path and verify it stays within workspace.

    Args:
        path: Path relative to workspace.
        workspace: Root workspace directory.

    Returns:
        Resolved absolute path within workspace.

    Raises:
        ValueError: If path is absolute, contains "..", or resolves outside workspace.
    """
    path_obj = Path(path)
    if path_obj.is_absolute():
        raise ValueError(
            f"Absolute paths are not allowed: {path}. "
            "Please use paths relative to the workspace."
        )

    if ".." in path_obj.parts:
        raise ValueError(
            f"Path traversal with '..' is not allowed: {path}"
        )

    resolved = (workspace / path_obj).resolve()

    try:
        resolved.relative_to(workspace)
    except ValueError:
        raise ValueError(
            f"Resolved path is outside workspace: {resolved}"
        )

    return resolved
