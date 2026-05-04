"""Tests for path validation utilities."""

import tempfile
from pathlib import Path

import pytest

from autoreport.core.tools.path_utils import resolve_and_validate_path


@pytest.fixture
def workspace():
    """Create a temporary workspace with resolved path (avoids Windows short-name mismatch)."""
    import shutil
    ws = Path(tempfile.mkdtemp()).resolve()
    yield ws
    shutil.rmtree(ws, ignore_errors=True)


def test_resolve_relative_path(workspace):
    resolved = resolve_and_validate_path("data/test.csv", workspace)
    assert resolved == (workspace / "data" / "test.csv").resolve()


def test_resolve_nested_relative_path(workspace):
    resolved = resolve_and_validate_path("data/processed/result.json", workspace)
    assert resolved == (workspace / "data" / "processed" / "result.json").resolve()


def test_reject_absolute_path():
    ws = Path(tempfile.mkdtemp()).resolve()
    # Use an OS-appropriate absolute path
    abs_path = str(Path("/") / "etc" / "passwd")
    with pytest.raises(ValueError):
        resolve_and_validate_path(abs_path, ws)


def test_reject_path_traversal(workspace):
    with pytest.raises(ValueError, match="Path traversal"):
        resolve_and_validate_path("../etc/passwd", workspace)


def test_reject_deep_path_traversal(workspace):
    with pytest.raises(ValueError, match="Path traversal"):
        resolve_and_validate_path("data/../../etc/passwd", workspace)


def test_resolve_dot_path(workspace):
    resolved = resolve_and_validate_path(".", workspace)
    assert resolved == workspace


def test_resolve_path_with_spaces(workspace):
    resolved = resolve_and_validate_path("data/my file.csv", workspace)
    assert resolved == (workspace / "data" / "my file.csv").resolve()
