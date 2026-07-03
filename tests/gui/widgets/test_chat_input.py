"""Tests for ChatInput widget."""

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QInputMethodEvent, QKeyEvent

from autoreport.gui.widgets.chat_input import ChatInput


def test_enter_key_sends_message(qtbot):
    """Enter key should send message signal."""
    widget = ChatInput()
    qtbot.addWidget(widget)

    # Track signal emissions
    signals = []
    widget.send_message.connect(lambda: signals.append("sent"))

    # Simulate Enter key press
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier,
        "\r"
    )
    widget.keyPressEvent(key_event)

    assert signals == ["sent"], "Enter key should send message"


def test_shift_enter_inserts_newline(qtbot):
    """Shift+Enter should insert newline, not send."""
    widget = ChatInput()
    qtbot.addWidget(widget)

    # Set initial text and move cursor to end
    widget.setPlainText("line 1")
    cursor = widget.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    widget.setTextCursor(cursor)

    # Track signal emissions
    signals = []
    widget.send_message.connect(lambda: signals.append("sent"))

    # Simulate Shift+Enter
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.ShiftModifier,
        "\r\n"
    )
    widget.keyPressEvent(key_event)

    assert signals == [], "Shift+Enter should not send message"
    assert widget.toPlainText() == "line 1\n", "Should insert newline"


def test_ctrl_enter_default_behavior(qtbot):
    """Ctrl+Enter should use default behavior (not send, not insert)."""
    widget = ChatInput()
    qtbot.addWidget(widget)

    signals = []
    widget.send_message.connect(lambda: signals.append("sent"))
    widget.textChanged.connect(lambda: signals.append("changed"))

    # Simulate Ctrl+Enter
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.ControlModifier,
        "\r"
    )
    widget.keyPressEvent(key_event)

    # Default behavior - no signal sent, no text change
    assert "sent" not in signals


def test_input_height_grows_and_scrolls_after_10_lines(qtbot):
    widget = ChatInput()
    qtbot.addWidget(widget)
    widget.resize(360, 80)

    h1 = widget.height()
    widget.setPlainText("\n".join(f"line {i}" for i in range(1, 6)))
    qtbot.wait(10)
    h5 = widget.height()

    assert h5 > h1
    assert widget.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    widget.setPlainText("\n".join(f"line {i}" for i in range(1, 20)))
    qtbot.wait(10)
    h19 = widget.height()

    assert widget.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert h19 >= h5
    assert h19 - h5 < 8 * widget.fontMetrics().lineSpacing()


def test_input_method_preedit_hides_placeholder(qtbot):
    widget = ChatInput()
    qtbot.addWidget(widget)

    assert widget.placeholderText()

    widget.inputMethodEvent(QInputMethodEvent("ni", []))
    assert widget.placeholderText() == ""

    widget.inputMethodEvent(QInputMethodEvent("", []))
    assert widget.placeholderText()


def test_current_prefixed_token_tracks_token_under_cursor(qtbot):
    widget = ChatInput()
    qtbot.addWidget(widget)
    widget.setPlainText("@plot and @rep")

    cursor = widget.textCursor()
    cursor.setPosition(2)
    widget.setTextCursor(cursor)

    token, start, end = widget.current_prefixed_token()

    assert token == "@plot"
    assert (start, end) == (0, 5)


def test_insert_agent_reference_replaces_token_at_cursor(qtbot):
    widget = ChatInput()
    qtbot.addWidget(widget)
    widget.setPlainText("@rep then @plot")
    widget._popup_kind = "@"

    cursor = widget.textCursor()
    cursor.setPosition(2)
    widget.setTextCursor(cursor)

    widget.insert_agent_reference("Report Agent")

    assert widget.toPlainText() == "@Report Agent then @plot"


def test_insert_file_reference_replaces_token_at_cursor(qtbot):
    widget = ChatInput()
    qtbot.addWidget(widget)
    widget.setPlainText("@rep then @plot")
    widget._popup_kind = "@"

    cursor = widget.textCursor()
    cursor.setPosition(2)
    widget.setTextCursor(cursor)

    widget.insert_file_reference(Path("Tex/main.tex"))

    assert widget.toPlainText() == "[@main.tex](project://Tex/main.tex) then @plot"


def test_cursor_motion_rechecks_popup_token(qtbot):
    widget = ChatInput()
    qtbot.addWidget(widget)
    widget.setPlainText("@rep x")
    widget.set_popup_active(True)

    cursor = widget.textCursor()
    cursor.setPosition(4)
    widget.setTextCursor(cursor)

    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Right,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.keyPressEvent(key_event)

    assert widget._popup_active is False
