"""Prompt loader — loads complete agent prompts with shared context."""

import re
from pathlib import Path
from typing import Final

from loguru import logger


class PromptLoader:
    """Load agent prompts.

    Each agent prompt file is a single Markdown file.  The full content is
    loaded and returned every time — there is no identity/full split.
    Shared context (Common.md) and per-agent skill summaries are assembled
    by the caller, not here.
    """

    # Template directory paths
    _BASE_DIR: Final = Path(__file__).parent.parent.parent / "templates"
    _AGENTS_DIR: Final = _BASE_DIR / "agents"

    def __init__(self, agents_dir: Path | None = None):
        """Initialize prompt loader.

        Args:
            agents_dir: Optional custom directory for agent templates.
                       Defaults to autoreport/templates/agents/.
        """
        self._agents_dir = Path(agents_dir) if agents_dir else self._AGENTS_DIR
        self._cache: dict[str, str] = {}

    def load_prompt(self, agent_type: str) -> str:
        """Load complete agent prompt.

        Args:
            agent_type: Agent type (e.g., "main", "data_analysis").

        Returns:
            Complete prompt file content.

        Raises:
            FileNotFoundError: If prompt file not found.
        """
        if agent_type in self._cache:
            return self._cache[agent_type]

        filename = self._get_filename(agent_type)
        filepath = self._agents_dir / filename

        if not filepath.exists():
            logger.warning("Prompt file not found: {}, using fallback", filepath)
            prompt = self._get_fallback_prompt(agent_type)
        else:
            content = filepath.read_text(encoding="utf-8")
            prompt = content.strip()

        self._cache[agent_type] = prompt
        return prompt

    def load_shared_context(self) -> str | None:
        """Load shared prompts for all agents.

        Returns:
            Shared context content, or None if file not found.
        """
        path = self._agents_dir / "Common.md"
        if not path.exists():
            logger.debug("Shared context file not found: {}", path)
            return None

        content = path.read_text(encoding="utf-8").strip()
        return content or None

    def _get_filename(self, agent_type: str) -> str:
        normalized = agent_type.lower().replace("-", "_").replace(" ", "_")
        mapping = {
            "main": "main_agent.md",
            "data_analysis": "data_analysis_agent.md",
            "plotting": "plotting_agent.md",
            "theory": "theory_agent.md",
            "report": "report_agent.md",
        }
        return mapping.get(normalized, f"{normalized}_agent.md")

    def _get_fallback_prompt(self, agent_type: str) -> str:
        fallbacks = {
            "main": "You are the Main Agent for an automated physics experiment report writing system. Coordinate sub-agents and communicate with users.",
            "data_analysis": "You are the Data Analysis Agent. Read experimental data, process it, and generate analysis results.",
            "plotting": "You are the Plotting Agent. Create data visualizations using matplotlib.",
            "theory": "You are the Theory Agent. Analyze reference materials and provide theoretical derivations.",
            "report": "You are the Report Agent. Write LaTeX reports and compile them to PDF.",
        }
        return fallbacks.get(
            agent_type.lower(),
            f"You are a {agent_type} agent for the AutoReport system.",
        )

    def reload(self) -> None:
        """Clear cache — useful when prompts are modified at runtime."""
        self._cache.clear()
        logger.info("Prompt cache cleared")