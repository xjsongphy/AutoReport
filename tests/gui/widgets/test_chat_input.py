"""Tests for ChatInput widget."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
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
