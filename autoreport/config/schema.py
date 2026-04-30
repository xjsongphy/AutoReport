"""Configuration schema using Pydantic."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=lambda x: ''.join(
        word.capitalize() for word in x.split('_')
    ), populate_by_name=True)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str | None = None
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None


class ProvidersConfig(Base):
    """Configuration for LLM providers."""

    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)


class AgentDefaults(Base):
    """Default agent configuration."""

    model: str = "anthropic/claude-sonnet-4.5"
    provider: Literal["anthropic", "openai", "deepseek", "auto"] = "auto"
    max_tokens: int = 8192
    temperature: float = 0.1
    max_tool_iterations: int = 200
    timezone: str = "Asia/Shanghai"


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class AppConfig(Base):
    """Main application configuration."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment-based API key overrides (higher priority than YAML)
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")

    # Config file path
    config_path: Path = Field(default=Path("autoreport.config.yaml"))

    def load_config(self) -> AppConfig:
        """Load configuration from YAML file and merge with environment variables."""
        import yaml

        config_data = {}
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

        config = AppConfig(**config_data)

        # Override API keys from environment if present
        if self.anthropic_api_key:
            config.providers.anthropic.api_key = self.anthropic_api_key
        if self.openai_api_key:
            config.providers.openai.api_key = self.openai_api_key
        if self.deepseek_api_key:
            config.providers.deepseek.api_key = self.deepseek_api_key

        return config

    def validate_api_keys(self, config: AppConfig) -> list[str]:
        """Validate that at least one API key is configured. Returns list of available providers."""
        available = []
        if config.providers.anthropic.api_key:
            available.append("anthropic")
        if config.providers.openai.api_key:
            available.append("openai")
        if config.providers.deepseek.api_key:
            available.append("deepseek")
        return available
