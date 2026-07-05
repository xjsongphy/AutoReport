"""Tests for FileTreeWidget file operations.

This test module verifies that the file operations work correctly:
- Drag-drop file import
- New file creation
- New folder creation
- File deletion
- File renaming

Note: Due to Windows permission issues with pytest-qt, these tests focus on
verifying the API and methods exist and are callable, rather than full integration tests.
"""

from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QItemSelectionModel, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QAbstractItemDelegate, QTreeWidgetItem

from autoreport.gui.theme import get_theme_colors
from autoreport.gui.widgets.file_tree import (
    FIXED_DIRECTORIES,
    FILE_TREE_CONTENT_LEFT_INSET,
    FileTreeWidget,
    _DragDropTreeWidget,
    _INDICATOR_PLACEHOLDER_ROLE,
)


def test_fixed_directories_constant() -> None:
    """Test that fixed directories are correctly defined."""
    assert isinstance(FIXED_DIRECTORIES, list)
    assert set(FIXED_DIRECTORIES) == {"Data", "References", "Theory", "Plots", "Outline", "Tex"}


def test_file_tree_class_has_required_methods() -> None:
    """Test that FileTreeWidget has all required file operation methods."""
    # Check that the class has the required methods
    assert hasattr(FileTreeWidget, "_new_file")
    assert hasattr(FileTreeWidget, "_new_folder")
    assert hasattr(FileTreeWidget, "_new_file_in_dir")
    assert hasattr(FileTreeWidget, "_new_folder_in_dir")
    assert hasattr(FileTreeWidget, "_delete_file")
    assert hasattr(FileTreeWidget, "_delete_directory")
    assert hasattr(FileTreeWidget, "_rename_file")
    assert hasattr(FileTreeWidget, "_rename_directory")
    assert hasattr(FileTreeWidget, "_handle_drop")
    assert hasattr(FileTreeWidget, "_show_context_menu")
    assert hasattr(FileTreeWidget, "refresh")


def test_file_tree_has_required_attributes() -> None:
    """Test that FileTreeWidget has required attributes for file operations."""
    # Check instance attributes by inspecting the class __init__
    import inspect
    init_source = inspect.getsource(FileTreeWidget.__init__)

    # Should initialize workspace
    assert "self.workspace" in init_source

    # Should initialize tracking variables for inline editing
    assert "_editing_item" in init_source
    assert "_pending_new_item" in init_source
    assert "_pending_new_kind" in init_source


def test_file_tree_has_drag_drop_handlers() -> None:
    """Test that FileTreeWidget has drag-drop event handlers."""
    # Check that drag-drop methods exist
    assert hasattr(FileTreeWidget, "dragEnterEvent")
    assert hasattr(FileTreeWidget, "dragMoveEvent")
    assert hasattr(FileTreeWidget, "dropEvent")


def test_file_tree_has_cross_platform_shortcut_handler() -> None:
    import inspect

    source = inspect.getsource(FileTreeWidget._handle_tree_key)
    assert "Key_F2" in source
    assert "Key_Delete" in source
    assert "Key_Backspace" in source
    assert "matches(QKeySequence.StandardKey.Copy)" in source
    assert "matches(QKeySequence.StandardKey.Paste)" in source


