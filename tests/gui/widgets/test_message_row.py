"""Tests for MessageRow component — Cline-style flat timeline."""

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QPainter, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
from autoreport.gui.widgets.message_row import MessageRow, _opaque_bounds, _raw_markdown_for_selected_text
from autoreport.gui.widgets.messages_area import MessagesArea
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


def test_selected_agent_markdown_copy_preserves_inline_markup():
    raw = "**Bold** and `code`"
    assert _raw_markdown_for_selected_text(raw, "Bold") == "**Bold**"
    assert _raw_markdown_for_selected_text(raw, "code") == "`code`"
    assert _raw_markdown_for_selected_text(raw, "Bold and code") == raw


def test_opaque_bounds_detects_nontransparent_region():
    pixmap = QPixmap(10, 10)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.fillRect(2, 1, 4, 5, QColor("#ffffff"))
    painter.end()

    bounds = _opaque_bounds(pixmap)
    assert bounds == QRect(2, 1, 4, 5)


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
        content="line 1\nline 2\nline 3\nline 4\nline 5\nline 6",
        bubble_title="Message From Main: line 1",
    )
    qtbot.addWidget(widget)
    widget.resize(520, 240)
    widget.show()
    qtbot.waitExposed(widget)
    qtbot.wait(20)

    assert not widget.is_expanded()
    assert widget._body_content_widget is not None
    widget._bubble_header.clicked.emit()
    assert widget.is_expanded()


def test_agent_message_can_render_collapsed_summary(qtbot):
    widget = MessageRow(
        role="agent",
        content="issue detail\nmore\nline 3\nline 4\nline 5\nline 6",
        display_mode="bubble",
        bubble_title="Theory reported quality: issue detail",
        bubble_align="left",
        bubble_on_timeline=True,
    )
    qtbot.addWidget(widget)
    widget.resize(520, 260)
    widget.show()
    qtbot.waitExposed(widget)
    qtbot.wait(20)

    assert not widget.is_expanded()
    assert widget._body_content_widget is not None
    widget._bubble_header.clicked.emit()
    assert widget.is_expanded()


def test_long_user_bubble_shows_expand_button_on_hover(qtbot):
    widget = MessageRow(
        role="user",
        content="\n".join(f"line {i}" for i in range(1, 9)),
    )
    qtbot.addWidget(widget)
    widget.resize(520, 260)
    widget.show()
    qtbot.waitExposed(widget)
    qtbot.wait(20)

    assert widget._body_content_widget is not None
    body = widget._body_content_widget
    assert body.has_overflow() is True
    assert body._toggle_btn.isVisible() is False

    QApplication.sendEvent(body, QEvent(QEvent.Type.Enter))
    qtbot.wait(20)
    assert body._toggle_btn.isVisible() is True
    assert body._toggle_btn.text() == "Show More"

    qtbot.mouseClick(body._toggle_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(20)
    assert body.is_expanded() is True
    assert body._toggle_btn.text() == "Show less"


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


def test_user_bubble_has_reasonable_min_width_in_normal_mode(qtbot):
    widget = MessageRow(role="user", content="short")
    qtbot.addWidget(widget)
    widget.resize(900, 200)
    widget.show()
    qtbot.waitExposed(widget)
    qtbot.wait(20)

    assert widget._user_bubble_container.width() >= 800


def test_user_bubble_is_centered_in_row(qtbot):
    widget = MessageRow(role="user", content="center me")
    qtbot.addWidget(widget)
    widget.resize(900, 200)
    widget.show()
    qtbot.waitExposed(widget)
    qtbot.wait(20)

    bubble_center = widget._user_bubble_container.mapTo(widget, widget._user_bubble_container.rect().center()).x()
    row_center = widget.rect().center().x()
    assert abs(bubble_center - row_center) <= 10


def test_user_bubble_left_edge_aligns_with_timeline_dot_guide(qtbot):
    widget = MessageRow(role="user", content="align me")
    qtbot.addWidget(widget)
    widget.resize(900, 200)
    widget.show()
    qtbot.waitExposed(widget)
    qtbot.wait(20)

    bubble_left = widget._user_bubble_container.mapTo(widget, widget._user_bubble_container.rect().topLeft()).x()
    assert abs(bubble_left - 22) <= 2


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


def test_edit_wheel_at_boundary_does_not_scroll_outer_messages_area(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    area = MessagesArea()
    layout.addWidget(area)
    host.resize(420, 220)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    for i in range(12):
        area.add_message_row(role="agent", content=f"agent {i}\nline 2\nline 3", timestamp="12:00")
    row = area.add_message_row(role="user", content="edit me")
    row.set_editable(True)
    row.enter_edit_mode()
    assert row._edit_widget is not None

    edit = row._edit_widget
    edit.setPlainText("\n".join(f"line {i}" for i in range(1, 40)))
    qtbot.wait(20)
    edit.verticalScrollBar().setValue(0)
    area.verticalScrollBar().setValue(max(0, area.verticalScrollBar().maximum() - 40))
    qtbot.wait(20)
    outer_before = area.verticalScrollBar().value()

    pos = edit.viewport().rect().center()
    wheel = QWheelEvent(
        QPointF(pos),
        QPointF(edit.viewport().mapToGlobal(pos)),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(edit.viewport(), wheel)
    qtbot.wait(20)

    assert area.verticalScrollBar().value() == outer_before


def test_copy_user_message_excludes_editor_context_metadata(qtbot):
    content = "Editor context: file\nCurrent file: docs/report.tex\n\nActual user message"
    widget = MessageRow(role="user", content=content)
    qtbot.addWidget(widget)

    widget._copy_content()

    assert QApplication.clipboard().text() == "Actual user message"
    assert "Current file:" not in QApplication.clipboard().text()


def test_edit_mode_uses_visible_text_without_editor_context_metadata(qtbot):
    content = "Editor context: selection\nFile: docs/report.tex\nSelected lines: 3-4\n\nActual user message"
    widget = MessageRow(role="user", content=content)
    qtbot.addWidget(widget)
    widget.mark_complete()
    widget.set_editable(True)
    widget.enter_edit_mode()

    assert widget._edit_widget is not None
    assert widget._edit_widget.toPlainText() == "Actual user message"


def test_context_chip_text_is_vertically_centered(qtbot):
    content = "Editor context: file\nCurrent file: docs/report.tex\n\nActual user message"
    widget = MessageRow(role="user", content=content)
    qtbot.addWidget(widget)
    widget.resize(900, 200)
    widget.show()
    qtbot.waitExposed(widget)
    qtbot.wait(20)

    chip = widget._context_chip_widget
    label = widget._context_chip_label
    assert chip is not None
    assert label is not None

    chip_center = chip.mapTo(widget, chip.rect().center()).y()
    label_center = label.mapTo(widget, label.rect().center()).y()
    assert abs(chip_center - label_center) <= 2
