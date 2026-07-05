"""Prompt loader with progressive loading support."""

import re
from pathlib import Path
from typing import Final

from loguru import logger


class PromptLoader:
    """Load agent prompts with progressive loading support.

    Progressive loading strategy:
    - Identity: Loaded at startup (~100-200 words), defines core role
    - Full: Loaded on first agent activation, contains detailed instructions

    Each prompt file should have two sections:
    ## Identity
    Brief role definition and core responsibilities.

    ## Full Instructions
    Detailed workflow, reference handling, narrative style, output format.
    """

    # Template directory paths
    _BASE_DIR: Final = Path(__file__).parent.parent.parent / "templates"
    _AGENTS_DIR: Final = _BASE_DIR / "agents"
    _SECTION_HEADERS: Final = {
        "identity": ("## Identity", "## identity"),
        "full": ("## Full Instructions", "## full instructions", "## Full"),
    }
    _NEXT_SECTION_PATTERN: Final = re.compile(r"^##\s[^#]", re.MULTILINE)

    def __init__(self, agents_dir: Path | None = None):
        """Initialize prompt loader.

        Args:
            agents_dir: Optional custom directory for agent templates.
                       Defaults to autoreport/templates/agents/.
        """
        self._agents_dir = Path(agents_dir) if agents_dir else self._AGENTS_DIR
        self._cache: dict[str, dict[str, str]] = {}
        self._shared_context: str | None = None

    def load_identity(self, agent_type: str) -> str:
        """Load identity section of agent prompt.

        Args:
            agent_type: Agent type (e.g., "main", "data_analysis", "plotting",
                        "theory", "report")

        Returns:
            Identity section content.

        Raises:
            FileNotFoundError: If prompt file not found.
            ValueError: If identity section not found in file.
        """
        return self._load_section(agent_type, "identity")

    def load_full(self, agent_type: str) -> str:
        """Load full instructions section of agent prompt.

        Args:
            agent_type: Agent type (e.g., "main", "data_analysis", "plotting",
                        "theory", "report")

        Returns:
            Full instructions section content.

        Raises:
            FileNotFoundError: If prompt file not found.
            ValueError: If full section not found in file.
        """
        return self._load_section(agent_type, "full")

    def load_complete(self, agent_type: str) -> str:
        """Load complete prompt (identity + full instructions).

        Args:
            agent_type: Agent type (e.g., "main", "data_analysis", "plotting",
                        "theory", "report")

        Returns:
            Complete prompt content with both sections.
        """
        identity = self.load_identity(agent_type)
        full = self.load_full(agent_type)
        return f"{identity}\n\n{full}"

    def load_shared_context(self) -> str | None:
        """Load shared prompts for all agents.

        Returns:
            Shared context content, or None if file not found.
        """
        if self._shared_context is not None:
            return self._shared_context

        path = self._AGENTS_DIR / "Common.md"
        if not path.exists():
            logger.debug("Shared context file not found: {}", path)
            return None

        content = path.read_text(encoding="utf-8").strip()
        self._shared_context = content
        return content

    def _load_section(self, agent_type: str, section: str) -> str:
        """Load a specific section from agent prompt file.

        Args:
            agent_type: Agent type identifier.
            section: Section name ("identity" or "full").

        Returns:
            Section content.

        Raises:
            FileNotFoundError: If prompt file not found.
            ValueError: If section not found in file.
        """
        # Check cache first
        cached = self._cache.get(agent_type)
        if cached and section in cached:
            return cached[section]

        # Map agent_type to filename
        filename = self._get_filename(agent_type)
        filepath = self._agents_dir / filename

        if not filepath.exists():
            logger.warning("Prompt file not found: {}, using fallback", filepath)
            return self._get_fallback_prompt(agent_type)

        # Read once and cache both sections to avoid duplicate disk reads/parsing.
        content = filepath.read_text(encoding="utf-8")
        identity = self._extract_section(content, "identity", filepath)
        full = self._extract_section(content, "full", filepath)
        self._cache[agent_type] = {"identity": identity, "full": full}
        return self._cache[agent_type][section]

    def _get_filename(self, agent_type: str) -> str:
        """Map agent type to filename.

        Args:
            agent_type: Agent type identifier.

        Returns:
            Filename for the agent prompt.
        """
        # Map common variations to standardized filenames
        mapping = {
            "main": "main_agent.md",
            "data_analysis": "data_analysis_agent.md",
            "plotting": "plotting_agent.md",
            "theory": "theory_agent.md",
            "report": "report_agent.md",
        }

        # Handle underscores and hyphens
        normalized = agent_type.lower().replace("-", "_").replace(" ", "_")

        return mapping.get(normalized, f"{normalized}_agent.md")

    def _extract_section(self, content: str, section: str, filepath: Path | None = None) -> str:
        """Extract a section from markdown content.

        Args:
            content: Full markdown content.
            section: Section name to extract.
            filepath: Optional file path for logging.

        Returns:
            Section content without the header.

        Raises:
            ValueError: If section not found.
        """
        headers = self._SECTION_HEADERS.get(section, ())
        if not headers:
            raise ValueError(f"Unknown section: {section}")

        # Find section start
        start_idx = -1
        matched_header = None
        for header in headers:
            idx = content.find(header)
            if idx != -1:
                start_idx = idx + len(header)
                matched_header = header
                break

        if start_idx == -1:
            # Section not found — return full file content as fallback
            logger.debug("Section '{}' not found in '{}', using full content", section, filepath)
            return content.strip()

        # Find next major section header (## level, not ###)
        search_start = start_idx
        next_header_idx = len(content)

        for match in self._NEXT_SECTION_PATTERN.finditer(content, search_start):
            idx = match.start()
            # Make sure it's not our matched header
            header_at_idx = content[idx:idx + len(matched_header)] if idx + len(matched_header) <= len(content) else ""
            if header_at_idx != matched_header:
                next_header_idx = idx
                break

        # Extract section content
        section_content = content[start_idx:next_header_idx].strip()

        return section_content

    def _get_fallback_prompt(self, agent_type: str) -> str:
        """Get fallback prompt when file not found.

        Args:
            agent_type: Agent type identifier.

        Returns:
            Fallback prompt content.
        """
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
        """Clear cache and reload all prompts.

        Useful for development or when prompts are modified at runtime.
        """
        self._cache.clear()
        logger.info("Prompt cache cleared")
