from PyQt6.QtGui import QColor

from autoreport.gui.scintilla_utils import (
    CODE_TEXT_LEFT_MARGIN,
    LINE_NUMBER_MARGIN_MIN_WIDTH,
    apply_scintilla_style,
    configure_lexer_colors,
)
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
    assert widget.marginWidth(1) >= LINE_NUMBER_MARGIN_MIN_WIDTH
    assert widget.SendScintilla(widget.SCI_GETMARGINLEFT) == CODE_TEXT_LEFT_MARGIN
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


def test_markdown_styles_match_vscode(qtbot):
    """Markdown headings/bold/code get VSCode accent colors; links stay plain.

    VSCode dark-modern scopes markup.heading/markup.bold (#569CD6) and
    markup.inline.raw (#CE9178), but defines NO link token color, so links and
    math content render as plain foreground.
    """
    from PyQt6.Qsci import QsciLexerMarkdown, QsciScintilla

    from autoreport.gui.scintilla_utils import configure_lexer_colors

    sci = QsciScintilla()
    qtbot.addWidget(sci)
    lexer = QsciLexerMarkdown(sci)
    sci.setLexer(lexer)
    configure_lexer_colors(lexer)

    sci.setText("# Title\n\n**bold** `code`\n\n$[a,b]$")
    sci.SendScintilla(sci.SCI_COLOURISE, 0, -1)

    from PyQt6.QtGui import QColor

    from autoreport.gui.theme import get_theme_colors

    colors = get_theme_colors()

    def color_at(char_index: int) -> str:
        style = sci.SendScintilla(sci.SCI_GETSTYLEAT, char_index)
        return lexer.color(style).name()

    text = sci.text()
    # Heading marker '#' -> heading color; bold 'b' -> bold color.
    assert color_at(text.index("#")).lower() == colors["md_heading"].lower()
    assert color_at(text.index("**bold**") + 2).lower() == colors["md_bold"].lower()
    # Inline code 'c' -> string (markup.inline.raw) color.
    assert color_at(text.index("`code`") + 1).lower() == colors["syntax_string"].lower()
    # Math brackets are plain foreground, NOT a link color.
    assert color_at(text.index("[a,b]")).lower() == colors["editor_fg"].lower()


def test_tex_commands_get_function_color(qtbot):
    r"""LaTeX \commands render in VSCode's function color (#DCDCAA / #795E26).

    QScintilla lumps \commands into the Text style; post-processing restyles
    them into the Command bucket.
    """
    from PyQt6.Qsci import QsciLexerTeX, QsciScintilla

    from autoreport.gui.scintilla_utils import (
        attach_tex_command_coloring,
        configure_lexer_colors,
    )

    sci = QsciScintilla()
    qtbot.addWidget(sci)
    lexer = QsciLexerTeX(sci)
    sci.setLexer(lexer)
    configure_lexer_colors(lexer)
    attach_tex_command_coloring(sci)

    sci.setText(r"\section{Hi} and text")
    # setText triggers the attached textChanged -> command coloring.

    from autoreport.gui.theme import get_theme_colors

    colors = get_theme_colors()
    text = sci.text()
    command_style = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, text.index("section")))
    # '\section' tokens use the function color; surrounding plain text does not.
    assert command_style.name().lower() == colors["syntax_function"].lower()
    plain = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, text.index("and")))
    assert plain.name().lower() == colors["editor_fg"].lower()


def test_markdown_fenced_code_block_has_syntax_colors(qtbot):
    """VSCode embeds language grammars in ```lang blocks; we do the same.

    A ```python block must show at least two distinct token colors (not the
    single monochrome style QScintilla's markdown lexer would give it).
    """
    from PyQt6.Qsci import QsciLexerMarkdown, QsciScintilla

    from autoreport.gui.scintilla_utils import (
        attach_markdown_post_styling,
        configure_lexer_colors,
    )

    sci = QsciScintilla()
    qtbot.addWidget(sci)
    lexer = QsciLexerMarkdown(sci)
    sci.setLexer(lexer)
    configure_lexer_colors(lexer)
    attach_markdown_post_styling(sci)

    sci.setText('Text\n\n```python\ndef f():\n    return "x"\n```\n')
    # setText fires textChanged -> highlighting.

    code = 'def f():\n    return "x"'
    start = sci.text().index(code)
    seen = {
        sci.SendScintilla(sci.SCI_STYLEGETFORE, sci.SendScintilla(sci.SCI_GETSTYLEAT, start + i))
        for i in range(len(code))
    }
    # Multiple distinct colors => the block is syntax-highlighted, not flat.
    assert len(seen) >= 2
