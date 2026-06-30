"""Tests for shared GUI scrollbar styling."""

import inspect

from autoreport.gui import main_window
from autoreport.gui.theme import scrollbar_stylesheet
from autoreport.gui.widgets import (
    base_popup_dropdown,
    chat_input,
    conversation_history,
    file_tree,
    messages_area,
    preview,
)


def test_scrollbar_stylesheet_preserves_vertical_options() -> None:
    qss = scrollbar_stylesheet(
        selector="QScrollArea#messagesArea QScrollBar",
        orientation="vertical",
        background_color="#123456",
        thickness="8px",
        min_handle_extent="30px",
        radius="4px",
    )

    assert "QScrollArea#messagesArea QScrollBar:vertical" in qss
    assert "background-color: #123456;" in qss
    assert "width: 8px;" in qss
    assert "min-height: 30px;" in qss
    assert "height: 0;" in qss
    assert ":horizontal" not in qss


def test_scrollbar_stylesheet_preserves_horizontal_options() -> None:
    qss = scrollbar_stylesheet(
        selector="QScrollArea#previewTabScrollArea QScrollBar",
        orientation="horizontal",
        background_color="transparent",
        thickness="6px",
        min_handle_extent="24px",
        radius="0px",
    )

    assert "QScrollArea#previewTabScrollArea QScrollBar:horizontal" in qss
    assert "background-color: transparent;" in qss
    assert "height: 6px;" in qss
    assert "min-width: 24px;" in qss
    assert "width: 0;" in qss
    assert ":vertical" not in qss


def test_scrollbar_call_sites_use_shared_helper() -> None:
    call_sites = [
        main_window.MainWindow._apply_theme,
        messages_area.MessagesArea._setup_ui,
        chat_input.ChatInput._setup_ui,
        file_tree.FileTreeWidget._apply_style,
        preview.PreviewWidget._apply_style,
        conversation_history.ConversationHistoryDropdown._apply_theme,
        base_popup_dropdown.BasePopupDropdown._apply_theme,
    ]

    for call_site in call_sites:
        assert "scrollbar_stylesheet(" in inspect.getsource(call_site)
