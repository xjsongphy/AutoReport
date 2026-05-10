"""Shared agent display labels for UI and queue summaries."""

from __future__ import annotations

from ..interfaces.types import AgentType


AGENT_LABELS: dict[str, dict[str, str]] = {
    "main": {"icon": "[总]", "name": "Main"},
    "data_analysis": {"icon": "[析]", "name": "Data Analysis"},
    "plotting": {"icon": "[图]", "name": "Plotting"},
    "theory": {"icon": "[笔]", "name": "Theory"},
    "report": {"icon": "[稿]", "name": "Report"},
    "sub": {"icon": "[选]", "name": "Select"},
}


def normalize_agent_type(agent_type: AgentType | str) -> str:
    if isinstance(agent_type, AgentType):
        return agent_type.value
    return str(agent_type or "").strip()


def get_agent_icon(agent_type: AgentType | str) -> str:
    agent_key = normalize_agent_type(agent_type)
    return AGENT_LABELS.get(agent_key, {}).get("icon", "[?]")


def get_agent_name(agent_type: AgentType | str) -> str:
    agent_key = normalize_agent_type(agent_type)
    if agent_key in AGENT_LABELS:
        return AGENT_LABELS[agent_key]["name"]
    return agent_key.replace("_", " ").title() or "Agent"


def get_agent_badge(agent_type: AgentType | str) -> str:
    return f"{get_agent_icon(agent_type)} {get_agent_name(agent_type)}"


def get_agent_title(agent_type: AgentType | str) -> str:
    agent_key = normalize_agent_type(agent_type)
    if agent_key == "sub":
        return f"{get_agent_badge(agent_type)} Agent"
    return f"{get_agent_badge(agent_type)} Agent"
