"""Shared path validation for workspace-scoped file tools."""

from pathlib import Path

_CANONICAL_TOP_DIRS = ("Data", "References", "Theory", "Code", "Tex")


def suggest_canonical_path(path: str) -> str | None:
    p = Path(path)
    parts = list(p.parts)
    if not parts:
        return None

    # Historical prefix hint only; do not auto-correct.
    if parts and parts[0].lower() == "project":
        trimmed = Path(*parts[1:]).as_posix() if len(parts) > 1 else ""
        if trimmed:
            return trimmed
        return None

    first = parts[0]
    for canonical in _CANONICAL_TOP_DIRS:
        if first.lower() == canonical.lower() and first != canonical:
            rest = Path(*parts[1:]).as_posix() if len(parts) > 1 else ""
            return f"{canonical}/{rest}" if rest else canonical
    return None


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
