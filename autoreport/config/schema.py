"""Configuration schema using Pydantic."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Base(BaseModel):
    """Base model with camelCase alias support."""

    model_config = ConfigDict(
        alias_generator=lambda x: "".join(
            word.capitalize() for word in x.split("_")
        ),
        populate_by_name=True,
    )


class ProviderConfig(Base):
    """LLM provider configuration.

    Based on OpenClaw's ModelProviderConfig pattern: each provider has
    an API key, base URL (with sensible default), and optional flags.
    """

    api_key: str | None = None
    api_base: str | None = None
    enabled: bool = True
    default_model: str | None = None
    extra_headers: dict[str, str] | None = None


class ProvidersConfig(Base):
    """Configuration for LLM providers.

    Provider list inspired by OpenClaw's plugin-based provider system.
    """

    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    google: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    custom: ProviderConfig = Field(default_factory=ProviderConfig)


class MinerUAPIConfig(Base):
    """MinerU API configuration for PDF parsing."""

    url: str = "http://localhost:9999"
    enabled: bool = True
    timeout: int = 300
    validate_on_startup: bool = True


class AgentDefaults(Base):
    """Default agent configuration."""

    model: str = "anthropic/claude-sonnet-4.5"
    provider: str = "auto"
    max_tokens: int = 8192
    temperature: float = 0.1
    max_tool_iterations: int = 200
    timezone: str = "Asia/Shanghai"
    prompt_templates_dir: str = "templates/agents"


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class AppConfig(Base):
    """Main application configuration."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    mineru_api: MinerUAPIConfig = Field(default_factory=MinerUAPIConfig)


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment-based API key overrides
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")

    config_path: Path = Field(default=Path("autoreport.config.yaml"))

    def load_config(self) -> AppConfig:
        """Load configuration from YAML file and merge with environment variables."""
        import yaml

        config_data = {}
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

        config = AppConfig(**config_data)

        # Override API keys from environment
        env_overrides: dict[str, str | None] = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "google": self.google_api_key,
            "deepseek": self.deepseek_api_key,
            "openrouter": self.openrouter_api_key,
            "groq": self.groq_api_key,
        }
        for provider_name, env_key in env_overrides.items():
            if env_key:
                getattr(config.providers, provider_name).api_key = env_key

        return config

    def validate_api_keys(self, config: AppConfig) -> list[str]:
        """Validate that at least one enabled provider has an API key."""
        available = []
        for name in ("anthropic", "openai", "google", "deepseek", "openrouter", "groq", "custom"):
            provider = getattr(config.providers, name)
            if provider.enabled and provider.api_key:
                available.append(name)
        return available