def test_blank_click_selects_project_root(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    selected = []
    widget.directory_selected.connect(selected.append)
    QApplication.sendEvent(
        widget.tree.viewport(),
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, widget.tree.viewport().height() + 20),
            QPointF(widget.tree.viewport().mapToGlobal(widget.tree.viewport().rect().bottomLeft())),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    assert widget.tree.currentItem() is None
    assert widget._get_selected_dir() == "."
    assert selected[-1] == "."


def test_file_tree_enables_extended_selection() -> None:
    import inspect

    setup_source = inspect.getsource(FileTreeWidget._setup_ui)
    assert "SelectionMode.ExtendedSelection" in setup_source


def test_top_level_tree_content_has_left_inset(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    assert widget.tree.indentation() == FILE_TREE_CONTENT_LEFT_INSET


def test_drag_guard_does_not_reference_class_constant() -> None:
    import inspect
    import autoreport.gui.widgets.file_tree as file_tree_module

    # Ensure drag guard uses module-level FIXED_DIRECTORIES, not class attr.
    file_source = inspect.getsource(file_tree_module)
    assert "FileTreeWidget.FIXED_DIRECTORIES" not in file_source


def test_file_tree_has_toolbar_buttons() -> None:
    """Test that FileTreeWidget setup creates toolbar buttons."""
    import inspect
    setup_source = inspect.getsource(FileTreeWidget._setup_ui)

    # Should create toolbar buttons
    assert "_new_file_btn" in setup_source
    assert "_new_folder_btn" in setup_source
    assert "_refresh_btn" in setup_source


def test_file_tree_has_context_menu() -> None:
    """Test that FileTreeWidget has context menu support."""
    import inspect
    setup_source = inspect.getsource(FileTreeWidget._setup_ui)

    # Should enable context menu
    assert "customContextMenuRequested" in setup_source


def test_context_menu_has_required_actions() -> None:
    """Test that context menu has required actions."""
    import inspect
    menu_source = inspect.getsource(FileTreeWidget._show_context_menu)

    # Should have actions for files
    assert "rename_action" in menu_source
    assert "delete_action" in menu_source

    # Should have actions for directories
    assert "new_file_action" in menu_source
    assert "new_folder_action" in menu_source
    assert "copy_action" in menu_source
    assert "paste_action" in menu_source


def test_file_tree_copy_paste_shortcuts_duplicate_selected_file(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "References" / "note.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("copied", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.select_file(source)

    copy_event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier,
    )
    paste_event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_V,
        Qt.KeyboardModifier.ControlModifier,
    )

    assert widget._handle_tree_key(copy_event) is True
    assert widget._handle_tree_key(paste_event) is True
    assert (tmp_path / "References" / "note copy.txt").read_text(encoding="utf-8") == "copied"


def test_file_tree_copy_paste_cmd_shortcut_works_on_mac(qtbot, tmp_path: Path) -> None:
    """⌘C / ⌘V must trigger copy/paste (matches() misses Cmd on macOS)."""
    source = tmp_path / "References" / "note.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("copied", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.select_file(source)

    copy_cmd = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.MetaModifier,
    )
    paste_cmd = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_V,
        Qt.KeyboardModifier.MetaModifier,
    )

    assert widget._handle_tree_key(copy_cmd) is True
    assert widget._handle_tree_key(paste_cmd) is True
    assert (tmp_path / "References" / "note copy.txt").read_text(encoding="utf-8") == "copied"


def test_unique_copy_target_naming(tmp_path: Path) -> None:
    from autoreport.gui.widgets.file_tree import FileTreeWidget

    d = tmp_path
    # no collision -> keep original name
    assert FileTreeWidget._unique_copy_target(Path("x.py"), d).name == "x.py"
    (d / "x.py").touch()
    assert FileTreeWidget._unique_copy_target(Path("x.py"), d).name == "x copy.py"
    (d / "x copy.py").touch()
    assert FileTreeWidget._unique_copy_target(Path("x.py"), d).name == "x copy 2.py"
    (d / "x copy 2.py").touch()
    assert FileTreeWidget._unique_copy_target(Path("x.py"), d).name == "x copy 3.py"
    # directory case: suffix is empty, stem is the dir name
    (d / "foo").mkdir(exist_ok=True)
    assert FileTreeWidget._unique_copy_target(Path("foo"), d).name == "foo copy"


def test_delete_operations_use_confirmation() -> None:
    """Test that delete operations show confirmation dialogs."""
    import inspect

    delete_file_source = inspect.getsource(FileTreeWidget._delete_file)
    delete_dir_source = inspect.getsource(FileTreeWidget._delete_directory)

    # Both should use confirmation dialogs (direct QMessageBox or wrapped helper)
    assert ("QMessageBox.question" in delete_file_source) or ("_ask_confirmation" in delete_file_source)
    assert ("QMessageBox.question" in delete_dir_source) or ("_ask_confirmation" in delete_dir_source)


def test_file_operations_use_correct_paths() -> None:
    """Test that file operations use workspace-relative paths."""
    import inspect

    new_file_source = inspect.getsource(FileTreeWidget._new_file_in_dir)
    new_folder_source = inspect.getsource(FileTreeWidget._new_folder_in_dir)

    # Should use workspace / dir_name for path construction
    assert "self.workspace" in new_file_source
    assert "self.workspace" in new_folder_source


