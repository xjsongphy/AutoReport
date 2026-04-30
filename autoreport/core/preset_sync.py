"""Sync provider presets from cc-switch repository.

Downloads TypeScript preset files from cc-switch GitHub and caches them
locally in external/cc-switch/. Files are git-ignored — fetched on demand.
"""

from pathlib import Path

from loguru import logger

CC_SWITCH_REPO = "https://github.com/farion1231/cc-switch"
CC_SWITCH_RAW = "https://raw.githubusercontent.com/farion1231/cc-switch/main"

PRESET_FILES = [
    "claudeProviderPresets.ts",
    "codexProviderPresets.ts",
    "geminiProviderPresets.ts",
    "opencodeProviderPresets.ts",
    "openclawProviderPresets.ts",
    "hermesProviderPresets.ts",
    "universalProviderPresets.ts",
]


class SyncError(Exception):
    """Preset sync failure (network, proxy, etc.)."""


def _cache_dir() -> Path:
    return Path(__file__).parent.parent.parent / "external" / "cc-switch"


def is_cached() -> bool:
    """Check if preset files exist in cache."""
    cfg = _cache_dir() / "src" / "config"
    return cfg.exists() and any(cfg.glob("*ProviderPresets.ts"))


def sync_presets(timeout: int = 15) -> int:
    """Download preset TS files from cc-switch GitHub.

    Returns count of files successfully downloaded.

    Raises SyncError on network/proxy failure.
    """
    import ssl
    import urllib.request

    cache = _cache_dir()
    config_dir = cache / "src" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    ctx = ssl.create_default_context()
    downloaded = 0

    for filename in PRESET_FILES:
        url = f"{CC_SWITCH_RAW}/src/config/{filename}"
        dest = config_dir / filename

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AutoReport/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                content = resp.read().decode("utf-8")
            dest.write_text(content, encoding="utf-8")
            downloaded += 1
            logger.debug("Synced preset: {}", filename)
        except urllib.error.URLError as e:
            reason = str(e.reason) if hasattr(e, "reason") else str(e)
            logger.warning("Failed to sync {}: {}", filename, reason)
        except Exception as e:
            logger.warning("Failed to sync {}: {}", filename, e)

    if downloaded == 0:
        raise SyncError(
            "无法同步预设数据，请检查网络连接和代理设置。\n"
            f"源地址: {CC_SWITCH_RAW}/src/config/\n"
            "你可以稍后点击「同步预设」按钮重试。"
        )

    logger.info("Synced {}/{} preset files from cc-switch", downloaded, len(PRESET_FILES))
    return downloaded
