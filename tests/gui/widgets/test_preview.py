from pathlib import Path

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
