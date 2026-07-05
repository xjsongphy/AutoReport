"""Tests for ConversationHistoryDropdown widget."""

from pathlib import Path

import pytest

from autoreport.gui.widgets.conversation_history import ConversationHistoryDropdown


@pytest.fixture
def dropdown(qtbot) -> ConversationHistoryDropdown:
    """Create a ConversationHistoryDropdown for testing."""
    widget = ConversationHistoryDropdown()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def sample_sessions() -> list[dict]:
    """Create sample session data."""
    return [
        {"id": "s1", "name": "First chat", "timestamp": "2026-05-01T10:00:00", "preview": "Hello"},
        {"id": "s2", "name": "Second chat", "timestamp": "2026-05-01T11:00:00", "preview": "World"},
    ]


class TestDropdownBasics:
    """Basic widget behavior."""

    def test_initially_hidden(self, dropdown: ConversationHistoryDropdown):
        """Dropdown should be hidden by default."""
        assert dropdown.isVisible() is False

    def test_is_a_list_widget(self, dropdown: ConversationHistoryDropdown):
        """Should be a QListWidget itself."""
        from PyQt6.QtWidgets import QListWidget
        assert isinstance(dropdown, QListWidget)

    def test_no_new_button(self, dropdown: ConversationHistoryDropdown):
        """Should NOT contain a new conversation button (removed)."""
        btn = dropdown.findChild(object, "newSessionBtn")
        assert btn is None


class TestPopulate:
    """Populating the session list."""

    def test_populate_shows_sessions(self, dropdown: ConversationHistoryDropdown, sample_sessions):
        """populate should add items."""
        dropdown.populate(sample_sessions)
        assert dropdown.count() == 2

    def test_populate_highlights_current(self, dropdown: ConversationHistoryDropdown, sample_sessions):
        """Current session should have blue text."""
        dropdown.populate(sample_sessions, current_session_id="s1")
        item = dropdown.item(0)
        widget = dropdown.itemWidget(item)
        assert widget is not None
        assert widget._is_current is True

    def test_populate_empty_sessions(self, dropdown: ConversationHistoryDropdown):
        """populate with empty list should work."""
        dropdown.populate([])
        assert dropdown.count() == 0

    def test_session_item_has_id(self, dropdown: ConversationHistoryDropdown, sample_sessions):
        """Each item should store the session ID in UserRole data."""
        from PyQt6.QtCore import Qt

        dropdown.populate(sample_sessions)
        item = dropdown.item(0)
        assert item.data(Qt.ItemDataRole.UserRole) == "s1"

    def test_session_item_has_custom_widget(self, dropdown: ConversationHistoryDropdown, sample_sessions):
        """Each item should have a custom SessionListItem widget."""
        dropdown.populate(sample_sessions)
        item = dropdown.item(0)
        widget = dropdown.itemWidget(item)
        assert widget is not None
        assert widget._session_id == "s1"


class TestSignals:
    """Signal emission."""

    def test_delete_button_emits_signal(self, qtbot, dropdown: ConversationHistoryDropdown, sample_sessions):
        """Clicking delete button should emit delete_session_requested signal."""
        dropdown.populate(sample_sessions)

        item = dropdown.item(0)
        widget = dropdown.itemWidget(item)

        with qtbot.waitSignal(dropdown.delete_session_requested, timeout=1000) as blocker:
            widget._on_delete()

        assert blocker.args == ["s1"]

    def test_click_emits_session_selected(self, qtbot, dropdown: ConversationHistoryDropdown, sample_sessions):
        """Clicking a session should emit session_selected."""
        dropdown.populate(sample_sessions)

        with qtbot.waitSignal(dropdown.session_selected, timeout=1000) as blocker:
            item = dropdown.item(0)
            dropdown._on_item_clicked(item)

        assert blocker.args == ["s1"]
