"""Tests for prompt loader."""

import tempfile
from pathlib import Path

import pytest

from autoreport.core.prompts.loader import PromptLoader


@pytest.fixture
def agents_dir():
    d = Path(tempfile.mkdtemp())
    (d / "main_agent.md").write_text(
        "# Main Agent\n\nYou are the main agent.\n\n## Core Rules\n\nCoordinate sub-agents.\n",
        encoding="utf-8",
    )
    (d / "data_analysis_agent.md").write_text(
        "# Data Analysis Agent\n\nYou analyze data.\n\n## Instructions\n\nProcess CSV files.\n",
        encoding="utf-8",
    )
    return d


def test_load_prompt_main(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    result = loader.load_prompt("main")
    assert "main agent" in result


def test_load_prompt_data_analysis(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    result = loader.load_prompt("data_analysis")
    assert "data" in result
    assert "CSV" in result


def test_cache_hits(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    first = loader.load_prompt("main")
    second = loader.load_prompt("main")
    assert first == second
    assert first is second  # same object, cached


def test_reload_clears_cache(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    loader.load_prompt("main")
    assert "main" in loader._cache

    loader.reload()
    assert "main" not in loader._cache


def test_fallback_for_missing_file(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    result = loader.load_prompt("nonexistent_agent")
    assert "nonexistent_agent" in result


def test_fallback_built_in_types(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    for agent_type in ["main", "data_analysis", "plotting", "theory", "report"]:
        result = loader.load_prompt(agent_type)
        assert len(result) > 0


def test_load_shared_context_available(agents_dir):
    d = agents_dir
    (d / "Common.md").write_text("## Shared\n\nCommon todo policy.", encoding="utf-8")
    loader = PromptLoader(agents_dir=d)
    result = loader.load_shared_context()
    assert "Common todo policy" in result


def test_load_shared_context_missing(agents_dir):
    loader = PromptLoader(agents_dir=agents_dir)
    result = loader.load_shared_context()
    assert result is None


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