"""Tests for prompt loader with progressive loading."""

import tempfile
from pathlib import Path

import pytest

from autoreport.core.prompts.loader import PromptLoader


@pytest.fixture
def agents_dir():
    d = Path(tempfile.mkdtemp())
    (d / "main_agent.md").write_text(
        "## Identity\nYou are the main agent.\n\n## Full Instructions\nDetailed main instructions.\n",
        encoding="utf-8",
    )
    (d / "data_analysis_agent.md").write_text(
        "## Identity\nYou analyze data.\n\n## Full Instructions\nProcess CSV files.\n",
        encoding="utf-8",
    )
    return d


def test_load_identity(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    result = loader.load_identity("main")
    assert "main agent" in result


def test_load_full(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    result = loader.load_full("main")
    assert "Detailed main instructions" in result


def test_load_complete(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    result = loader.load_complete("main")
    assert "main agent" in result
    assert "Detailed main instructions" in result


def test_cache_hits(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    first = loader.load_identity("main")
    second = loader.load_identity("main")
    assert first == second


def test_reload_clears_cache(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    loader.load_identity("main")
    assert "main" in loader._cache

    loader.reload()
    assert "main" not in loader._cache


def test_fallback_for_missing_file(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    result = loader.load_identity("nonexistent_agent")
    assert "nonexistent_agent" in result


def test_fallback_built_in_types(agents_dir):
    """Built-in agent types should have fallback prompts."""
    loader = PromptLoader(agents_dir=agents_dir)
    for agent_type in ["main", "data_analysis", "plotting", "theory", "report"]:
        result = loader.load_identity(agent_type)
        assert len(result) > 0


def test_extract_section(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    content = (agents_dir / "main_agent.md").read_text()
    section = loader._extract_section(content, "identity")
    assert "main agent" in section


def test_extract_section_not_found(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    content = "No sections here"
    section = loader._extract_section(content, "identity")
    assert section == ""


def test_get_filename_mapping(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    assert loader._get_filename("main") == "main_agent.md"
    assert loader._get_filename("data_analysis") == "data_analysis_agent.md"
    assert loader._get_filename("plotting") == "plotting_agent.md"


def test_get_filename_unknown_type(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    assert loader._get_filename("custom") == "custom_agent.md"


def test_get_filename_normalizes_hyphens(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    assert loader._get_filename("data-analysis") == "data_analysis_agent.md"
