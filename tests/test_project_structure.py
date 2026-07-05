"""Tests for canonical project directory creation and legacy migration."""

from pathlib import Path

from autoreport.app import _copy_builtin_templates
from autoreport.core.project_structure import ensure_project_structure


def _has_exact_path(root: Path, rel: str) -> bool:
    current = root
    for part in Path(rel).parts:
        matches = [child for child in current.iterdir() if child.name == part]
        if not matches:
            return False
        current = matches[0]
    return True


def _legacy_path(*parts: str) -> str:
    return Path(*parts).as_posix()


def test_ensure_project_structure_creates_canonical_case_only(tmp_path: Path) -> None:
    ensure_project_structure(tmp_path)

    for rel in (
        "Data",
        "Data/Processed",
        "References",
        "Theory",
        "Theory/Derivations",
        "Plots",
        "Plots/Fig",
        "Plots/Scripts",
        "Outline",
        "Tex",
    ):
        assert _has_exact_path(tmp_path, rel)

    for rel in (
        "data",
        _legacy_path("data", "processed"),
        "references",
        "theory",
        "plots",
        "tex",
    ):
        assert not _has_exact_path(tmp_path, rel)


def test_ensure_project_structure_migrates_legacy_case(tmp_path: Path) -> None:
    (tmp_path / "data" / "processed").mkdir(parents=True)
    (tmp_path / "data" / "raw.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (tmp_path / "data" / "processed" / "analysis.md").write_text("ok", encoding="utf-8")
    (tmp_path / "references").mkdir()
    (tmp_path / "theory").mkdir()
    (tmp_path / "theory" / "formulas.md").write_text("F=ma", encoding="utf-8")
    (tmp_path / "theory" / "derivations").mkdir()
    (tmp_path / "theory" / "derivations" / "freefall.md").write_text("d", encoding="utf-8")
    (tmp_path / "plots" / "fig").mkdir(parents=True)
    (tmp_path / "plots" / "scripts").mkdir(parents=True)
    (tmp_path / "plots" / "fig" / "a.png").write_bytes(b"png")
    (tmp_path / "plots" / "scripts" / "plot.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "tex").mkdir()

    ensure_project_structure(tmp_path)

    assert (tmp_path / "Data" / "raw.csv").is_file()
    assert (tmp_path / "Data" / "Processed" / "analysis.md").is_file()
    assert (tmp_path / "Theory" / "formulas.md").is_file()
    assert (tmp_path / "Theory" / "Derivations" / "freefall.md").is_file()
    assert (tmp_path / "Plots" / "Fig" / "a.png").is_file()
    assert (tmp_path / "Plots" / "Scripts" / "plot.py").is_file()
    assert _has_exact_path(tmp_path, "Tex")

    for rel in (
        "data",
        _legacy_path("data", "processed"),
        "references",
        "theory",
        _legacy_path("theory", "derivations"),
        _legacy_path("plots", "fig"),
        _legacy_path("plots", "scripts"),
        "tex",
    ):
        assert not _has_exact_path(tmp_path, rel)


def test_builtin_templates_copy_to_canonical_tex(tmp_path: Path) -> None:
    ensure_project_structure(tmp_path)

    _copy_builtin_templates(tmp_path)

    assert (tmp_path / "Tex" / "main.tex").is_file()
    assert (tmp_path / "Tex" / "mpltx.cls").is_file()
    assert not _has_exact_path(tmp_path, "tex")
