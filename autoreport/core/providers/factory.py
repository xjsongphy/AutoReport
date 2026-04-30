"""Provider factory for creating LLM provider instances."""

from typing import Literal

from loguru import logger

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .deepseek_provider import DeepSeekProvider
from .openai_provider import OpenAIProvider

ProviderType = Literal["anthropic", "openai", "deepseek"]


class ProviderFactory:
    """Factory for creating LLM provider instances."""

    @staticmethod
    def create_provider(
        provider_type: ProviderType,
        api_key: str,
        api_base: str | None = None,
        model: str | None = None,
    ) -> LLMProvider:
        """Create a provider instance.

        Args:
            provider_type: Type of provider to create.
            api_key: API key for authentication.
            api_base: Optional custom API base URL.
            model: Optional model override.

        Returns:
            Provider instance.

        Raises:
            ValueError: If provider type is unknown.
        """
        if provider_type == "anthropic":
            default_model = model or "claude-sonnet-4.5"
            return AnthropicProvider(api_key, api_base, default_model)
        elif provider_type == "openai":
            default_model = model or "gpt-4o"
            return OpenAIProvider(api_key, api_base, default_model)
        elif provider_type == "deepseek":
            default_model = model or "deepseek-chat"
            return DeepSeekProvider(api_key, api_base, default_model)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")


class ProviderManager:
    """Manager for LLM providers."""

    def __init__(self):
        """Initialize provider manager."""
        self._providers: dict[ProviderType, LLMProvider] = {}
        self._active_provider: ProviderType | None = None

    def register_provider(
        self,
        provider_type: ProviderType,
        provider: LLMProvider,
    ) -> None:
        """Register a provider.

        Args:
            provider_type: Type of provider.
            provider: Provider instance.
        """
        self._providers[provider_type] = provider
        logger.debug("Registered provider: {}", provider_type)

        # Set as active if first provider
        if self._active_provider is None:
            self._active_provider = provider_type

    def get_active_provider(self) -> LLMProvider:
        """Get the active provider.

        Returns:
            Active provider instance.

        Raises:
            ValueError: If no active provider.
        """
        if self._active_provider is None:
            raise ValueError("No active provider")

        return self._providers[self._active_provider]

    def set_active_provider(self, provider_type: ProviderType) -> None:
        """Set the active provider.

        Args:
            provider_type: Provider type to activate.

        Raises:
            ValueError: If provider not registered.
        """
        if provider_type not in self._providers:
            raise ValueError(f"Provider not registered: {provider_type}")

        self._active_provider = provider_type
        logger.info("Active provider set to: {}", provider_type)

    def get_available_providers(self) -> list[ProviderType]:
        """Get list of available providers.

        Returns:
            List of available provider types.
        """
        return list(self._providers.keys())

    def has_provider(self, provider_type: ProviderType) -> bool:
        """Check if a provider is registered.

        Args:
            provider_type: Provider type to check.

        Returns:
            True if provider is registered.
        """
        return provider_type in self._providers
