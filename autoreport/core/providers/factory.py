"""Provider factory for creating LLM provider instances."""

from loguru import logger

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .defaults import DEFAULT_API_BASES, DEFAULT_MODELS
from .openai_provider import OpenAICompatProvider

# All supported provider types
ALL_PROVIDER_TYPES = (
    "anthropic", "openai", "google", "deepseek", "openrouter", "groq", "custom",
)


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

        default_model = model or DEFAULT_MODELS.get(provider_type, "")
        # Fall back to the canonical base for this provider type so runtime
        # resolves the same endpoint the GUI pre-fills, even if the config
        # omits an explicit base.
        resolved_base = api_base or DEFAULT_API_BASES.get(provider_type)

        if provider_type == "anthropic":
            return AnthropicProvider(api_key, resolved_base, default_model)
        else:
            return OpenAICompatProvider(
                api_key=api_key,
                api_base=resolved_base,
                model=default_model,
                provider_type=provider_type,
            )


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
