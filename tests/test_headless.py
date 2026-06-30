"""Tests for the headless integration harness."""

from pathlib import Path

import pytest

from autoreport.config.schema import ApiConfig
from tests.headless import HeadlessBackend


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "project"
    ws.mkdir()
    return ws


@pytest.mark.asyncio
async def test_headless_backend_skips_when_provider_is_unusable(tmp_path, monkeypatch):
    """Integration harness should skip when configured providers cannot start."""
    from autoreport.core.providers.factory import ProviderFactory

    backend = HeadlessBackend(_workspace(tmp_path))
    backend.config_manager.config.providers.configurations.clear()
    backend.config_manager.config.providers.configurations.append(
        ApiConfig(
            provider="deepseek",
            api_key="test-key",
            enabled=True,
            name="DeepSeek",
        )
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("provider bootstrap failed")

    monkeypatch.setattr(ProviderFactory, "create_provider", _raise)

    with pytest.raises(pytest.skip.Exception, match="No usable LLM provider"):
        await backend.start()


@pytest.mark.asyncio
async def test_headless_backend_skips_before_provider_init_for_missing_socksio(
    tmp_path, monkeypatch
):
    """SOCKS proxy environments should skip before provider construction."""
    from autoreport.core.providers.factory import ProviderFactory

    backend = HeadlessBackend(_workspace(tmp_path))
    backend.config_manager.config.providers.configurations.clear()
    backend.config_manager.config.providers.configurations.append(
        ApiConfig(
            provider="anthropic",
            api_key="test-key",
            enabled=True,
            name="Anthropic",
        )
    )

    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:7897")

    def _should_not_run(*args, **kwargs):
        raise AssertionError("provider construction should be skipped")

    monkeypatch.setattr(ProviderFactory, "create_provider", _should_not_run)

    with pytest.raises(pytest.skip.Exception, match="socksio"):
        await backend.start()
