"""Tests for SkillLoader (now in autoreport.core.tools.skill_tool)."""

import pytest
from pathlib import Path

from autoreport.core.tools.skill_tool import SkillLoader


def _write_skill(path: Path, name: str, description: str, body: str = "") -> None:
    """Write a skill file with YAML frontmatter (current SkillLoader format)."""
    content = f"---\nname: {name}\ndescription: {description}\n---\n{body}"
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def skills_dir(tmp_path):
    """Create a temp skills directory with sample skill files (frontmatter format)."""
    d = tmp_path / "skills"
    d.mkdir()
    _write_skill(
        d / "latex-compile.md",
        "latex-compile",
        "LaTeX Compile",
        body="# LaTeX Compile\n\nCompile LaTeX files.",
    )
    _write_skill(
        d / "data-analysis.md",
        "data-analysis",
        "Data Analysis",
        body="# Data Analysis\n\nAnalyze data.",
    )
    return d


class TestSkillLoader:
    def test_parse_skill_file(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        parsed = loader._parse_skill_file(skills_dir / "latex-compile.md")
        assert parsed is not None
        assert parsed["name"] == "latex-compile"
        assert parsed["description"] == "LaTeX Compile"
        assert "LaTeX Compile" in parsed["content"]

    def test_get_available_skills_lists_all(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        skills = loader.get_available_skills()
        names = {s["name"] for s in skills}
        assert names == {"latex-compile", "data-analysis"}
        for s in skills:
            assert "filename" in s
            assert "description" in s

    def test_get_available_skills_caches(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        first = loader.get_available_skills()
        # Second call should return cached metadata (no re-scan)
        second = loader.get_available_skills()
        assert {s["name"] for s in first} == {s["name"] for s in second}

    def test_load_skill_by_name(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        skill = loader.load_skill_by_name("latex-compile")
        assert skill is not None
        assert skill["name"] == "latex-compile"
        assert "LaTeX Compile" in skill["content"]

    def test_load_missing_skill_returns_none(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        assert loader.load_skill_by_name("nonexistent") is None

    def test_get_available_skills_missing_dir(self, tmp_path):
        loader = SkillLoader(skills_dir=tmp_path / "does_not_exist")
        assert loader.get_available_skills() == []

    def test_parse_skill_file_missing_frontmatter(self, tmp_path):
        """A file without frontmatter fails to parse."""
        f = tmp_path / "no_frontmatter.md"
        f.write_text("# just a heading\n", encoding="utf-8")
        loader = SkillLoader(skills_dir=tmp_path)
        assert loader._parse_skill_file(f) is None

    def test_build_skills_summary_with_skills(self, skills_dir):
        loader = SkillLoader(skills_dir=skills_dir)
        summary = loader.build_skills_summary()
        assert summary is not None
        assert "latex-compile" in summary
        assert "data-analysis" in summary
        assert "LaTeX Compile" in summary

    def test_build_skills_summary_no_skills(self, tmp_path):
        empty_dir = tmp_path / "empty_skills"
        empty_dir.mkdir()
        loader = SkillLoader(skills_dir=empty_dir)
        assert loader.build_skills_summary() is None

    def test_load_skill_by_name_populates_cache(self, skills_dir):
        """Loading by name before listing should still work (populates cache)."""
        loader = SkillLoader(skills_dir=skills_dir)
        skill = loader.load_skill_by_name("data-analysis")
        assert skill is not None
        assert "Data Analysis" in skill["content"]
