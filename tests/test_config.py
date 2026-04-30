"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest

from autoreport.config import AppConfig, ConfigManager, Settings
from autoreport.config.schema import ApiConfig


@pytest.fixture
def temp_config_file():
    """Create a temporary config file."""
    config_file = Path(tempfile.mktemp(suffix=".yaml"))
    yield config_file
    config_file.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_config_manager_load_default(temp_config_file):
    """Test loading default configuration."""
    settings = Settings(config_path=temp_config_file)
    config = settings.load_config()

    assert isinstance(config, AppConfig)
    assert config.agents.defaults.provider == "auto"


@pytest.mark.asyncio
async def test_config_manager_validate_api_keys():
    """Test API key validation."""
    config_manager = ConfigManager()

    # No API keys configured
    is_valid, available = config_manager.validate_api_keys()
    assert is_valid is False
    assert len(available) == 0

    # Add an Anthropic configuration with API key
    config_manager.config.providers.configurations.append(
        ApiConfig(provider="anthropic", api_key="test_key", enabled=True, name="Test Anthropic")
    )

    is_valid, available = config_manager.validate_api_keys()
    assert is_valid is True
    assert "anthropic" in available


@pytest.mark.asyncio
async def test_config_manager_save_and_load(temp_config_file):
    """Test saving and loading configuration."""
    config_manager = ConfigManager(config_path=temp_config_file)

    # Modify config
    config_manager.config.agents.defaults.model = "custom_model"
    config_manager.config.agents.defaults.temperature = 0.5

    # Save
    config_manager.save_config()

    # Load into new manager
    new_manager = ConfigManager(config_path=temp_config_file)
    config = new_manager.config

    assert config.agents.defaults.model == "custom_model"
    assert config.agents.defaults.temperature == 0.5


@pytest.mark.asyncio
async def test_config_manager_reset(temp_config_file):
    """Test resetting configuration."""
    config_manager = ConfigManager(config_path=temp_config_file)

    # Modify config
    config_manager.config.agents.defaults.model = "custom_model"

    # Save
    config_manager.save_config()

    # Reset
    config_manager.reset_config()

    # Should be back to default
    assert config_manager.config.agents.defaults.model == "anthropic/claude-sonnet-4.5"


@pytest.mark.asyncio
async def test_config_manager_env_override():
    """Test environment variable override for API keys."""
    import os

    # Add an Anthropic configuration first
    config_manager = ConfigManager()
    config_manager.config.providers.configurations.append(
        ApiConfig(provider="anthropic", api_key="original_key", enabled=True, name="Anthropic")
    )

    # Set environment variable
    old_key = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "env_test_key"

    try:
        # Re-create settings to pick up env var
        from autoreport.config.schema import Settings
        settings = Settings()
        settings._apply_env_overrides(config_manager.config)

        # Environment variable should override
        anthropic_cfg = next(
            c for c in config_manager.config.providers.configurations
            if c.provider == "anthropic"
        )
        assert anthropic_cfg.api_key == "env_test_key"

    finally:
        # Restore
        if old_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = old_key
