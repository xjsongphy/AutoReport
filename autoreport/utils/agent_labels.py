"""Shared agent display labels for UI and queue summaries."""

from __future__ import annotations

from PyQt6.QtGui import QIcon
from ..interfaces.types import AgentType


def _get_qicon(agent_type: str, color: str | None = None, size: int = 16) -> QIcon:
    """Lazy import of icon function to avoid circular imports."""
    from ..gui.icons import get_agent_icon as get_agent_qicon
    return get_agent_qicon(agent_type, color, size)


AGENT_LABELS: dict[str, dict[str, str]] = {
    "main": {"name": "Main"},
    "data_analysis": {"name": "Data Analysis"},
    "plotting": {"name": "Plotting"},
    "theory": {"name": "Theory"},
    "report": {"name": "Report"},
    "sub": {"name": "Select"},
}


def normalize_agent_type(agent_type: AgentType | str) -> str:
    if isinstance(agent_type, AgentType):
        return agent_type.value
    return str(agent_type or "").strip()


def get_agent_icon(agent_type: AgentType | str, color: str | None = None, size: int = 16) -> QIcon:
    """Get QIcon for an agent type.

    Args:
        agent_type: The agent type
        color: Optional color override. If None, uses agent's theme color.
        size: Icon size in pixels.
    """
    return _get_qicon(agent_type, color, size)


def get_agent_name(agent_type: AgentType | str) -> str:
    agent_key = normalize_agent_type(agent_type)
    if agent_key in AGENT_LABELS:
        return AGENT_LABELS[agent_key]["name"]
    return agent_key.replace("_", " ").title() or "Agent"


def get_agent_badge(agent_type: AgentType | str) -> str:
    """Get text badge for an agent type (no icon, just name)."""
    return get_agent_name(agent_type)


def get_agent_title(agent_type: AgentType | str) -> str:
    """Get full title for an agent type."""
    agent_key = normalize_agent_type(agent_type)
    name = get_agent_name(agent_type)
    if agent_key == "sub":
        return f"{name} Agent"
    return f"{name} Agent"


def get_agent_badge_with_icon(agent_type: AgentType | str) -> tuple[QIcon, str]:
    """Get (icon, name) tuple for an agent type."""
    return get_agent_icon(agent_type), get_agent_name(agent_type)
