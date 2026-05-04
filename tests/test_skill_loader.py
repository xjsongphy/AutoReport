"""Tests for SkillLoader."""

import pytest
from pathlib import Path

from autoreport.core.skills import SkillLoader, AGENT_SKILLS


@pytest.fixture
def skills_dir(tmp_path):
    """Create a temp skills directory with sample skill files."""
    d = tmp_path / "skills"
    d.mkdir()
    (d / "latex-compile.md").write_text("# LaTeX Compile\n\nCompile LaTeX files.", encoding="utf-8")
    (d / "data-analysis.md").write_text("# Data Analysis\n\nAnalyze data.", encoding="utf-8")
    return d


class TestSkillLoader:
    def test_load_skill_from_file(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        content = loader._load_skill("latex-compile.md")
        assert content is not None
        assert "LaTeX Compile" in content

    def test_load_skill_caches(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        c1 = loader._load_skill("latex-compile.md")
        c2 = loader._load_skill("latex-compile.md")
        assert c1 is c2

    def test_load_missing_skill_returns_none(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        assert loader._load_skill("nonexistent.md") is None

    def test_get_skills_for_report_agent(self):
        assert "latex-compile.md" in AGENT_SKILLS.get("report", [])

    def test_get_skills_for_agent_without_skills(self):
        assert AGENT_SKILLS.get("main", []) == []
        assert AGENT_SKILLS.get("data_analysis", []) == []

    def test_build_skills_section_with_skills(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        section = loader.build_skills_section("report")
        assert section is not None
        assert "Available Skills" in section
        assert "LaTeX Compile" in section

    def test_build_skills_section_no_skills_assigned(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        assert loader.build_skills_section("main") is None

    def test_build_skills_section_skill_file_missing(self, tmp_path):
        empty_dir = tmp_path / "empty_skills"
        empty_dir.mkdir()
        loader = SkillLoader(skills_dir=empty_dir)
        # report has skill assigned but file doesn't exist
        section = loader.build_skills_section("report")
        assert section is None

    def test_reload_clears_cache(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        loader._load_skill("latex-compile.md")
        assert "latex-compile.md" in loader._cache
        loader.reload()
        assert len(loader._cache) == 0

    def test_multiple_skills_per_agent(self, skills_dir):
        """Verify multi-skill agents build sections from all skills."""
        # Override AGENT_SKILLS temporarily
        from autoreport.core import skills as skills_mod
        original = skills_mod.AGENT_SKILLS.copy()
        skills_mod.AGENT_SKILLS["test_agent"] = ["latex-compile.md", "data-analysis.md"]
        try:
            loader = SkillLoader(skills_dir=skills_dir)
            section = loader.build_skills_section("test_agent")
            assert section is not None
            assert "LaTeX Compile" in section
            assert "Data Analysis" in section
        finally:
            skills_mod.AGENT_SKILLS = original
