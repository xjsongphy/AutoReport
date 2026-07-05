"""Single source of truth for provider default models and API base URLs.

Both the runtime (``ProviderFactory`` / ``OpenAICompatProvider``) and the GUI
config dialog consume these so the defaults shown to the user always match the
defaults applied at runtime.  Keeping them here avoids the factory ↔
openai-provider import cycle and prevents the three previous call sites from
silently drifting apart.
"""

from __future__ import annotations

#: Default model id per provider type. ``custom`` has no default.
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "google": "gemini-2.0-flash-exp",
    "deepseek": "deepseek-chat",
    "openrouter": "anthropic/claude-sonnet-4.6",
    "groq": "llama-3.3-70b-versatile",
    "custom": "",
}

#: Default OpenAI-compatible API base URL per provider type. Providers not
#: listed here rely on the SDK's own default (e.g. the official OpenAI endpoint).
DEFAULT_API_BASES: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
}
