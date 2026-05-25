"""Skill loading tool for on-demand skill access."""

import re
from pathlib import Path

from loguru import logger

from ..tools.registry import Tool


class SkillLoader:
    """Load and manage skill Markdown files.

    Skills are loaded on-demand. Agents see only descriptions in their prompt,
    and can call load_skill to get full content when needed.
    """

    def __init__(self, skills_dir: Path | None = None):
        from pathlib import Path
        if skills_dir:
            self._dir = Path(skills_dir)
        else:
            # autoreport/core/tools/skill_tool.py -> project root -> external/skills
            project_root = Path(__file__).parent.parent.parent.parent
            self._dir = project_root / "external" / "skills"
        self._cache: dict[str, dict] = {}  # filename -> {name, description, content}

    def _parse_skill_file(self, path: Path) -> dict | None:
        """Parse a skill file with frontmatter.

        Returns:
            dict with name, description, content or None if parse fails
        """
        try:
            content = path.read_text(encoding="utf-8")

            # Parse YAML frontmatter between ---
            frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
            if not frontmatter_match:
                logger.warning("Skill file missing frontmatter: {}", path)
                return None

            frontmatter_text = frontmatter_match.group(1)
            body_content = frontmatter_match.group(2).strip()

            # Parse name and description from frontmatter
            name = None
            description = None
            for line in frontmatter_text.split("\n"):
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key == "name":
                    name = value
                elif key == "description":
                    description = value

            if not name or not description:
                logger.warning("Skill file missing name or description: {}", path)
                return None

            return {
                "name": name,
                "description": description,
                "content": body_content,
                "filename": path.name,
            }
        except Exception as e:
            logger.error("Failed to parse skill file {}: {}", path, e)
            return None

    def get_available_skills(self) -> list[dict]:
        """Get list of all available skills (name + description only).

        Returns:
            List of dicts with name, description, filename
        """
        if self._cache:
            # Return cached metadata
            return [
                {
                    "name": v["name"],
                    "description": v["description"],
                    "filename": v["filename"],
                }
                for v in self._cache.values()
            ]

        # Scan skills directory
        skills = []
        if not self._dir.exists():
            logger.warning("Skills directory not found: {}", self._dir)
            return skills

        for path in self._dir.glob("*.md"):
            skill_data = self._parse_skill_file(path)
            if skill_data:
                self._cache[path.name] = skill_data
                skills.append({
                    "name": skill_data["name"],
                    "description": skill_data["description"],
                    "filename": path.name,
                })

        return skills

    def load_skill_by_name(self, skill_name: str) -> dict | None:
        """Load full skill content by name.

        Args:
            skill_name: Name of the skill (from frontmatter)

        Returns:
            dict with name, description, content or None
        """
        # Ensure cache is populated
        if not self._cache:
            self.get_available_skills()

        # Find skill by name
        for skill_data in self._cache.values():
            if skill_data["name"] == skill_name:
                return {
                    "name": skill_data["name"],
                    "description": skill_data["description"],
                    "content": skill_data["content"],
                }

        return None

    def build_skills_summary(self) -> str | None:
        """Build a summary of available skills for agent prompt.

        Returns format:
            · SKILL latex-compile — LaTeX compilation guidance
            · SKILL data-analysis — Data processing workflow

        Returns:
            Markdown string or None if no skills available
        """
        skills = self.get_available_skills()
        if not skills:
            return None

        lines = []
        for skill in sorted(skills, key=lambda x: x["name"]):
            lines.append(f"· SKILL {skill['name']} — {skill['description']}")

        return "\n".join(lines)


class LoadSkillTool(Tool):
    """Tool for agents to load skill content on demand."""

    name = "load_skill"
    description = (
        "Load the full content of a skill by name. "
        "Use this when you need detailed guidance for a specific task."
    )

    def __init__(self, skill_loader: SkillLoader):
        super().__init__()
        self._skill_loader = skill_loader

    async def __call__(self, skill_name: str) -> dict:
        """Load skill content by name.

        Args:
            skill_name: Name of the skill to load (e.g., 'latex-compile')

        @enum skill_name: latex-compile

        Returns:
            dict with skill content or error
        """
        skill = self._skill_loader.load_skill_by_name(skill_name)
        if not skill:
            available = [s["name"] for s in self._skill_loader.get_available_skills()]
            return {
                "error": f"Skill not found: {skill_name}",
                "available_skills": available,
            }

        return {
            "name": skill["name"],
            "description": skill["description"],
            "content": skill["content"],
        }
