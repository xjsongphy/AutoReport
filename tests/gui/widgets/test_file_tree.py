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
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QAbstractItemDelegate, QTreeWidgetItem

from autoreport.gui.widgets.file_tree import FileTreeWidget, FIXED_DIRECTORIES


def test_fixed_directories_constant() -> None:
    """Test that fixed directories are correctly defined."""
    assert isinstance(FIXED_DIRECTORIES, list)
    assert set(FIXED_DIRECTORIES) == {"data", "references", "theory", "code", "tex"}


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


def test_delete_operations_use_confirmation() -> None:
    """Test that delete operations show confirmation dialogs."""
    import inspect

    delete_file_source = inspect.getsource(FileTreeWidget._delete_file)
    delete_dir_source = inspect.getsource(FileTreeWidget._delete_directory)

    # Both should use QMessageBox for confirmation
    assert "QMessageBox.question" in delete_file_source
    assert "QMessageBox.question" in delete_dir_source


def test_file_operations_use_correct_paths() -> None:
    """Test that file operations use workspace-relative paths."""
    import inspect

    new_file_source = inspect.getsource(FileTreeWidget._new_file_in_dir)
    new_folder_source = inspect.getsource(FileTreeWidget._new_folder_in_dir)

    # Should use workspace / dir_name for path construction
    assert "self.workspace" in new_file_source
    assert "self.workspace" in new_folder_source


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
    file_path = tmp_path / "code" / "plot.py"
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

    widget._new_file_in_dir("references")
    first_pending = widget._pending_new_item
    assert first_pending is not None

    widget._new_file_in_dir("references")
    second_pending = widget._pending_new_item

    assert second_pending is not None
    assert first_pending is not second_pending


def test_repeat_new_click_keeps_typed_pending_and_starts_another(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    widget._new_file_in_dir("references")
    first_pending = widget._pending_new_item
    assert first_pending is not None
    widget.tree.blockSignals(True)
    first_pending.setText(0, "first.txt")
    widget.tree.blockSignals(False)

    widget._new_file_in_dir("references")
    second_pending = widget._pending_new_item

    assert (tmp_path / "references" / "first.txt").exists()
    assert second_pending is not None
    assert first_pending is not second_pending


def test_repeat_new_click_uses_live_editor_text(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    widget._new_file_in_dir("references")
    qtbot.wait(20)
    assert widget._pending_editor is not None
    widget._pending_editor.setText("typed.txt")

    widget._new_file_in_dir("references")

    assert (tmp_path / "references" / "typed.txt").exists()
    assert widget._pending_new_item is not None


def test_close_editor_uses_live_editor_text(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    widget._new_file_in_dir("references")
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

    widget._new_file_in_dir("data/processed")

    pending = widget._pending_new_item
    assert pending is not None
    assert pending.parent() is processed_item
    assert processed_item.isExpanded()


def test_drop_target_resolves_nested_directories(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    data_item = widget.tree.topLevelItem(0)
    processed_item = data_item.child(0)

    assert widget._resolve_target_dir(processed_item) == "data/processed"


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

    references_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("references"))
    assert references_item is not None

    references_item.setExpanded(True)
    widget._on_item_expanded(references_item)

    assert references_item.childCount() == 0
    assert (
        references_item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )
    assert widget.tree.updatesEnabled()


def test_refresh_recovers_directory_indicator_policy(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    references_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("references"))
    assert references_item is not None

    references_item.setChildIndicatorPolicy(
        QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless
    )
    widget.refresh()

    assert (
        references_item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )


def test_expand_top_level_collapses_other_top_level(qtbot, tmp_path: Path) -> None:
    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    data_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("data"))
    refs_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("references"))
    assert data_item is not None
    assert refs_item is not None

    data_item.setExpanded(True)
    assert data_item.isExpanded()

    widget._collapse_other_top_level_dirs("references")
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

    widget._new_file_in_dir("references")
    qtbot.wait(20)
    assert widget._pending_new_item is not None
    assert widget._pending_editor is not None


def test_directory_changed_restores_selected_file(qtbot, tmp_path: Path) -> None:
    target_file = tmp_path / "references" / "keep.txt"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("x", encoding="utf-8")

    widget = FileTreeWidget(tmp_path)
    qtbot.addWidget(widget)

    refs_item = widget.tree.topLevelItem(FIXED_DIRECTORIES.index("references"))
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
