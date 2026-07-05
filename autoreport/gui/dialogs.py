"""Themed, non-native message boxes that use the unified button styles.

``QMessageBox`` static helpers (``question``/``warning``/…) produce OS-native
dialogs whose buttons ignore the application stylesheet.  These wrappers force
the non-native Qt implementation and apply the same ``filled_button_qss`` /
``secondary_filled_button_qss`` the rest of the UI uses, so every popup's
buttons stay visually consistent.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox, QWidget

from .theme import get_theme_colors
from .widgets.ui_utils import filled_button_qss, secondary_filled_button_qss

_StandardButton = QMessageBox.StandardButton


def styled_message_box(
    parent: QWidget | None,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    buttons: _StandardButton = QMessageBox.StandardButton.Ok,
    *,
    default: _StandardButton = QMessageBox.StandardButton.NoButton,
    affirmative: _StandardButton | None = None,
) -> QMessageBox:
    """Build a non-native ``QMessageBox`` styled with unified buttons.

    Args:
        parent: Parent widget (or ``None``).
        icon: Message-box icon.
        title: Window title.
        text: Body text.
        buttons: OR-combined standard buttons.
        default: The default (focused) button.
        affirmative: Button to render in the primary filled style (e.g. the
            "confirm" action).  Other buttons use the secondary style.
    """
    c = get_theme_colors()
    box = QMessageBox(parent) if parent is not None else QMessageBox()
    box.setOption(QMessageBox.Option.DontUseNativeDialog, True)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)
    if default != QMessageBox.StandardButton.NoButton:
        box.setDefaultButton(default)
    if affirmative is not None:
        primary = box.button(affirmative)
        if primary is not None:
            primary.setObjectName("msgPrimaryBtn")

    padding = "6px 18px"
    radius = c["radius_sm"]
    box.setStyleSheet(
        f"""
        QMessageBox {{
            background-color: {c["bg"]};
            color: {c["fg"]};
        }}
        QMessageBox QLabel, QMessageBox QTextEdit {{
            color: {c["fg"]};
        }}
        {secondary_filled_button_qss(
            "QPushButton",
            radius=radius,
            padding=padding,
            font_size=13,
        )}
        {filled_button_qss(
            "#msgPrimaryBtn",
            bg=c["buttonBlue"],
            fg=c["primaryBtnFg"],
            hover_bg=c["buttonBlue"],
            disabled_bg=c["border"],
            disabled_fg=c["muted"],
            radius=radius,
            padding=padding,
            font_size=13,
        )}
        """
    )
    return box


def question_box(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    default: _StandardButton = QMessageBox.StandardButton.No,
    affirmative: _StandardButton = QMessageBox.StandardButton.Yes,
    buttons: _StandardButton = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
) -> _StandardButton:
    """Styled replacement for ``QMessageBox.question``."""
    box = styled_message_box(
        parent, QMessageBox.Icon.Question, title, text, buttons,
        default=default, affirmative=affirmative,
    )
    return _StandardButton(box.exec())


def warning_box(
    parent: QWidget | None, title: str, text: str
) -> _StandardButton:
    """Styled replacement for ``QMessageBox.warning``."""
    box = styled_message_box(
        parent, QMessageBox.Icon.Warning, title, text,
        QMessageBox.StandardButton.Ok,
        default=QMessageBox.StandardButton.Ok,
        affirmative=QMessageBox.StandardButton.Ok,
    )
    return _StandardButton(box.exec())


def information_box(
    parent: QWidget | None, title: str, text: str
) -> _StandardButton:
    """Styled replacement for ``QMessageBox.information``."""
    box = styled_message_box(
        parent, QMessageBox.Icon.Information, title, text,
        QMessageBox.StandardButton.Ok,
        default=QMessageBox.StandardButton.Ok,
        affirmative=QMessageBox.StandardButton.Ok,
    )
    return _StandardButton(box.exec())


def critical_box(
    parent: QWidget | None, title: str, text: str
) -> _StandardButton:
    """Styled replacement for ``QMessageBox.critical``."""
    box = styled_message_box(
        parent, QMessageBox.Icon.Critical, title, text,
        QMessageBox.StandardButton.Ok,
        default=QMessageBox.StandardButton.Ok,
        affirmative=QMessageBox.StandardButton.Ok,
    )
    return _StandardButton(box.exec())
