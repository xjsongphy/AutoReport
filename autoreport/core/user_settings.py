"""User settings persistence service.

Stores user-level preferences in a JSON file under ~/.autoreport/.
Used for flags like "has the user completed onboarding?".
"""

import json
from pathlib import Path

from loguru import logger


class UserSettings:
    """Manage user-level settings stored in ~/.autoreport/user_settings.json."""

    STORAGE_FILE = Path.home() / ".autoreport" / "user_settings.json"

    def __init__(self) -> None:
        self._storage_dir = self.STORAGE_FILE.parent
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    def _load(self) -> dict:
        """Load settings from storage."""
        if not self.STORAGE_FILE.exists():
            return {}

        try:
            data = json.loads(self.STORAGE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning("Failed to load user settings: {}", e)

        return {}

    def _save(self) -> None:
        """Save settings to storage."""
        try:
            self.STORAGE_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save user settings: {}", e)

    def get(self, key: str, default=None):
        """Get a setting value.

        Args:
            key: Setting key.
            default: Default value if key not found.

        Returns:
            Setting value or default.
        """
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        """Set a setting value and persist.

        Args:
            key: Setting key.
            value: Setting value.
        """
        self._data[key] = value
        self._save()

    @property
    def has_seen_onboarding(self) -> bool:
        """Check if user has completed the onboarding tutorial."""
        return bool(self.get("has_seen_onboarding", False))

    @has_seen_onboarding.setter
    def has_seen_onboarding(self, value: bool) -> None:
        self.set("has_seen_onboarding", value)
