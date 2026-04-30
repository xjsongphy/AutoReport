"""Provider factory for creating LLM provider instances."""

from loguru import logger

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .deepseek_provider import DeepSeekProvider
from .openai_provider import OpenAIProvider

# All supported provider types
ALL_PROVIDER_TYPES = (
    "anthropic", "openai", "google", "deepseek", "openrouter", "groq", "custom",
)

# Providers that use OpenAI-compatible Chat Completions API
_OPENAI_COMPATIBLE = {"openai", "google", "openrouter", "groq", "custom"}

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "google": "gemini-2.0-flash-exp",
    "deepseek": "deepseek-chat",
    "openrouter": "anthropic/claude-sonnet-4.6",
    "groq": "llama-3.3-70b-versatile",
    "custom": "",
}


class ProviderFactory:
    """Factory for creating LLM provider instances."""

    @staticmethod
    def create_provider(
        provider_type: str,
        api_key: str,
        api_base: str | None = None,
        model: str | None = None,
    ) -> LLMProvider:
        """Create a provider instance.

        Args:
            provider_type: anthropic|openai|google|deepseek|openrouter|groq|custom.
            api_key: API key for authentication.
            api_base: Optional custom API base URL.
            model: Optional model override.

        Returns:
            Provider instance.

        Raises:
            ValueError: If provider type is unknown.
        """
        if provider_type not in ALL_PROVIDER_TYPES:
            raise ValueError(f"Unknown provider type: {provider_type}")

        default_model = model or _DEFAULT_MODELS.get(provider_type, "")

        if provider_type == "anthropic":
            return AnthropicProvider(api_key, api_base, default_model)
        elif provider_type == "deepseek":
            return DeepSeekProvider(api_key, api_base, default_model)
        elif provider_type in _OPENAI_COMPATIBLE:
            return OpenAIProvider(api_key, api_base, default_model)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")


class ProviderManager:
    """Manager for LLM provider instances.

    Stores providers keyed by provider type string. Multiple configs
    of the same type are stored by their config ID.
    """

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._active_key: str | None = None

    def register_provider(
        self,
        key: str,
        provider: LLMProvider,
    ) -> None:
        """Register a provider.

        Args:
            key: Unique key for this provider instance (config ID).
            provider: Provider instance.
        """
        self._providers[key] = provider
        logger.debug("Registered provider: {}", key)

        if self._active_key is None:
            self._active_key = key

    def get_active_provider(self) -> LLMProvider:
        """Get the active provider."""
        if self._active_key is None:
            raise ValueError("No active provider")
        return self._providers[self._active_key]

    def set_active_provider(self, key: str) -> None:
        """Set the active provider by key."""
        if key not in self._providers:
            raise ValueError(f"Provider not registered: {key}")
        self._active_key = key
        logger.info("Active provider set to: {}", key)

    def get_available_providers(self) -> list[str]:
        """Get list of available provider keys."""
        return list(self._providers.keys())

    def has_provider(self, key: str) -> bool:
        """Check if a provider is registered."""
        return key in self._providers
