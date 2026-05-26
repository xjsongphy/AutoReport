"""Sync provider presets from cc-switch repository and skills from skill repository.

Downloads TypeScript preset files from cc-switch GitHub and caches them
locally in external/cc-switch/. Also syncs skill files to external/skills/.
Files are git-ignored — fetched on demand.
"""

from pathlib import Path

from loguru import logger

CC_SWITCH_REPO = "https://github.com/farion1231/cc-switch"
CC_SWITCH_RAW = "https://raw.githubusercontent.com/farion1231/cc-switch/main"

SKILLS_REPO = "https://github.com/xjsongphy/skills"
SKILLS_BRANCH = "main"

PRESET_FILES = [
    "claudeProviderPresets.ts",
    "codexProviderPresets.ts",
    "geminiProviderPresets.ts",
    "opencodeProviderPresets.ts",
    "openclawProviderPresets.ts",
    "hermesProviderPresets.ts",
    "universalProviderPresets.ts",
]

SKILL_FILES = [
    ("latex-compile", "SKILL.md"),
    ("experiment-report-writer", "SKILL.md"),
]


class SyncError(Exception):
    """Preset sync failure (network, proxy, etc.)."""


def _cache_dir() -> Path:
    return Path(__file__).parent.parent.parent / "external" / "cc-switch"


def _skills_dir() -> Path:
    return Path(__file__).parent.parent.parent / "external" / "skills"


def is_cached() -> bool:
    """Check if preset files exist in cache."""
    cfg = _cache_dir() / "src" / "config"
    return cfg.exists() and any(cfg.glob("*ProviderPresets.ts"))


def _download_file(url: str, dest: Path, timeout: int, ctx) -> bool:
    """Download a single file. Returns True on success."""
    import urllib.request

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AutoReport/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            content = resp.read().decode("utf-8")
        dest.write_text(content, encoding="utf-8")
        return True
    except urllib.error.URLError as e:
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        logger.warning("Failed to sync {}: {}", dest.name, reason)
    except Exception as e:
        logger.warning("Failed to sync {}: {}", dest.name, e)
    return False


def sync_presets(timeout: int = 15) -> int:
    """Download preset TS files from cc-switch GitHub and skills from skill repo.

    Returns total count of files successfully downloaded.

    Raises SyncError on network/proxy failure (when nothing could be downloaded).
    """
    import ssl
    import urllib.request

    ctx = ssl.create_default_context()
    downloaded = 0

    # Sync cc-switch presets
    cache = _cache_dir()
    config_dir = cache / "src" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    for filename in PRESET_FILES:
        url = f"{CC_SWITCH_RAW}/src/config/{filename}"
        dest = config_dir / filename
        if _download_file(url, dest, timeout, ctx):
            downloaded += 1
            logger.debug("Synced preset: {}", filename)

    # Sync skills
    skills_dir = _skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)

    for skill_name, filename in SKILL_FILES:
        url = f"https://raw.githubusercontent.com/xjsongphy/skills/{SKILLS_BRANCH}/{skill_name}/{filename}"
        dest = skills_dir / f"{skill_name}.md"
        if _download_file(url, dest, timeout, ctx):
            downloaded += 1
            logger.debug("Synced skill: {}/{}", skill_name, filename)

    if downloaded == 0:
        raise SyncError(
            "无法同步预设数据，请检查网络连接和代理设置。\n"
            f"源地址: {CC_SWITCH_RAW}/src/config/\n"
            "你可以稍后点击「同步预设」按钮重试。"
        )

    logger.info("Synced {} files (presets + skills)", downloaded)
    return downloaded
