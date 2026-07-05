"""Configuration manager for AutoReport."""

from pathlib import Path

from loguru import logger

from .schema import ApiConfig, AppConfig, Settings


class ConfigManager:
    """Manages application configuration."""

    def __init__(self, config_path: Path | None = None):
        if config_path:
            self._settings = Settings(config_path=config_path)
        else:
            self._settings = Settings()
        self._config: AppConfig | None = None

    @property
    def config(self) -> AppConfig:
        """Get loaded configuration."""
        if self._config is None:
            self._config = self._settings.load_config()
        return self._config

    def reload(self) -> AppConfig:
        """Reload configuration from file."""
        self._config = self._settings.load_config()
        logger.info("Configuration reloaded from {}", self._settings.config_path)
        return self._config

    def validate_api_keys(self) -> tuple[bool, list[str]]:
        """Validate API configuration.

        Returns:
            Tuple of (is_valid, list_of_available_provider_types).
        """
        available = self._settings.validate_api_keys(self.config)
        is_valid = len(available) > 0
        return is_valid, available

    def get_active_config(self) -> ApiConfig | None:
        """Get the currently active API configuration."""
        for cfg in self.config.providers.configurations:
            if cfg.id == self.config.providers.active:
                return cfg
        # Fallback: return first enabled config with a key
        for cfg in self.config.providers.configurations:
            if cfg.enabled and cfg.api_key:
                return cfg
        return None

    def get_active_provider(self) -> str:
        """Get the active provider type string.

        Returns provider type of active config, or falls back to
        priority order: anthropic > openai > deepseek.
        """
        active = self.get_active_config()
        if active:
            return active.provider

        _, available = self.validate_api_keys()
        for provider in ["anthropic", "openai", "deepseek"]:
            if provider in available:
                return provider

        raise ValueError("No API keys configured. Please set at least one provider.")

    def get_provider_config(self, provider: str) -> dict:
        """Get configuration for a specific provider type.

        Returns the first enabled config matching the provider type.
        """
        for cfg in self.config.providers.configurations:
            if cfg.provider == provider and cfg.enabled and cfg.api_key:
                return {
                    "api_key": cfg.api_key,
                    "api_base": cfg.api_base,
                    "extra_headers": cfg.extra_headers,
                }

        raise ValueError(f"No enabled configuration found for provider '{provider}'")

    def save_config(self) -> None:
        """Save configuration to file."""
        import yaml

        config_path = self._settings.config_path
        config_dict = self.config.model_dump(mode="json", exclude_none=True)
        providers = config_dict.get("providers", {})
        config_dict["providers"] = {
            "configurations": providers.get("configurations", []),
            "active": self.config.providers.active,
        }

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)

        logger.info("Configuration saved to {}", config_path)

    def reset_config(self) -> None:
        """Reset configuration to defaults."""
        self._config = AppConfig()
        logger.info("Configuration reset to defaults")
