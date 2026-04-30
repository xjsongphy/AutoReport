"""Tests for preset sync from cc-switch."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoreport.core.preset_sync import SyncError, is_cached, sync_presets


def test_is_cached_false_by_default():
    with patch("autoreport.core.preset_sync._cache_dir", return_value=Path("/nonexistent")):
        assert is_cached() is False


def test_sync_presets_raises_when_all_fail():
    with (
        patch("autoreport.core.preset_sync._cache_dir", return_value=Path("/tmp/test_sync")),
        patch("urllib.request.urlopen", side_effect=Exception("Network error")),
    ):
        with pytest.raises(SyncError, match="无法同步预设数据"):
            sync_presets()


def test_sync_error_is_exception():
    assert issubclass(SyncError, Exception)


def test_sync_presets_success():
    """Test successful preset sync with mocked HTTP responses."""
    import tempfile
    import shutil
    cache_dir = Path(tempfile.mkdtemp())
    try:
        mock_response = MagicMock()
        mock_response.read.return_value = b"export const test = true;"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        config_dir = cache_dir / "src" / "config"

        with (
            patch("autoreport.core.preset_sync._cache_dir", return_value=cache_dir),
            patch("urllib.request.urlopen", return_value=mock_response),
        ):
            count = sync_presets()
            assert count > 0
            assert config_dir.exists()
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


def test_sync_presets_partial_failure():
    """Some files fail, some succeed — should return partial count."""
    import tempfile
    import shutil
    cache_dir = Path(tempfile.mkdtemp())
    try:
        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("Network error")
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"test content"
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with (
            patch("autoreport.core.preset_sync._cache_dir", return_value=cache_dir),
            patch("urllib.request.urlopen", side_effect=mock_urlopen),
        ):
            count = sync_presets()
            assert count > 0
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)
