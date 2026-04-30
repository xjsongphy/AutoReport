"""Provider presets parsed from cc-switch TypeScript files at runtime.

Reads TS preset files from external/cc-switch/ (synced from GitHub) and
extracts structured preset data. Falls back to built-in presets when files
are not available (offline or not yet synced).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class ProviderPreset:
    """A provider preset extracted from cc-switch or built-in."""

    name: str
    provider: str  # "anthropic" | "openai" | "google" | "deepseek" | "openrouter" | "groq" | "custom"
    category: str  # "official" | "cn_official" | "aggregator" | "third_party" | "cloud_provider" | "builtin"
    base_url: str = ""
    default_model: str = ""
    website_url: str = ""
    api_key_url: str | None = None
    description: str = ""
    icon_color: str = ""


def _cache_dir() -> Path:
    return Path(__file__).parent.parent.parent / "external" / "cc-switch"


# ── TS Parser ──────────────────────────────────────────────────────────

def _strip_ts_comments(source: str) -> str:
    """Remove // line comments and /* */ block comments from TypeScript."""
    # Remove block comments
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    # Remove line comments (but not URLs)
    source = re.sub(r"(?<!:)//[^\n]*", "", source)
    return source


def _extract_ts_string(ts: str, key: str) -> str | None:
    """Extract a single-quoted or double-quoted string value for key."""
    # Match: key: "value" or key: 'value'
    m = re.search(rf'{key}\s*:\s*["\']([^"\']*)["\']', ts)
    return m.group(1) if m else None


def _extract_ts_number(ts: str, key: str) -> int | None:
    """Extract a numeric value for key."""
    m = re.search(rf'{key}\s*:\s*(\d+)', ts)
    return int(m.group(1)) if m else None


def _extract_ts_env(ts: str, key: str) -> str | None:
    """Extract an env var value from settingsConfig.env block."""
    m = re.search(rf'{key}\s*:\s*"([^"]*)"', ts)
    if m and m.group(1):
        return m.group(1)
    return None


def _split_ts_objects(text: str) -> list[str]:
    """Split a TS array body into individual top-level object strings."""
    objects: list[str] = []
    depth = 0
    start = -1
    in_string = False
    string_char = ""

    for i, ch in enumerate(text):
        if ch in ('"', "'") and (i == 0 or text[i - 1] != "\\"):
            if not in_string:
                in_string = True
                string_char = ch
            elif ch == string_char:
                in_string = False
            continue

        if in_string:
            continue

        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                objects.append(text[start:i + 1])

    return objects


def _parse_claude_presets(filepath: Path) -> list[ProviderPreset]:
    """Parse a cc-switch Claude-compatible provider presets TS file."""
    if not filepath.exists():
        return []

    content = filepath.read_text(encoding="utf-8")
    clean = _strip_ts_comments(content)

    # Find the preset array
    presets: list[ProviderPreset] = []

    for pattern in [
        r'export const providerPresets[^=]*=\s*\[',
        r'export const universalProviderPresets[^=]*=\s*\[',
    ]:
        m = re.search(pattern, clean)
        if m:
            # Extract everything from [ to the matching ];
            start = m.end()
            # Find matching ] by counting brackets
            depth = 1
            end = start
            in_string = False
            sc = ""
            for i in range(start, len(clean)):
                ch = clean[i]
                if ch in ('"', "'") and (i == 0 or clean[i - 1] != "\\"):
                    if not in_string:
                        in_string = True
                        sc = ch
                    elif ch == sc:
                        in_string = False
                    continue
                if in_string:
                    continue
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break

            array_body = clean[start:end]
            blocks = _split_ts_objects(array_body)

            for block in blocks:
                name = _extract_ts_string(block, "name")
                if not name:
                    continue

                base_url = (
                    _extract_ts_env(block, "ANTHROPIC_BASE_URL")
                    or _extract_ts_env(block, "CLAUDE_CODE_BASE_URL")
                    or ""
                )
                # Remove template variables like ${AWS_REGION} from URLs
                base_url = re.sub(r'\$\{[^}]+\}', "", base_url).rstrip("/")

                default_model = (
                    _extract_ts_env(block, "ANTHROPIC_MODEL")
                    or _extract_ts_env(block, "ANTHROPIC_DEFAULT_SONNET_MODEL")
                    or ""
                )

                category = _extract_ts_string(block, "category") or "third_party"
                website_url = _extract_ts_string(block, "websiteUrl") or ""
                api_key_url = _extract_ts_string(block, "apiKeyUrl")
                icon_color = _extract_ts_string(block, "iconColor") or ""

                provider = "anthropic"

                presets.append(ProviderPreset(
                    name=name,
                    provider=provider,
                    category=category,
                    base_url=base_url,
                    default_model=default_model,
                    website_url=website_url,
                    api_key_url=api_key_url,
                    icon_color=icon_color,
                ))

            break  # Only parse first matching pattern

    return presets


