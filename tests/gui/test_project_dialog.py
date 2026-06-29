"""Tests for project dialog helpers, onboarding persistence, and tutorial button."""

from pathlib import Path

from PyQt6.QtWidgets import QPushButton

from autoreport.config import ConfigManager
from autoreport.core.user_settings import UserSettings
from autoreport.gui.onboarding import PreProjectGuide, show_pre_project_guide
from autoreport.gui.project_dialog import (
    ProjectDialog,
    create_project_structure,
    is_valid_project,
)


def test_is_valid_project_detects_markers(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert is_valid_project(empty) is False

    real = tmp_path / "proj"
    (real / "data").mkdir(parents=True)
    assert is_valid_project(real) is True


def test_create_project_structure_scaffolds_all_dirs(tmp_path: Path) -> None:
    proj = tmp_path / "newproj"
    create_project_structure(proj)
    # All fixed project directories must exist after scaffolding.
    assert is_valid_project(proj) is True
    for sub in ("Data", "Data/Processed", "References", "Theory", "Code", "Outline", "Tex"):
        assert (proj / sub).is_dir()


def test_skip_persists_has_seen_onboarding(qtbot, tmp_path: Path, monkeypatch) -> None:
    # Isolate user-settings storage so the test never touches the real file.
    monkeypatch.setattr(UserSettings, "STORAGE_FILE", tmp_path / "user_settings.json")

    assert UserSettings().has_seen_onboarding is False

    guide = PreProjectGuide()
    qtbot.addWidget(guide)
    guide._on_skip()

    assert UserSettings().has_seen_onboarding is True


def test_show_pre_project_guide_skips_when_already_seen(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(UserSettings, "STORAGE_FILE", tmp_path / "user_settings.json")
    UserSettings().has_seen_onboarding = True

    # Must short-circuit without raising (and without showing a modal dialog).
    assert show_pre_project_guide() is False


def test_project_dialog_has_tutorial_button(qtbot, tmp_path: Path, monkeypatch) -> None:
    # Point ConfigManager at an isolated config so the test is hermetic.
    monkeypatch.chdir(tmp_path)
    cm = ConfigManager(config_path=tmp_path / "autoreport.config.yaml")
    dialog = ProjectDialog(cm)
    qtbot.addWidget(dialog)

    tutorial_btns = dialog.findChildren(QPushButton)
    labels = [b.text() for b in tutorial_btns]
    assert "新手提示" in labels

    # The handler exists and is callable (button is wired to it in _setup_ui).
    assert callable(getattr(dialog, "_on_show_tutorial", None))
