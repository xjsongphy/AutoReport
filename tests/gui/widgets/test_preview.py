import json
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QApplication, QLabel, QTabBar, QPushButton
from PyQt6.QtWidgets import QMessageBox

from autoreport.gui.theme import get_theme_colors
from autoreport.gui.widgets.preview import PreviewWidget, _EmbeddedImageLabel


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


def test_unselected_unified_tabs_use_surface_background(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)

    colors = get_theme_colors()

    assert f'background-color: {colors["surface"]};' in widget.styleSheet()


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


def test_file_action_button_tooltips_are_chinese(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)

    assert widget._run_button._compact_tooltip_filter._text == "编译 / 运行当前文件"
    assert widget._preview_button._compact_tooltip_filter._text == "预览当前文件"
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


def test_dirty_unified_tab_shows_dot_and_close_for_unselected_tab(qtbot, tmp_path: Path) -> None:
    text_file = tmp_path / "note.txt"
    text_file.write_text("old", encoding="utf-8")
    other = tmp_path / "other.txt"
    other.write_text("other", encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(text_file)
    widget.load_file(other)

    key = str(text_file.resolve())
    state = widget._panels[0]._tabs[key]
    state.viewer.setText("changed")
    qtbot.wait(10)
    widget._sync_tabs_from_panels()
    widget._unified_tab_bar.setCurrentIndex(1)

    host = widget._unified_tab_bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
    buttons = host.findChildren(QPushButton)
    texts = [b.text() for b in buttons]

    assert "•" in texts
    assert "✕" in texts


def test_close_modified_tab_cancel_keeps_tab_open(qtbot, tmp_path: Path, monkeypatch) -> None:
    text_file = tmp_path / "note.txt"
    text_file.write_text("old", encoding="utf-8")
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(text_file)

    key = str(text_file.resolve())
    state = widget._panels[0]._tabs[key]
    state.viewer.setText("changed")
    qtbot.wait(10)

    monkeypatch.setattr(
        PreviewWidget,
        "_confirm_close_modified_tab",
        lambda self, path: QMessageBox.StandardButton.Cancel,
    )
    assert widget._on_unified_tab_close(0) is False
    assert widget._unified_tab_bar.count() == 1


def test_close_modified_tab_save_then_close(qtbot, tmp_path: Path, monkeypatch) -> None:
    text_file = tmp_path / "note.txt"
    text_file.write_text("old", encoding="utf-8")
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.load_file(text_file)

    key = str(text_file.resolve())
    state = widget._panels[0]._tabs[key]
    state.viewer.setText("changed")
    qtbot.wait(10)

    monkeypatch.setattr(
        PreviewWidget,
        "_confirm_close_modified_tab",
        lambda self, path: QMessageBox.StandardButton.Save,
    )
    assert widget._on_unified_tab_close(0) is True
    assert widget._unified_tab_bar.count() == 0
    assert text_file.read_text(encoding="utf-8") == "changed"


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


def test_unified_tab_bar_disables_scroll_buttons(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    assert widget._unified_tab_bar.usesScrollButtons() is False


def test_tab_scrollbar_shows_on_hover_and_hides_on_leave(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)

    assert (
        widget._tab_scroll.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    enter_event = QEvent(QEvent.Type.Enter)
    leave_event = QEvent(QEvent.Type.Leave)
    QApplication.sendEvent(widget._tab_scroll.viewport(), enter_event)
    qtbot.wait(10)
    assert (
        widget._tab_scroll.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    QApplication.sendEvent(widget._tab_scroll.viewport(), leave_event)
    qtbot.wait(10)
    assert (
        widget._tab_scroll.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_vertical_wheel_on_tab_bar_scrolls_tabs_instead_of_switching(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.resize(260, 300)
    widget.show()
    qtbot.waitExposed(widget)

    files = []
    for i in range(6):
        path = tmp_path / f"file_{i}.txt"
        path.write_text(f"content {i}", encoding="utf-8")
        files.append(path)
        widget.load_file(path)

    widget._unified_tab_bar.setCurrentIndex(2)
    before = widget._unified_tab_bar.currentIndex()
    before_scroll = widget._tab_scroll.horizontalScrollBar().value()

    center = widget._unified_tab_bar.rect().center()
    event = QWheelEvent(
        QPointF(center),
        QPointF(widget._unified_tab_bar.mapToGlobal(center)),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(widget._unified_tab_bar, event)

    assert widget._unified_tab_bar.currentIndex() == before
    assert widget._tab_scroll.horizontalScrollBar().value() != before_scroll


def test_horizontal_wheel_on_tab_bar_scrolls_tabs_instead_of_switching(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.resize(260, 300)
    widget.show()
    qtbot.waitExposed(widget)

    for i in range(10):
        path = tmp_path / f"long_named_file_{i}.txt"
        path.write_text(f"content {i}", encoding="utf-8")
        widget.load_file(path)

    scroll_bar = widget._tab_scroll.horizontalScrollBar()
    assert scroll_bar.maximum() > 0

    widget._unified_tab_bar.setCurrentIndex(5)
    before_index = widget._unified_tab_bar.currentIndex()
    before_scroll = scroll_bar.value()
    center = widget._unified_tab_bar.rect().center()
    event = QWheelEvent(
        QPointF(center),
        QPointF(widget._unified_tab_bar.mapToGlobal(center)),
        QPoint(0, 0),
        QPoint(-120, 0),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(widget._unified_tab_bar, event)

    assert widget._unified_tab_bar.currentIndex() == before_index
    assert scroll_bar.value() != before_scroll


def test_shift_vertical_wheel_on_tab_bar_scrolls_tabs_horizontally(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.resize(260, 300)
    widget.show()
    qtbot.waitExposed(widget)

    for i in range(10):
        path = tmp_path / f"shift_scroll_file_{i}.txt"
        path.write_text(f"content {i}", encoding="utf-8")
        widget.load_file(path)

    scroll_bar = widget._tab_scroll.horizontalScrollBar()
    assert scroll_bar.maximum() > 0

    widget._unified_tab_bar.setCurrentIndex(4)
    before_index = widget._unified_tab_bar.currentIndex()
    before_scroll = scroll_bar.value()
    center = widget._unified_tab_bar.rect().center()
    event = QWheelEvent(
        QPointF(center),
        QPointF(widget._unified_tab_bar.mapToGlobal(center)),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ShiftModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(widget._unified_tab_bar, event)

    assert widget._unified_tab_bar.currentIndex() == before_index
    assert scroll_bar.value() != before_scroll


def test_horizontal_pixel_delta_on_tab_bar_scrolls_tabs(qtbot, tmp_path: Path) -> None:
    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.resize(260, 300)
    widget.show()
    qtbot.waitExposed(widget)

    for i in range(10):
        path = tmp_path / f"pixel_scroll_file_{i}.txt"
        path.write_text(f"content {i}", encoding="utf-8")
        widget.load_file(path)

    scroll_bar = widget._tab_scroll.horizontalScrollBar()
    assert scroll_bar.maximum() > 0

    before_index = widget._unified_tab_bar.currentIndex()
    before_scroll = scroll_bar.value()
    center = widget._unified_tab_bar.rect().center()
    event = QWheelEvent(
        QPointF(center),
        QPointF(widget._unified_tab_bar.mapToGlobal(center)),
        QPoint(-40, 0),
        QPoint(0, 0),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(widget._unified_tab_bar, event)

    assert widget._unified_tab_bar.currentIndex() == before_index
    assert scroll_bar.value() != before_scroll



def test_drag_reordering_tab_persists_and_does_not_snap_back(qtbot, tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    third = tmp_path / "third.txt"
    for f in (first, second, third):
        f.write_text(f.name, encoding="utf-8")

    widget = PreviewWidget(tmp_path)
    qtbot.addWidget(widget)
    for f in (first, second, third):
        widget.load_file(f)

    bar = widget._unified_tab_bar
    assert [bar.tabData(i) for i in range(bar.count())] == [
        str(first.resolve()),
        str(second.resolve()),
        str(third.resolve()),
    ]

    # Simulate a drag that moves tab 0 to the end. QTabBar.emit tabIndexMoved
    # fires the `tabMoved` signal just like a real mouse drag does.
    bar.moveTab(0, bar.count() - 1)

    # The owning panel's source-of-truth order must mirror the new arrangement…
    assert widget._panels[0]._tab_order == [
        str(second.resolve()),
        str(third.resolve()),
        str(first.resolve()),
    ]
    # …and so must the hidden per-panel tab bar (index alignment).
    assert [widget._panels[0]._tab_bar.tabData(i) for i in range(widget._panels[0]._tab_bar.count())] == [
        str(second.resolve()),
        str(third.resolve()),
        str(first.resolve()),
    ]

    # A subsequent sync (the thing that used to snap the tab back) must preserve
    # the reordered arrangement.
    widget._sync_tabs_from_panels()
    assert [bar.tabData(i) for i in range(bar.count())] == [
        str(second.resolve()),
        str(third.resolve()),
        str(first.resolve()),
    ]

    # And the new order is persisted to disk.
    saved = json.loads(widget._tab_state_path.read_text(encoding="utf-8"))
    assert [Path(p).name for p in saved["tabs"]] == ["second.txt", "third.txt", "first.txt"]


def test_embedded_image_label_does_not_upscale_small_source(qtbot) -> None:
    label = _EmbeddedImageLabel()
    qtbot.addWidget(label)
    label.resize(400, 400)
    label.show()
    qtbot.waitExposed(label)

    source = QPixmap(64, 64)
    source.fill(QColor("#ff0000"))
    label.set_source_pixmap(source)
    rendered = label.pixmap()

    assert rendered is not None
    assert rendered.width() <= 64
    assert rendered.height() <= 64