def _make_multi_select_tree(qtbot, tmp_path: Path) -> tuple:
    """Build a tree with Theory/a.tex and Theory/b.tex; return (widget, a_item, b_item)."""
    theory = tmp_path / "Theory"
    theory.mkdir()
    (theory / "a.tex").write_text("a", encoding="utf-8")
    (theory / "b.tex").write_text("b", encoding="utf-8")
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)
    tree = widget.tree
    # select_file forces the directory to be populated and selects a.tex.
    widget.select_file(theory / "a.tex")
    root = tree.topLevelItem(FIXED_DIRECTORIES.index("Theory"))
    items = {root.child(i).text(0): root.child(i) for i in range(root.childCount())}
    return widget, items["a.tex"], items["b.tex"]


def _click_item(tree, item, modifier) -> None:
    rect = tree.visualItemRect(item)
    pt = rect.center()
    ev = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(pt),
        QPointF(tree.mapToGlobal(pt)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        modifier,
    )
    tree.mousePressEvent(ev)


def test_ctrl_click_toggles_multi_selection(qtbot, tmp_path: Path) -> None:
    """Ctrl/Cmd-click toggles a file into the selection (shift already worked)."""
    widget, a, b = _make_multi_select_tree(qtbot, tmp_path)
    tree = widget.tree

    assert {i.text(0) for i in tree.selectedItems()} == {"a.tex"}
    _click_item(tree, b, Qt.KeyboardModifier.ControlModifier)
    assert {i.text(0) for i in tree.selectedItems()} == {"a.tex", "b.tex"}


def test_select_file_preserves_active_multi_selection(qtbot, tmp_path: Path) -> None:
    """Preview feedback (select_file) must not collapse a Ctrl/Cmd multi-selection."""
    widget, a, b = _make_multi_select_tree(qtbot, tmp_path)
    tree = widget.tree

    # Establish multi-selection (a selected, ctrl-toggle b).
    sm = tree.selectionModel()
    sm.select(tree.indexFromItem(b), QItemSelectionModel.SelectionFlag.Toggle)
    assert {i.text(0) for i in tree.selectedItems()} == {"a.tex", "b.tex"}

    # The preview's file-changed feedback calls select_file; selection survives.
    widget.select_file((tmp_path / "Theory" / "b.tex"))
    assert {i.text(0) for i in tree.selectedItems()} == {"a.tex", "b.tex"}


def test_drag_drop_handles_multiple_files() -> None:
    """Test that drag-drop can handle multiple files."""
    import inspect
    drop_source = inspect.getsource(FileTreeWidget._handle_drop)

    # Should iterate through URLs
    assert "for url in urls:" in drop_source

    # Should copy files with progress dialog
    assert "_copy_files_with_progress" in drop_source


def test_file_tree_has_file_watcher() -> None:
    """Test that FileTreeWidget sets up file system watcher."""
    import inspect
    init_source = inspect.getsource(FileTreeWidget.__init__)

    # Should setup file watcher
    assert "_setup_file_watcher" in init_source


def test_inline_edit_methods_exist() -> None:
    """Test that inline edit methods exist for create/rename operations."""
    assert hasattr(FileTreeWidget, "_start_inline_create")
    assert hasattr(FileTreeWidget, "_on_close_editor")
    assert hasattr(FileTreeWidget, "_bind_create_editor_live_updates")


def test_refresh_method_updates_tree() -> None:
    """Test that refresh method updates the tree display."""
    import inspect
    refresh_source = inspect.getsource(FileTreeWidget.refresh)

    # Should update expanded items
    assert "setExpanded" in refresh_source


