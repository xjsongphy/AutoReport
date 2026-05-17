from PyQt6.QtGui import QColor

from autoreport.gui.scintilla_utils import apply_scintilla_style
from autoreport.gui.theme import get_theme_colors


def _scintilla_color_value(color: QColor) -> int:
    return color.red() | (color.green() << 8) | (color.blue() << 16)


def test_scintilla_uses_theme_caret_and_margin(qtbot):
    from PyQt6.Qsci import QsciScintilla

    widget = QsciScintilla()
    qtbot.addWidget(widget)

    apply_scintilla_style(widget, object_name="testEditor")
    colors = get_theme_colors()

    assert widget.SendScintilla(widget.SCI_GETCARETFORE) == _scintilla_color_value(
        QColor(colors["editor_caret_fg"])
    )
    assert widget.marginWidth(1) >= 44


def test_scintilla_accepts_content_background_override(qtbot):
    from PyQt6.Qsci import QsciScintilla

    widget = QsciScintilla()
    qtbot.addWidget(widget)

    apply_scintilla_style(widget, object_name="testEditorOverride", content_bg="#2d2d2d")

    assert widget.SendScintilla(widget.SCI_STYLEGETBACK, widget.STYLE_DEFAULT) == (
        _scintilla_color_value(QColor("#2d2d2d"))
    )
