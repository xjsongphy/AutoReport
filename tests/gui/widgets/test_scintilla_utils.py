from PyQt6.QtGui import QColor

from autoreport.gui.scintilla_utils import apply_scintilla_style, configure_lexer_colors
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
    assert widget.wrapMode() == QsciScintilla.WrapMode.WrapWord


def test_scintilla_accepts_content_background_override(qtbot):
    from PyQt6.Qsci import QsciScintilla

    widget = QsciScintilla()
    qtbot.addWidget(widget)

    apply_scintilla_style(widget, object_name="testEditorOverride", content_bg="#2d2d2d")

    assert widget.SendScintilla(widget.SCI_STYLEGETBACK, widget.STYLE_DEFAULT) == (
        _scintilla_color_value(QColor("#2d2d2d"))
    )


def test_lexer_uses_override_background():
    from PyQt6.Qsci import QsciLexerPython

    lexer = QsciLexerPython()
    configure_lexer_colors(lexer, paper_color="#2d2d2d")

    assert lexer.paper(0) == QColor("#2d2d2d")


def test_lexer_keeps_syntax_token_colors():
    class FakeLexer:
        def __init__(self):
            self.calls = []

        def setDefaultPaper(self, color):
            self.calls.append(("setDefaultPaper", color))

        def setPaper(self, color, style=None):
            self.calls.append(("setPaper", color, style))

        def setDefaultFont(self, font):
            self.calls.append(("setDefaultFont", font))

        def setFont(self, font, style):
            self.calls.append(("setFont", font, style))

        def setColor(self, color, style=None):
            self.calls.append(("setColor", color, style))

    lexer = FakeLexer()
    configure_lexer_colors(lexer, paper_color="#2d2d2d")

    # Global flattening call should not happen: setColor(color) with no style id.
    set_color_calls = [call for call in lexer.calls if call[0] == "setColor"]
    assert not any(len(call) < 3 or call[2] is None for call in set_color_calls)
    assert any(call[0] == "setDefaultPaper" for call in lexer.calls)
    assert any(call[0] == "setDefaultFont" for call in lexer.calls)
    # Per-style font assignment should exist to avoid style-level fallback fonts.
    assert any(call[0] == "setFont" for call in lexer.calls)
