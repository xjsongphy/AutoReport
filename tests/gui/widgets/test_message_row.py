"""Tests for MessageRow component — Cline-style flat timeline."""

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication
from autoreport.gui.widgets.message_row import MessageRow
from autoreport.gui.widgets.ui_utils import compact_tooltip_qss


def test_user_message_renders_badge_style(qtbot):
    """User message uses badge-background bubble, no timestamp header."""
    widget = MessageRow(
        role="user",
        content="Hello, agent!",
        timestamp="14:32",
        is_coordination=False
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "You" in display_text
    assert "Hello, agent!" in display_text


def test_agent_message_renders_inline(qtbot):
    """Agent message is inline text with no background."""
    widget = MessageRow(
        role="agent",
        content="I will help you.",
        timestamp="14:33"
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Agent" in display_text
    assert "I will help you." in display_text


def test_agent_message_renders_markdown_but_copies_raw_source(qtbot):
    widget = MessageRow(
        role="agent",
        content="**Bold** and `code`",
        timestamp="14:33",
    )
    qtbot.addWidget(widget)

    label = widget._wrapping_labels[0]
    assert label.textFormat() == Qt.TextFormat.RichText
    assert "<strong>" in label.text() or "font-weight" in label.text()

    event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier,
    )
    assert widget.eventFilter(label, event) is True
    assert QApplication.clipboard().text() == "**Bold** and `code`"


def test_message_row_emits_rollback_checkpoint(qtbot):
    widget = MessageRow(role="user", content="rollback me")
    qtbot.addWidget(widget)
    widget.set_checkpoint_id("cp_123")

    seen = []
    widget.rollback_requested.connect(lambda checkpoint_id, row: seen.append((checkpoint_id, row)))
    widget.rollback_requested.emit(widget._checkpoint_id, widget)

    assert seen == [("cp_123", widget)]


def test_coordination_message_shows_prefix(qtbot):
    """Coordination message shows mute source label."""
    widget = MessageRow(
        role="user",
        content="Calling data analysis agent...",
        timestamp="14:35",
        is_coordination=True
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Calling data analysis agent..." in display_text


def test_empty_timestamp_is_handled(qtbot):
    """Empty timestamp should not cause errors."""
    widget = MessageRow(
        role="user",
        content="Test message",
        timestamp=""
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Test message" in display_text


def test_multiline_content(qtbot):
    """Multiline content should be preserved."""
    widget = MessageRow(
        role="agent",
        content="Line 1\nLine 2\nLine 3",
        timestamp="14:40"
    )
    qtbot.addWidget(widget)

    display_text = widget.get_display_text()
    assert "Line 1" in display_text
    assert "Line 2" in display_text
    assert "Line 3" in display_text


def test_user_message_can_render_collapsed_summary(qtbot):
    widget = MessageRow(
        role="user",
        content="line 1\nline 2",
        summary="Message From Main: line 1",
        detail="line 1\nline 2",
    )
    qtbot.addWidget(widget)

    assert not widget.is_expanded()
    widget._summary_header.clicked.emit()
    assert widget.is_expanded()


def test_agent_message_can_render_collapsed_summary(qtbot):
    widget = MessageRow(
        role="agent",
        content="issue detail",
        summary="Theory reported quality: issue detail",
        detail="issue detail\nmore",
    )
    qtbot.addWidget(widget)

    assert not widget.is_expanded()
    widget._summary_header.clicked.emit()
    assert widget.is_expanded()


def test_user_bubble_width_stable_when_actions_toggle(qtbot):
    widget = MessageRow(role="user", content="Width stability check")
    qtbot.addWidget(widget)
    widget.resize(900, 200)
    widget.mark_complete()
    widget.show()
    qtbot.waitExposed(widget)

    before = widget._user_bubble_container.sizeHint().width()
    widget._set_user_actions_visible(True)
    qtbot.wait(10)
    after_show = widget._user_bubble_container.sizeHint().width()
    widget._set_user_actions_visible(False)
    qtbot.wait(10)
    after_hide = widget._user_bubble_container.sizeHint().width()

    assert before == after_show == after_hide


def test_tooltip_delay_is_2s_for_action_buttons(qtbot):
    widget = MessageRow(role="user", content="tooltip check")
    qtbot.addWidget(widget)
    timer = widget._user_copy_btn._compact_tooltip_filter._timer
    assert timer.interval() == 2000


def test_tooltip_hides_on_leave(qtbot):
    widget = MessageRow(role="user", content="tooltip check")
    qtbot.addWidget(widget)
    filt = widget._user_copy_btn._compact_tooltip_filter
    filt._show(widget._user_copy_btn)
    assert filt._tip is not None
    QApplication.sendEvent(widget._user_copy_btn, QEvent(QEvent.Type.Leave))
    assert filt._tip is None


def test_tooltip_radius_is_larger():
    qss = compact_tooltip_qss()
    assert "border-radius: 6px;" in qss


def test_edit_mode_expands_user_bubble_and_shows_cancel_send(qtbot):
    widget = MessageRow(role="user", content="edit me")
    qtbot.addWidget(widget)
    widget.resize(800, 220)
    widget.mark_complete()
    widget.set_editable(True)
    widget.enter_edit_mode()

    assert widget._editing is True
    assert widget._cancel_btn is not None and widget._cancel_btn.text() == "取消"
    assert widget._save_btn is not None and widget._save_btn.text() == "发送"
    assert widget._user_bubble_container.width() >= 700


def test_edit_input_height_grows_and_caps_at_10_lines(qtbot):
    widget = MessageRow(role="user", content="edit me")
    qtbot.addWidget(widget)
    widget.resize(800, 220)
    widget.mark_complete()
    widget.set_editable(True)
    widget.enter_edit_mode()

    assert widget._edit_widget is not None
    edit = widget._edit_widget
    h1 = edit.height()
    edit.setPlainText("\n".join(f"line {i}" for i in range(1, 6)))
    qtbot.wait(10)
    h5 = edit.height()
    assert edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    edit.setPlainText("\n".join(f"line {i}" for i in range(1, 20)))
    qtbot.wait(10)
    h19 = edit.height()
    assert edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded

    assert h5 > h1
    assert h19 >= h5
    # capped around 10 lines (not unbounded growth)
    assert h19 - h5 < 8 * edit.fontMetrics().lineSpacing()
