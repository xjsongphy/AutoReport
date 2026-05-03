"""Skill loading and management for AutoReport agents.

Skills are Markdown files stored in external/skills/ that provide
domain-specific instructions (e.g., LaTeX compilation). Each skill
is loaded on demand and injected into the agent's system prompt.

Skill files use the following Markdown structure:
  # Skill Title
  (body content)
"""

from pathlib import Path
from typing import Final

from loguru import logger

_PROJECT_ROOT: Final = Path(__file__).parent.parent.parent
_DEFAULT_SKILLS_DIR: Final = _PROJECT_ROOT / "external" / "skills"

# Per-agent skill assignments.
# Map agent_type -> list of skill filenames (without path).
AGENT_SKILLS: dict[str, list[str]] = {
    "report": ["latex-compile.md"],
}


class SkillLoader:
    """Load skill Markdown files and prepare prompt sections for agents."""

    def __init__(self, skills_dir: Path | None = None):
        self._dir = Path(skills_dir) if skills_dir else _DEFAULT_SKILLS_DIR
        self._cache: dict[str, str] = {}

    def _load_skill(self, filename: str) -> str | None:
        if filename in self._cache:
            return self._cache[filename]

        path = self._dir / filename
        if not path.exists():
            logger.warning("Skill file not found: {}", path)
            return None

        content = path.read_text(encoding="utf-8").strip()
        self._cache[filename] = content
        return content

    def get_skills_for_agent(self, agent_type: str) -> list[str]:
        """Return list of skill filenames assigned to an agent."""
        return AGENT_SKILLS.get(agent_type, [])

    def build_skills_section(self, agent_type: str) -> str | None:
        """Build a Markdown section with all skills for an agent.

        Returns None if the agent has no skills assigned.
        """
        skill_files = self.get_skills_for_agent(agent_type)
        if not skill_files:
            return None

        parts: list[str] = []
        for filename in skill_files:
            content = self._load_skill(filename)
            if content:
                parts.append(content)

        if not parts:
            return None

        return (
            "## Available Skills\n\n"
            "The following skills provide specialized instructions for specific tasks. "
            "When performing tasks that match a skill, follow the skill's guidance.\n\n"
            + "\n\n---\n\n".join(parts)
        )

    def reload(self) -> None:
        """Clear cache for hot-reload during development."""
        self._cache.clear()
