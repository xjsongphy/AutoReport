"""Tests for fuzzy file search."""

import tempfile
from pathlib import Path

import pytest

from autoreport.core.file_search import FileMatch, FileSearchManager, FuzzyMatcher


# ── FuzzyMatcher tests ──────────────────────────────────────────────────


class TestFuzzyMatcher:
    def test_exact_match(self):
        score, indices = FuzzyMatcher.match("test.txt", "test.txt")
        assert score == 1000

    def test_startswith_match(self):
        score, indices = FuzzyMatcher.match("test_file.csv", "test")
        assert score == 800

    def test_contains_match(self):
        score, indices = FuzzyMatcher.match("my_test_file.csv", "test")
        assert score == 600

    def test_fuzzy_match(self):
        score, indices = FuzzyMatcher.match("test_file.csv", "tst")
        assert score > 0
        assert indices is not None

    def test_no_match(self):
        score, indices = FuzzyMatcher.match("abc.txt", "xyz")
        assert score == -1
        assert indices is None

    def test_empty_query(self):
        score, indices = FuzzyMatcher.match("test.txt", "")
        assert score == 0

    def test_case_insensitive(self):
        score, indices = FuzzyMatcher.match("Test_File.csv", "test")
        assert score == 800

    def test_longer_query_than_text(self):
        score, indices = FuzzyMatcher.match("ab", "abcdef")
        assert score == -1

    def test_consecutive_match_higher_score(self):
        """Consecutive character matches should score higher than scattered."""
        score_consec, _ = FuzzyMatcher.match("abc", "abc")
        score_scatter, _ = FuzzyMatcher.match("a_b_c", "abc")
        assert score_consec > score_scatter


# ── FileSearchManager tests ─────────────────────────────────────────────


@pytest.fixture
def search_workspace():
    ws = Path(tempfile.mkdtemp())
    (ws / "data").mkdir()
    (ws / "code").mkdir()
    (ws / "data" / "experiment_results.csv").write_text("data")
    (ws / "data" / "analysis_output.json").write_text("{}")
    (ws / "code" / "plot_temperature.py").write_text("code")
    (ws / "code" / "plot_pressure.py").write_text("code")
    (ws / "report.tex").write_text("latex")
    yield ws
    import shutil
    shutil.rmtree(ws, ignore_errors=True)


def test_build_file_cache(search_workspace):
    mgr = FileSearchManager(search_workspace)
    cache = mgr._build_file_cache()
    names = {f.name for f in cache}
    assert "experiment_results.csv" in names
    assert "plot_temperature.py" in names
    assert "report.tex" in names


def test_file_cache_ignores_pycache(search_workspace):
    pycache = search_workspace / "__pycache__"
    pycache.mkdir()
    (pycache / "module.cpython-312.pyc").write_bytes(b"\x00")

    mgr = FileSearchManager(search_workspace)
    cache = mgr._build_file_cache()
    names = {f.name for f in cache}
    assert "module.cpython-312.pyc" not in names


def test_file_cache_ignores_git(search_workspace):
    git_dir = search_workspace / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main")

    mgr = FileSearchManager(search_workspace)
    cache = mgr._build_file_cache()
    names = {f.name for f in cache}
    assert "HEAD" not in names


def test_do_search_finds_files(search_workspace):
    mgr = FileSearchManager(search_workspace)
    results = mgr._do_search("plot")
    names = [r.path.name for r in results]
    assert "plot_temperature.py" in names
    assert "plot_pressure.py" in names


def test_do_search_empty_query(search_workspace):
    mgr = FileSearchManager(search_workspace)
    results = mgr._do_search("")
    assert results == []


def test_do_search_no_results(search_workspace):
    mgr = FileSearchManager(search_workspace)
    results = mgr._do_search("zzzznonexistent")
    assert results == []


def test_do_search_sorted_by_score(search_workspace):
    mgr = FileSearchManager(search_workspace)
    results = mgr._do_search("plot")
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_invalidate_cache(search_workspace):
    mgr = FileSearchManager(search_workspace)
    # _build_file_cache returns the list but doesn't set _file_cache
    # _file_cache is set by _do_search
    mgr._file_cache = mgr._build_file_cache()
    assert mgr._file_cache is not None

    mgr.invalidate_cache()
    assert mgr._file_cache is None


def test_search_limit_50(search_workspace):
    for i in range(60):
        (search_workspace / f"file_{i:03d}.txt").write_text(f"content {i}")

    mgr = FileSearchManager(search_workspace)
    results = mgr._do_search("file")
    assert len(results) <= 50


def test_file_match_dataclass():
    fm = FileMatch(path=Path("/test/file.txt"), score=100, indices=[0, 1, 2])
    assert fm.score == 100
    assert len(fm.indices) == 3
