"""Configuration manager for AutoReport."""

from pathlib import Path
from loguru import logger

from .schema import Settings, AppConfig


class ConfigManager:
    """Manages application configuration."""

    def __init__(self, config_path: Path | None = None):
        """Initialize configuration manager.

        Args:
            config_path: Optional path to configuration file.
        """
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
            Tuple of (is_valid, list_of_available_providers)
        """
        available = self._settings.validate_api_keys(self.config)
        is_valid = len(available) > 0
        return is_valid, available

    def get_active_provider(self) -> str:
        """Get the active provider based on configuration and available API keys.

        Returns:
            Provider name that should be used.
        """
        _, available = self.validate_api_keys()

        # If explicit provider is set and available, use it
        if self.config.agents.defaults.provider != "auto":
            if self.config.agents.defaults.provider in available:
                return self.config.agents.defaults.provider
            logger.warning(
                "Configured provider '{}' is not available. Available: {}",
                self.config.agents.defaults.provider,
                available,
            )

        # Auto-select: prefer anthropic > openai > deepseek
        for provider in ["anthropic", "openai", "deepseek"]:
            if provider in available:
                return provider

        raise ValueError("No API keys configured. Please set at least one provider.")

    def get_provider_config(self, provider: str) -> dict:
        """Get configuration for a specific provider.

        Args:
            provider: Provider name (anthropic, openai, deepseek)

        Returns:
            Dictionary with api_key, api_base, extra_headers
        """
        provider_config = getattr(self.config.providers, provider)
        return {
            "api_key": provider_config.api_key,
            "api_base": provider_config.api_base,
            "extra_headers": provider_config.extra_headers,
        }