def test_selected_nested_dir_is_used_for_new_file(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    data_item = widget.tree.topLevelItem(0)
    data_item.setExpanded(True)
    processed_item = data_item.child(0)
    widget.tree.setCurrentItem(processed_item)

    widget._new_file()
    pending = widget._pending_new_item
    assert pending is not None
    widget.tree.blockSignals(True)
    pending.setText(0, "a.txt")
    widget.tree.blockSignals(False)
    widget._finalize_pending_new_item()

    assert (tmp_path / "data" / "processed" / "a.txt").exists()
    assert not (tmp_path / "data" / "a.txt").exists()


def test_hover_text_uses_tilde_prefixed_system_path(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    item = QTreeWidgetItem()
    file_path = tmp_path / "plots" / "plot.py"
    item.setData(0, 257, str(file_path))

    assert widget._hover_text_for_item(item) == FileTreeWidget._tilde_path(file_path)


def test_directory_items_do_not_use_native_tooltip(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    top = widget.tree.topLevelItem(0)
    assert top.toolTip(0) == ""


def test_file_tree_hover_uses_two_second_delay(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    assert widget._hover_timer.interval() == 2000


def test_repeat_new_click_cancels_empty_pending_and_restarts(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    widget._new_file_in_dir("References")
    first_pending = widget._pending_new_item
    assert first_pending is not None

    widget._new_file_in_dir("References")
    second_pending = widget._pending_new_item

    assert second_pending is not None
    assert first_pending is not second_pending


def test_repeat_new_click_keeps_typed_pending_and_starts_another(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    widget._new_file_in_dir("References")
    first_pending = widget._pending_new_item
    assert first_pending is not None
    widget.tree.blockSignals(True)
    first_pending.setText(0, "first.txt")
    widget.tree.blockSignals(False)

    widget._new_file_in_dir("References")
    second_pending = widget._pending_new_item

    assert (tmp_path / "references" / "first.txt").exists()
    assert second_pending is not None
    assert first_pending is not second_pending


def test_repeat_new_click_uses_live_editor_text(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    widget._new_file_in_dir("References")
    qtbot.wait(20)
    assert widget._pending_editor is not None
    widget._pending_editor.setText("typed.txt")

    widget._new_file_in_dir("References")

    assert (tmp_path / "references" / "typed.txt").exists()
    assert widget._pending_new_item is not None


def test_close_editor_uses_live_editor_text(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    widget._new_file_in_dir("References")
    qtbot.wait(20)
    assert widget._pending_editor is not None
    editor = widget._pending_editor
    editor.setText("closed.txt")

    widget._on_close_editor(editor, QAbstractItemDelegate.EndEditHint.NoHint)

    assert (tmp_path / "references" / "closed.txt").exists()
    assert widget._pending_new_item is None


def test_new_file_in_collapsed_nested_dir_keeps_pending_item(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    data_item = widget.tree.topLevelItem(0)
    processed_item = data_item.child(0)
    assert not processed_item.isExpanded()

    widget._new_file_in_dir("Data/Processed")

    pending = widget._pending_new_item
    assert pending is not None
    assert pending.parent() is processed_item
    assert processed_item.isExpanded()


def test_drop_target_resolves_nested_directories(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    data_item = widget.tree.topLevelItem(0)
    processed_item = data_item.child(0)

    assert widget._resolve_target_dir(processed_item) == "Data/Processed"


def test_drag_hover_highlights_resolved_directory(qtbot, tmp_path: Path) -> None:
    target_file = tmp_path / "References" / "note.txt"
    nested_file = tmp_path / "References" / "nested" / "deep.txt"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    nested_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("x", encoding="utf-8")
    nested_file.write_text("deep", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    refs_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    refs_item.setExpanded(True)
    widget._on_item_expanded(refs_item)
    file_item = None
    nested_item = None
    nested_child = None
    for i in range(refs_item.childCount()):
        child = refs_item.child(i)
        if child.data(0, Qt.ItemDataRole.UserRole + 1) == str(target_file):
            file_item = child
        if child.data(0, Qt.ItemDataRole.UserRole) == "References/nested":
            nested_item = child
            child.setExpanded(True)
            widget._on_item_expanded(child)
            nested_child = child.child(0)
    assert file_item is not None
    assert nested_item is not None
    assert nested_child is not None

    widget._set_drop_target_from_item(file_item)
    assert widget._drop_target_item is refs_item
    assert widget.tree._row_background_color(refs_item).name() == get_theme_colors()["tree_hover"]
    assert widget.tree._row_background_color(file_item).name() == get_theme_colors()["tree_hover"]
    assert widget.tree._row_background_color(nested_item).name() == get_theme_colors()["tree_hover"]
    assert widget.tree._row_background_color(nested_child).name() == get_theme_colors()["tree_hover"]

    widget._clear_drop_target()
    assert widget._drop_target_item is None
    assert not widget._is_drop_highlight_item(refs_item)


def test_tree_row_states_paint_row_and_branch_with_same_color(qtbot, tmp_path: Path) -> None:
    import inspect

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    colors = get_theme_colors()
    refs_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert refs_item is not None

    widget.tree.setCurrentItem(refs_item)
    refs_item.setSelected(True)
    assert widget.tree._row_background_color(refs_item).name() == colors["tree_sel_bg"]

    widget.tree.clearSelection()
    refs_item.setSelected(False)
    widget._set_drop_target_from_item(refs_item)
    assert widget.tree._row_background_color(refs_item).name() == colors["tree_hover"]

    widget._clear_drop_target()
    widget._editing_item = refs_item
    assert widget.tree._row_background_color(refs_item).name() == colors["tree_sel_bg"]
    widget._set_editing_item(None)

    widget._new_file_in_dir("References")
    pending = widget._pending_new_item
    assert pending is not None
    assert widget._editing_item is pending
    assert widget.tree._row_background_color(pending).name() == colors["tree_sel_bg"]
    widget._cancel_pending_new_item()

    refs_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert refs_item is not None
    widget._rename_directory(tmp_path / "references", refs_item)
    assert widget._editing_item is refs_item
    assert widget.tree._row_background_color(refs_item).name() == colors["tree_sel_bg"]
    widget._set_editing_item(None)

    row_color_source = inspect.getsource(_DragDropTreeWidget._row_background_color)
    draw_row_source = inspect.getsource(_DragDropTreeWidget.drawRow)
    draw_branch_source = inspect.getsource(_DragDropTreeWidget.drawBranches)
    stylesheet = widget.styleSheet()

    assert "tree_sel_bg" in row_color_source
    assert "tree_hover" in row_color_source
    assert "fillRect(rect, color)" in draw_row_source
    assert "fillRect(rect, color)" in draw_branch_source
    assert "super().drawBranches" not in draw_branch_source
    assert "drawLine" in draw_branch_source
    assert "#fileTree::item:hover" in stylesheet
    assert "show-decoration-selected: 0;" in stylesheet
    assert f'background-color: {colors["bg"]};' in stylesheet


def test_processed_directory_is_not_draggable_but_files_inside_are(qtbot, tmp_path: Path) -> None:
    processed_file = tmp_path / "data" / "processed" / "result.txt"
    processed_file.parent.mkdir(parents=True, exist_ok=True)
    processed_file.write_text("ok", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    data_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("Data"))
    processed_item = data_item.child(0)
    processed_item.setExpanded(True)
    widget._on_item_expanded(processed_item)
    file_item = processed_item.child(0)

    assert not (data_item.flags() & Qt.ItemFlag.ItemIsDragEnabled)
    assert not (processed_item.flags() & Qt.ItemFlag.ItemIsDragEnabled)
    assert file_item.flags() & Qt.ItemFlag.ItemIsDragEnabled


def test_directories_do_not_show_folder_icons(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    for i in range(widget.tree.topLevelItemCount()):
        item = widget.tree.topLevelItem(i)
        assert item is not None
        assert item.icon(0).isNull()


def test_empty_directory_keeps_expand_indicator_after_reload(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    references_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert references_item is not None

    references_item.setExpanded(True)
    widget._on_item_expanded(references_item)

    real_children = [
        references_item.child(i)
        for i in range(references_item.childCount())
        if not references_item.child(i).data(0, _INDICATOR_PLACEHOLDER_ROLE)
    ]
    assert len(real_children) == 0
    assert any(
        references_item.child(i).data(0, _INDICATOR_PLACEHOLDER_ROLE)
        for i in range(references_item.childCount())
    )
    assert (
        references_item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )
    assert widget.tree.updatesEnabled()


def test_refresh_recovers_directory_indicator_policy(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    references_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert references_item is not None

    references_item.setChildIndicatorPolicy(
        QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless
    )
    widget.refresh()

    # refresh() rebuilds the tree, so re-fetch the item before asserting.
    references_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert references_item is not None
    assert (
        references_item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )


def test_expand_top_level_collapses_other_top_level(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    data_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("Data"))
    refs_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert data_item is not None
    assert refs_item is not None

    data_item.setExpanded(True)
    assert data_item.isExpanded()

    widget._collapse_other_top_level_dirs("References")
    refs_item.setExpanded(True)

    assert not data_item.isExpanded()
    assert refs_item.isExpanded()
    assert (
        data_item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )
    assert (
        refs_item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )


def test_new_file_editor_is_bound_after_start_create(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    widget._new_file_in_dir("References")
    qtbot.wait(20)
    assert widget._pending_new_item is not None
    assert widget._pending_editor is not None


def test_directory_changed_restores_selected_file(qtbot, tmp_path: Path) -> None:
    target_file = tmp_path / "References" / "keep.txt"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("x", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    refs_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert refs_item is not None
    refs_item.setExpanded(True)
    widget._on_item_expanded(refs_item)
    assert refs_item.childCount() > 0

    selected = None
    for i in range(refs_item.childCount()):
        child = refs_item.child(i)
        if child.data(0, 257) == str(target_file):
            selected = child
            break
    assert selected is not None

    widget.tree.setCurrentItem(selected)
    widget._on_directory_changed(str((tmp_path / "references").resolve()))

    current = widget.tree.currentItem()
    assert current is not None
    assert current.data(0, 257) == str(target_file)


def test_select_moved_path_keeps_selection_on_new_file(qtbot, tmp_path: Path) -> None:
    moved = tmp_path / "References" / "moved.txt"
    moved.parent.mkdir(parents=True, exist_ok=True)
    moved.write_text("x", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    widget._select_moved_path(moved)

    current = widget.tree.currentItem()
    assert current is not None
    assert current.data(0, Qt.ItemDataRole.UserRole + 1) == str(moved)


def test_internal_move_keeps_references_expand_indicator(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "Data" / "raw.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("x", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    data_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("Data"))
    refs_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert data_item is not None
    assert refs_item is not None

    data_item.setExpanded(True)
    widget._on_item_expanded(data_item)
    processed_item = None
    file_item = None
    for i in range(data_item.childCount()):
        child = data_item.child(i)
        rel = child.data(0, Qt.ItemDataRole.UserRole)
        if rel == "Data/Processed":
            processed_item = child
        if child.data(0, Qt.ItemDataRole.UserRole + 1) == str(source):
            file_item = child
    assert processed_item is not None
    assert file_item is not None

    widget.tree.clearSelection()
    file_item.setSelected(True)
    widget._handle_internal_move(None, processed_item)

    # _handle_internal_move refreshes the tree, rebuilding all items.
    references_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert references_item is not None
    assert (
        references_item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )


def test_internal_move_keeps_indicator_when_references_is_expanded(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "Data" / "raw.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("x", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    data_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("Data"))
    refs_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert data_item is not None
    assert refs_item is not None

    refs_item.setExpanded(True)
    widget._on_item_expanded(refs_item)

    data_item.setExpanded(True)
    widget._on_item_expanded(data_item)
    processed_item = None
    file_item = None
    for i in range(data_item.childCount()):
        child = data_item.child(i)
        rel = child.data(0, Qt.ItemDataRole.UserRole)
        if rel == "Data/Processed":
            processed_item = child
        if child.data(0, Qt.ItemDataRole.UserRole + 1) == str(source):
            file_item = child
    assert processed_item is not None
    assert file_item is not None

    widget.tree.clearSelection()
    file_item.setSelected(True)
    widget._handle_internal_move(None, processed_item)

    # _handle_internal_move refreshes the tree, rebuilding all items.
    references_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("References"))
    assert references_item is not None
    assert (
        references_item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )


def test_clicking_blank_area_selects_root_directory(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)
    widget.resize(320, 420)
    widget.show()
    qtbot.wait(20)

    captured: list[str] = []
    widget.directory_selected.connect(captured.append)

    viewport = widget.tree.viewport()
    pos = QPointF(float(viewport.width() - 2), float(viewport.height() - 2))
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(viewport, event)

    assert widget.tree.currentItem() is None
    assert captured
    assert captured[-1] == "."


def test_select_file_updates_current_item(qtbot, tmp_path: Path) -> None:
    target = tmp_path / "Tex" / "a.tex"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    assert widget.select_file(target)
    selected = widget.get_selected_file()
    assert selected is not None
    assert selected.resolve() == target.resolve()


def test_file_tree_state_is_persisted_and_restored(qtbot, tmp_path: Path) -> None:
    target = tmp_path / "Tex" / "state.tex"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")

    first = FileTreeWidget(tmp_path)
    qtbot.addWidget(first)
    assert first.select_file(target)
    first.save_state()

    second = FileTreeWidget(tmp_path)
    qtbot.addWidget(second)
    second.restore_state()

    selected = second.get_selected_file()
    assert selected is not None
    assert selected.resolve() == target.resolve()
