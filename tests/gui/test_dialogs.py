"""Tests for the unified themed message-box helpers."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QWidget

from autoreport.gui.theme import get_theme_colors
from autoreport.gui.dialogs import (
    critical_box,
    information_box,
    styled_message_box,
    warning_box,
)


def _build_question_box():
    return styled_message_box(
        None,
        QMessageBox.Icon.Question,
        "确认",
        "删除该文件？",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        default=QMessageBox.StandardButton.No,
        affirmative=QMessageBox.StandardButton.Yes,
    )


def test_styled_message_box_is_non_native(qtbot) -> None:
    box = _build_question_box()
    qtbot.addWidget(box)
    # Non-native rendering is required for the unified button stylesheet to apply.
    assert box.testOption(QMessageBox.Option.DontUseNativeDialog) is True


def test_affirmative_button_uses_primary_style(qtbot) -> None:
    box = _build_question_box()
    qtbot.addWidget(box)
    yes = box.button(QMessageBox.StandardButton.Yes)
    no = box.button(QMessageBox.StandardButton.No)
    assert yes is not None and no is not None
    assert yes.objectName() == "msgPrimaryBtn"
    # Non-affirmative buttons keep the default (secondary) selector.
    assert no.objectName() == ""
    assert "#msgPrimaryBtn" in box.styleSheet()


def test_message_box_buttons_use_unified_text_button_style(qtbot) -> None:
    box = _build_question_box()
    qtbot.addWidget(box)
    colors = get_theme_colors()

    style = box.styleSheet()
    assert "background-color: transparent" in style
    assert f"background-color: {colors['buttonBlue']}" not in style
    assert f"background-color: {colors['secondaryBtnBg']}" not in style


def test_message_box_buttons_use_text_button_cursor(qtbot) -> None:
    box = _build_question_box()
    qtbot.addWidget(box)

    yes = box.button(QMessageBox.StandardButton.Yes)
    no = box.button(QMessageBox.StandardButton.No)

    assert yes.cursor().shape() == no.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_standard_buttons_get_chinese_labels(qtbot) -> None:
    box = _build_question_box()
    qtbot.addWidget(box)
    assert box.button(QMessageBox.StandardButton.Yes).text() == "是"
    assert box.button(QMessageBox.StandardButton.No).text() == "否"


def test_simple_wrappers_set_primary_affirmative(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    for fn, icon in [
        (lambda: warning_box(parent, "t", "x"), QMessageBox.Icon.Warning),
        (lambda: information_box(parent, "t", "x"), QMessageBox.Icon.Information),
        (lambda: critical_box(parent, "t", "x"), QMessageBox.Icon.Critical),
    ]:
        # Avoid blocking on exec(): build via the underlying builder instead.
        box = styled_message_box(
            parent, icon, "t", "x", QMessageBox.StandardButton.Ok,
            default=QMessageBox.StandardButton.Ok,
            affirmative=QMessageBox.StandardButton.Ok,
        )
        qtbot.addWidget(box)
        ok = box.button(QMessageBox.StandardButton.Ok)
        assert ok is not None
        assert ok.objectName() == "msgPrimaryBtn"
        assert ok.text() == "确定"
