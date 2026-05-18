from pathlib import Path

from PyQt6.QtWidgets import QMessageBox

from autoreport.gui.theme import get_theme_colors
from autoreport.gui.widgets.preview import PreviewWidget


def test_clicking_unified_tab_switches_active_file(qtbot, tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)

    widget.load_file(first)
    widget.load_file(second)

    assert widget.current_file == second.resolve()

    widget._unified_tab_bar.setCurrentIndex(0)

    assert widget.current_file == first.resolve()
    assert widget._panels[0].active_path() == first.resolve()


def test_loading_existing_file_switches_back_to_its_tab(qtbot, tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)

    widget.load_file(first)
    widget.load_file(second)
    widget.load_file(first)

    assert widget.current_file == first.resolve()
    assert widget._unified_tab_bar.currentIndex() == 0
    assert widget._unified_tab_bar.tabData(0) == str(first.resolve())


def test_unselected_unified_tabs_use_inactive_background(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)

    colors = get_theme_colors()

    assert f'background-color: {colors["tab_inactive_bg"]};' in widget.styleSheet()


def test_selected_unified_tabs_use_active_background(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)

    colors = get_theme_colors()

    assert f'background-color: {colors["tab_active_bg"]};' in widget.styleSheet()


def test_file_action_buttons_follow_active_suffix(qtbot, tmp_path: Path) -> None:
    py_file = tmp_path / "run.py"
    tex_file = tmp_path / "paper.tex"
    txt_file = tmp_path / "note.txt"
    py_file.write_text("print('x')", encoding="utf-8")
    tex_file.write_text("\\documentclass{article}", encoding="utf-8")
    txt_file.write_text("hello", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)

    widget.load_file(py_file)
    assert widget._active_action_kind == "python"
    assert widget._run_button.isVisible()
    assert not widget._preview_button.isVisible()

    widget.load_file(tex_file)
    assert widget._active_action_kind == "tex"
    assert widget._run_button.isVisible()
    assert widget._preview_button.isVisible()

    widget.load_file(txt_file)
    assert widget._active_action_kind == ""
    assert not widget._run_button.isVisible()
    assert not widget._preview_button.isVisible()


def test_save_current_file_persists_and_clears_modified(qtbot, tmp_path: Path) -> None:
    text_file = tmp_path / "note.txt"
    text_file.write_text("old", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(text_file)

    key = str(text_file.resolve())
    panel = widget._panels[0]
    state = panel._tabs[key]
    state.viewer.setText("new content")
    qtbot.wait(10)
    assert state.modified

    assert widget.save_current_file()
    assert text_file.read_text(encoding="utf-8") == "new content"
    assert not state.modified


def test_preview_clicked_without_pdf_shows_information(qtbot, tmp_path: Path, monkeypatch) -> None:
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text("\\documentclass{article}", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(tex_file)

    called = {"count": 0}

    def _fake_info(*args, **kwargs):
        called["count"] += 1
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", _fake_info)
    widget._on_preview_clicked()

    assert called["count"] == 1
