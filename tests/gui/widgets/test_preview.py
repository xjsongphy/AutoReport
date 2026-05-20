from pathlib import Path

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel, QTabBar, QPushButton
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


def test_editor_selection_emits_selected_line_context(qtbot, tmp_path: Path) -> None:
    text_file = tmp_path / "note.txt"
    text_file.write_text("first\nsecond\nthird", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(text_file)

    viewer = widget._panels[0].get_active_viewer()
    with qtbot.waitSignal(widget.selection_changed, timeout=1000) as blocker:
        viewer.setSelection(0, 0, 1, 6)

    assert blocker.args[0] == "note.txt"
    assert blocker.args[2] == 1
    assert blocker.args[3] == 2


def test_dirty_unified_tab_affordance_only_turns_close_on_button_hover(qtbot, tmp_path: Path) -> None:
    text_file = tmp_path / "note.txt"
    text_file.write_text("old", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(text_file)

    key = str(text_file.resolve())
    state = widget._panels[0]._tabs[key]
    state.viewer.setText("changed")
    qtbot.wait(10)
    widget._sync_tabs_from_panels()

    host = widget._unified_tab_bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
    button = host.findChild(QPushButton)

    assert button is not None
    assert button.text() == "●"
    assert button.cursor().shape() == Qt.CursorShape.PointingHandCursor

    tab_center = widget._unified_tab_bar.tabRect(0).center()
    QApplication.sendEvent(
        widget._unified_tab_bar,
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(tab_center),
            QPointF(widget._unified_tab_bar.mapToGlobal(tab_center)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    host = widget._unified_tab_bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
    button = host.findChild(QPushButton)
    assert button is not None
    assert button.text() == "●"

    QApplication.sendEvent(button, QEvent(QEvent.Type.Enter))
    assert button.text() == "✕"

    QApplication.sendEvent(button, QEvent(QEvent.Type.Leave))
    assert button.text() == "●"


def test_open_tab_updates_when_file_path_changes(qtbot, tmp_path: Path) -> None:
    old_file = tmp_path / "old.txt"
    new_file = tmp_path / "renamed.txt"
    old_file.write_text("content", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(old_file)
    old_file.rename(new_file)

    widget.update_open_path(old_file, new_file)

    assert widget._unified_tab_bar.tabData(0) == str(new_file.resolve())
    assert widget._unified_tab_bar.tabText(0) == "renamed.txt"
    assert widget.current_file == new_file.resolve()


def test_open_tabs_are_persisted_and_restored_with_missing_badge(qtbot, tmp_path: Path) -> None:
    existing = tmp_path / "existing.txt"
    missing = tmp_path / "missing.txt"
    existing.write_text("content", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(existing)
    widget.load_file(missing)
    widget.save_open_tabs()

    restored = PreviewWidget(tmp_path)
    qtbot.addWidget(restored)
    restored.restore_open_tabs()

    assert restored._unified_tab_bar.count() == 2
    assert restored._unified_tab_bar.tabText(1) == "missing.txt"
    host = restored._unified_tab_bar.tabButton(1, QTabBar.ButtonPosition.RightSide)
    assert host.findChild(QPushButton) is not None
    assert any(label.text() == "D" for label in host.findChildren(QLabel))


def test_duplicate_tab_names_show_relative_parent_path(qtbot, tmp_path: Path) -> None:
    first = tmp_path / "first" / "note.txt"
    second = tmp_path / "second" / "note.txt"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(first)
    widget.load_file(second)

    hosts = [
        widget._unified_tab_bar.tabButton(i, QTabBar.ButtonPosition.RightSide)
        for i in range(widget._unified_tab_bar.count())
    ]
    labels = [label.text() for host in hosts for label in host.findChildren(QLabel)]

    assert "first" in labels
    assert "second" in labels
