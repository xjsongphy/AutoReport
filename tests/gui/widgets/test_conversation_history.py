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

    def test_has_session_list(self, dropdown: ConversationHistoryDropdown):
        """Should contain a QListWidget."""
        assert dropdown._session_list is not None
        assert dropdown._session_list.count() == 0

    def test_has_new_button(self, dropdown: ConversationHistoryDropdown):
        """Should contain a new conversation button."""
        btn = dropdown.findChild(object, "newSessionBtn")
        assert btn is not None


class TestPopulate:
    """Populating the session list."""

    def test_populate_shows_sessions(self, dropdown: ConversationHistoryDropdown, sample_sessions):
        """populate should add items and show the dropdown."""
        dropdown.populate(sample_sessions)

        assert dropdown.isVisible() is True
        assert dropdown._session_list.count() == 2

    def test_populate_highlights_current(self, dropdown: ConversationHistoryDropdown, sample_sessions):
        """Current session should be bold."""
        dropdown.populate(sample_sessions, current_session_id="s1")

        item = dropdown._session_list.item(0)
        assert item.font().bold() is True

    def test_populate_empty_sessions(self, dropdown: ConversationHistoryDropdown):
        """populate with empty list should still show."""
        dropdown.populate([])
        assert dropdown.isVisible() is True
        assert dropdown._session_list.count() == 0

    def test_session_item_has_id(self, dropdown: ConversationHistoryDropdown, sample_sessions):
        """Each item should store the session ID in UserRole data."""
        from PyQt6.QtCore import Qt

        dropdown.populate(sample_sessions)
        item = dropdown._session_list.item(0)
        assert item.data(Qt.ItemDataRole.UserRole) == "s1"


class TestSignals:
    """Signal emission."""

    def test_new_conversation_signal(self, qtbot, dropdown: ConversationHistoryDropdown, sample_sessions):
        """Clicking new conversation should emit signal and hide."""
        dropdown.populate(sample_sessions)

        with qtbot.waitSignal(dropdown.new_conversation_requested, timeout=1000):
            dropdown._on_new_conversation()

        assert dropdown.isVisible() is False

    def test_double_click_emits_session_selected(self, qtbot, dropdown: ConversationHistoryDropdown, sample_sessions):
        """Double-clicking a session should emit session_selected."""
        from PyQt6.QtCore import Qt

        dropdown.populate(sample_sessions)

        with qtbot.waitSignal(dropdown.session_selected, timeout=1000) as blocker:
            item = dropdown._session_list.item(0)
            dropdown._on_item_double_clicked(item)

        assert blocker.args == ["s1"]
        assert dropdown.isVisible() is False