# ── Built-in Fallback Presets ──────────────────────────────────────────

def _builtin_presets() -> list[ProviderPreset]:
    """Built-in presets available when cc-switch files are not synced."""
    return [
        ProviderPreset(
            name="Anthropic (Official)",
            provider="anthropic",
            category="official",
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-20250514",
            website_url="https://www.anthropic.com",
            description="Claude 系列模型",
            icon_color="#D4915D",
        ),
        ProviderPreset(
            name="OpenAI (Official)",
            provider="openai",
            category="official",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o",
            website_url="https://platform.openai.com",
            description="GPT 系列模型",
            icon_color="#74AA9C",
        ),
        ProviderPreset(
            name="Google Gemini",
            provider="google",
            category="official",
            base_url="https://generativelanguage.googleapis.com",
            default_model="gemini-2.0-flash-exp",
            website_url="https://ai.google.dev",
            description="Gemini 系列模型",
            icon_color="#4285F4",
        ),
        ProviderPreset(
            name="DeepSeek",
            provider="deepseek",
            category="official",
            base_url="https://api.deepseek.com/v1",
            default_model="deepseek-chat",
            website_url="https://platform.deepseek.com",
            description="DeepSeek Chat 模型",
            icon_color="#1E88E5",
        ),
        ProviderPreset(
            name="OpenRouter",
            provider="openrouter",
            category="aggregator",
            base_url="https://openrouter.ai/api/v1",
            default_model="anthropic/claude-sonnet-4.6",
            website_url="https://openrouter.ai",
            description="多模型聚合平台",
            icon_color="#6566F1",
        ),
        ProviderPreset(
            name="Groq",
            provider="groq",
            category="official",
            base_url="https://api.groq.com/openai/v1",
            default_model="llama-3.3-70b-versatile",
            website_url="https://groq.com",
            description="高速推理 (LPU 加速)",
            icon_color="#F55036",
        ),
        ProviderPreset(
            name="Custom / Local",
            provider="custom",
            category="custom",
            base_url="http://localhost:11434/v1",
            default_model="",
            description="自建服务 (vLLM, Ollama 等)",
        ),
    ]


# ── Public API ─────────────────────────────────────────────────────────

def load_presets() -> list[ProviderPreset]:
    """Load all available presets (cc-switch + builtin).

    Parses TS files at runtime if cached, falls back to builtin presets.
    cc-switch presets are prioritized for display diversity; builtin presets
    fill gaps for non-Anthropic provider types.
    """
    all_presets: list[ProviderPreset] = []
    seen: set[str] = set()

    # Load from cc-switch TS files
    cache = _cache_dir()
    config_dir = cache / "src" / "config"

    claude_file = config_dir / "claudeProviderPresets.ts"
    if claude_file.exists():
        try:
            cc_presets = _parse_claude_presets(claude_file)
            for p in cc_presets:
                key = p.name.lower()
                if key not in seen:
                    seen.add(key)
                    all_presets.append(p)
            logger.info("Loaded {} presets from cc-switch", len(cc_presets))
        except Exception as e:
            logger.warning("Failed to parse cc-switch presets: {}", e)

    # Add builtin presets for non-Anthropic providers
    for p in _builtin_presets():
        key = p.name.lower()
        if key not in seen:
            seen.add(key)
            all_presets.append(p)

    return all_presets


def get_presets_by_category() -> dict[str, list[ProviderPreset]]:
    """Group presets by category for UI display."""
    presets = load_presets()
    groups: dict[str, list[ProviderPreset]] = {}
    order = ["official", "cn_official", "aggregator", "third_party", "cloud_provider", "custom", "builtin"]

    for p in presets:
        cat = p.category if p.category in order else "builtin"
        groups.setdefault(cat, []).append(p)

    # Sort within each group
    for cat in groups:
        groups[cat].sort(key=lambda p: p.name)

    # Return in category order
    return {k: groups[k] for k in order if k in groups}
