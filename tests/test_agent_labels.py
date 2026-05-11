"""Tests for agent_labels utility functions."""

from autoreport.interfaces.types import AgentType
from autoreport.utils.agent_labels import (
    AGENT_LABELS,
    get_agent_badge,
    get_agent_name,
    get_agent_title,
    normalize_agent_type,
)


class TestNormalizeAgentType:
    """Tests for normalize_agent_type()."""

    def test_with_agent_type_enum(self):
        result = normalize_agent_type(AgentType.MAIN)
        assert result == "main"

    def test_with_agent_type_enum_data_analysis(self):
        result = normalize_agent_type(AgentType.DATA_ANALYSIS)
        assert result == "data_analysis"

    def test_with_string(self):
        result = normalize_agent_type("plotting")
        assert result == "plotting"

    def test_with_none_returns_empty(self):
        result = normalize_agent_type(None)
        assert result == ""

    def test_with_empty_string(self):
        result = normalize_agent_type("")
        assert result == ""

    def test_with_padded_string(self):
        result = normalize_agent_type("  theory  ")
        assert result == "theory"


class TestGetAgentName:
    """Tests for get_agent_name()."""

    def test_main(self):
        assert get_agent_name(AgentType.MAIN) == "Main"

    def test_data_analysis(self):
        assert get_agent_name(AgentType.DATA_ANALYSIS) == "Data Analysis"

    def test_plotting(self):
        assert get_agent_name(AgentType.PLOTTING) == "Plotting"

    def test_theory(self):
        assert get_agent_name(AgentType.THEORY) == "Theory"

    def test_report(self):
        assert get_agent_name(AgentType.REPORT) == "Report"

    def test_unknown_returns_title_cased(self):
        assert get_agent_name("some_new_agent") == "Some New Agent"

    def test_empty_returns_agent(self):
        assert get_agent_name("") == "Agent"

    def test_sub_returns_select(self):
        assert get_agent_name("sub") == "Select"


class TestGetAgentBadge:
    """Tests for get_agent_badge() — should be alias for get_agent_name."""

    def test_badge_equals_name_main(self):
        assert get_agent_badge(AgentType.MAIN) == get_agent_name(AgentType.MAIN)

    def test_badge_equals_name_data_analysis(self):
        assert get_agent_badge(AgentType.DATA_ANALYSIS) == get_agent_name(
            AgentType.DATA_ANALYSIS
        )

    def test_badge_equals_name_plotting(self):
        assert get_agent_badge(AgentType.PLOTTING) == get_agent_name(AgentType.PLOTTING)

    def test_badge_equals_name_theory(self):
        assert get_agent_badge(AgentType.THEORY) == get_agent_name(AgentType.THEORY)

    def test_badge_equals_name_report(self):
        assert get_agent_badge(AgentType.REPORT) == get_agent_name(AgentType.REPORT)


class TestGetAgentTitle:
    """Tests for get_agent_title()."""

    def test_main_title(self):
        assert get_agent_title(AgentType.MAIN) == "Main Agent"

    def test_data_analysis_title(self):
        assert get_agent_title(AgentType.DATA_ANALYSIS) == "Data Analysis Agent"

    def test_plotting_title(self):
        assert get_agent_title(AgentType.PLOTTING) == "Plotting Agent"

    def test_theory_title(self):
        assert get_agent_title(AgentType.THEORY) == "Theory Agent"

    def test_report_title(self):
        assert get_agent_title(AgentType.REPORT) == "Report Agent"

    def test_sub_returns_select_agent(self):
        assert get_agent_title("sub") == "Select Agent"

    def test_unknown_returns_agent_format(self):
        assert get_agent_title("custom_type") == "Custom Type Agent"


class TestAgentLabelsDict:
    """Tests for AGENT_LABELS completeness."""

    def test_has_all_agent_type_values(self):
        for agent_type in AgentType:
            assert agent_type.value in AGENT_LABELS, (
                f"Missing {agent_type.value} in AGENT_LABELS"
            )

    def test_has_sub_entry(self):
        assert "sub" in AGENT_LABELS

    def test_all_entries_have_name(self):
        for key, entry in AGENT_LABELS.items():
            assert "name" in entry, f"Missing 'name' key for {key}"
            assert isinstance(entry["name"], str)
            assert len(entry["name"]) > 0
