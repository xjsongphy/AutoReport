"""Tests for configuration schema (Pydantic models)."""

import tempfile
from pathlib import Path

from autoreport.config.schema import (
    AgentDefaults,
    AgentsConfig,
    ApiConfig,
    AppConfig,
    MinerUAPIConfig,
    ProvidersConfig,
    Settings,
)


def test_api_config_defaults():
    cfg = ApiConfig()
    assert cfg.name == "Unnamed"
    assert cfg.provider == "custom"
    assert cfg.api_key is None
    assert cfg.enabled is True
    assert len(cfg.id) == 8


def test_api_config_custom():
    cfg = ApiConfig(
        provider="anthropic",
        api_key="sk-test",
        name="My Anthropic",
    )
    assert cfg.provider == "anthropic"
    assert cfg.api_key == "sk-test"


def test_providers_config():
    cfg = ProvidersConfig()
    assert cfg.configurations == []
    assert cfg.active is None


def test_mineru_config_defaults():
    cfg = MinerUAPIConfig()
    assert cfg.timeout == 300
    assert cfg.enabled is True


def test_agent_defaults():
    cfg = AgentDefaults()
    assert cfg.model == "anthropic/claude-sonnet-4.5"
    assert cfg.provider == "auto"
    assert cfg.max_tokens == 8192
    assert cfg.temperature == 0.1
    assert cfg.max_tool_iterations == 200


def test_app_config_defaults():
    cfg = AppConfig()
    assert isinstance(cfg.agents, AgentsConfig)
    assert isinstance(cfg.providers, ProvidersConfig)
    assert isinstance(cfg.mineru_api, MinerUAPIConfig)


def test_settings_load_default():
    config_file = Path(tempfile.mktemp(suffix=".yaml"))
    try:
        settings = Settings(config_path=config_file)
        config = settings.load_config()
        assert isinstance(config, AppConfig)
        assert config.agents.defaults.provider == "auto"
    finally:
        config_file.unlink(missing_ok=True)


def test_settings_load_from_yaml():
    import yaml

    config_file = Path(tempfile.mktemp(suffix=".yaml"))
    try:
        data = {
            "agents": {
                "defaults": {
                    "model": "gpt-4o",
                    "temperature": 0.5,
                }
            }
        }
        config_file.write_text(yaml.dump(data), encoding="utf-8")

        settings = Settings(config_path=config_file)
        config = settings.load_config()

        assert config.agents.defaults.model == "gpt-4o"
        assert config.agents.defaults.temperature == 0.5
    finally:
        config_file.unlink(missing_ok=True)


def test_settings_migrate_old_providers():
    import yaml

    config_file = Path(tempfile.mktemp(suffix=".yaml"))
    try:
        data = {
            "providers": {
                "anthropic": {"api_key": "sk-old", "enabled": True},
                "openai": {"api_key": None, "enabled": True},
            }
        }
        config_file.write_text(yaml.dump(data), encoding="utf-8")

        settings = Settings(config_path=config_file)
        config = settings.load_config()

        # Migration creates configs for all 7 provider types
        assert len(config.providers.configurations) == 7
        anthropic_cfg = next(
            c for c in config.providers.configurations if c.provider == "anthropic"
        )
        assert anthropic_cfg.api_key == "sk-old"
        assert config.providers.active == "anthropic-default"
    finally:
        config_file.unlink(missing_ok=True)


def test_settings_env_override():
    import os

    config_file = Path(tempfile.mktemp(suffix=".yaml"))
    try:
        import yaml

        data = {
            "providers": {
                "configurations": [
                    {
                        "id": "test-anthropic",
                        "name": "Anthropic",
                        "provider": "anthropic",
                        "api_key": "original",
                        "enabled": True,
                    }
                ]
            }
        }
        config_file.write_text(yaml.dump(data), encoding="utf-8")

        old_key = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "env_key"
        try:
            settings = Settings(config_path=config_file)
            config = settings.load_config()
            anthropic_cfg = next(
                c for c in config.providers.configurations if c.provider == "anthropic"
            )
            assert anthropic_cfg.api_key == "env_key"
        finally:
            if old_key is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old_key
    finally:
        config_file.unlink(missing_ok=True)


def test_settings_validate_api_keys():
    config = AppConfig()
    settings = Settings()
    available = settings.validate_api_keys(config)
    assert available == []


def test_settings_validate_api_keys_with_key():
    config = AppConfig()
    config.providers.configurations.append(
        ApiConfig(provider="anthropic", api_key="sk-test", enabled=True, name="Test")
    )
    settings = Settings()
    available = settings.validate_api_keys(config)
    assert "anthropic" in available


def test_settings_validate_api_keys_disabled():
    config = AppConfig()
    config.providers.configurations.append(
        ApiConfig(provider="anthropic", api_key="sk-test", enabled=False, name="Test")
    )
    settings = Settings()
    available = settings.validate_api_keys(config)
    assert available == []


def test_api_config_camelcase_alias():
    # Alias generator capitalizes each word: default_model → DefaultModel
    cfg = ApiConfig(**{"DefaultModel": "gpt-4o", "Name": "Test"})
    assert cfg.default_model == "gpt-4o"
    assert cfg.name == "Test"
