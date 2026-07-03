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
    """Markdown headings/bold/code/links get VSCode accent colors.

    Verifies that the VSCode-inspired palette maps QScintilla's markdown
    lexer style names to the correct theme keys.  Link references like
    ``[label]`` are now coloured as md_link (#4CB9FF / #0451A5).
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
    # Inline code 'c' -> md_code (markup.inline.raw) color — decoupled from
    # syntax_string so light mode uses VSCode blue (#0451A5) instead of red.
    assert color_at(text.index("`code`") + 1).lower() == colors["md_code"].lower()
    # Link reference '[a,b]' is now styled as a link (md_link); previously
    # fell through to fg because the Link style was unmapped.
    assert color_at(text.index("[a,b]")).lower() == colors["md_link"].lower()


def test_tex_commands_get_function_color(qtbot):
    r"""LaTeX \commands render in tex_command color (#DCDCAA / #624A16).

    QScintilla lumps \commands into the Text style; post-processing restyles
    them into the Command bucket.  Uses tex_command (not syntax_function)
    for darker light-mode readability on white backgrounds.
    """
    from PyQt6.Qsci import QsciLexerTeX, QsciScintilla

    from autoreport.gui.scintilla_utils import (
        attach_tex_post_styling,
        configure_lexer_colors,
    )

    sci = QsciScintilla()
    qtbot.addWidget(sci)
    lexer = QsciLexerTeX(sci)
    sci.setLexer(lexer)
    configure_lexer_colors(lexer)
    attach_tex_post_styling(sci)

    sci.setText(r"\section{Hi} and text")
    # setText triggers the attached textChanged -> command coloring.

    from autoreport.gui.theme import get_theme_colors

    colors = get_theme_colors()
    text = sci.text()
    command_style = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, text.index("section")))
    # '\section' tokens use the tex_command color; surrounding plain text does not.
    assert command_style.name().lower() == colors["tex_command"].lower()
    plain = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, text.index("and")))
    assert plain.name().lower() == colors["editor_fg"].lower()


def test_tex_keyword_commands_get_keyword_color(qtbot):
    r"""\begin, \end, \usepackage etc. render in tex_keyword color.

    VSCode scopes \begin, \end as keyword.control.tex (keyword purple/pink)
    while \section, \textbf are support.function.general.tex (function gold).
    """
    from PyQt6.Qsci import QsciLexerTeX, QsciScintilla

    from autoreport.gui.scintilla_utils import (
        attach_tex_post_styling,
        configure_lexer_colors,
    )

    sci = QsciScintilla()
    qtbot.addWidget(sci)
    lexer = QsciLexerTeX(sci)
    sci.setLexer(lexer)
    configure_lexer_colors(lexer)
    attach_tex_post_styling(sci)

    sci.setText(r"\begin{document}\n\section{Hi}\n\end{document}")
    # setText triggers the attached textChanged -> command coloring.

    from autoreport.gui.theme import get_theme_colors

    colors = get_theme_colors()
    text = sci.text()

    # \begin → keyword color
    begin_style = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, text.index("begin")))
    assert begin_style.name().lower() == colors["tex_keyword"].lower()

    # \end → keyword color
    end_style = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, text.index("end", text.index("section"))))
    assert end_style.name().lower() == colors["tex_keyword"].lower()

    # \section → still function color (not keyword)
    sec_style = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, text.index("section")))
    assert sec_style.name().lower() == colors["tex_command"].lower()


def test_markdown_hr_color_matches_vscode(qtbot):
    """Horizontal rule color should differ between dark and light modes.

    VSCode dark-modern uses comment green (#6A9955); light-modern uses
    a lighter green (#008000) to match the light-mode comment token.
    """
    from PyQt6.Qsci import QsciLexerMarkdown, QsciScintilla

    from autoreport.gui.scintilla_utils import configure_lexer_colors

    sci = QsciScintilla()
    qtbot.addWidget(sci)
    lexer = QsciLexerMarkdown(sci)
    sci.setLexer(lexer)
    configure_lexer_colors(lexer)

    sci.setText("text\n\n---\n")
    sci.SendScintilla(sci.SCI_COLOURISE, 0, -1)

    from autoreport.gui.theme import get_theme_colors

    colors = get_theme_colors()
    text = sci.text()
    # "---" after a blank line → horizontal-rule style.
    hr_pos = text.index("---")
    hr_color = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, hr_pos)).name()
    assert hr_color.lower() == colors["md_hr"].lower()


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


def test_tex_commands_inside_math_mode_keep_command_color(qtbot):
    r"""\mathrm, \frac, \sqrt inside $...$ retain tex_command color.

    After the ordering fix (math colour applied first, then command colour
    on top), commands inside math mode must show tex_command (gold/brown),
    not tex_math (orange/red).  This matches VSCode where support.function
    scoping applies inside string.other.math.
    """
    from PyQt6.Qsci import QsciLexerTeX, QsciScintilla

    from autoreport.gui.scintilla_utils import (
        attach_tex_post_styling,
        configure_lexer_colors,
    )

    sci = QsciScintilla()
    qtbot.addWidget(sci)
    lexer = QsciLexerTeX(sci)
    sci.setLexer(lexer)
    configure_lexer_colors(lexer)
    attach_tex_post_styling(sci)

    sci.setText(r"$\mathrm{p}^+\mathrm{n}$ and $\frac{a}{b}$")
    # setText fires textChanged → post-styling.

    from autoreport.gui.theme import get_theme_colors

    colors = get_theme_colors()
    text = sci.text()

    # First \mathrm → tex_command (function gold), not tex_math
    r1 = text.index("mathrm")
    s1 = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, r1))
    assert s1.name().lower() == colors["tex_command"].lower(), (
        f"\\mathrm inside $…$ should be tex_command, got {s1.name()}"
    )

    # Second \mathrm → tex_command
    r2 = text.index("mathrm", r1 + 1)
    s2 = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, r2))
    assert s2.name().lower() == colors["tex_command"].lower()

    # \frac → tex_command
    frac_pos = text.index("frac")
    s3 = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, frac_pos))
    assert s3.name().lower() == colors["tex_command"].lower()

    # Dollar signs (math delimiters) → tex_math (Symbol style)
    dollar_pos = text.index("$")
    s4 = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, dollar_pos))
    assert s4.name().lower() == colors["tex_math"].lower()


def test_tex_comment_overrides_everything(qtbot):
    r"""% comment lines should be solid green — math and commands inside
    comments must not show their own colours.

    The comment post-styling runs last, so it must overwrite any math or
    command styling previously applied to the same range.
    """
    from PyQt6.Qsci import QsciLexerTeX, QsciScintilla

    from autoreport.gui.scintilla_utils import (
        attach_tex_post_styling,
        configure_lexer_colors,
    )

    sci = QsciScintilla()
    qtbot.addWidget(sci)
    lexer = QsciLexerTeX(sci)
    sci.setLexer(lexer)
    configure_lexer_colors(lexer)
    attach_tex_post_styling(sci)

    sci.setText(r"real content\n% \textbf{not bold} $E=mc^2$ \begin{not}\nmore text")
    # setText fires textChanged → post-styling.

    from autoreport.gui.theme import get_theme_colors

    colors = get_theme_colors()
    text = sci.text()

    # Everything after % on the comment line should be comment green.
    pct = text.index("%")
    # \textbf inside comment
    tb = text.index("textbf")
    assert tb > pct  # sanity: inside comment
    s_tb = lexer.color(sci.SendScintilla(sci.SCI_GETSTYLEAT, tb))
    # Virtual style indices have no description(); color() returns the QColor
    # set via SCI_STYLESETFORE.  We compare the actual foreground colour.
    fg_tb = sci.SendScintilla(sci.SCI_STYLEGETFORE,
                              sci.SendScintilla(sci.SCI_GETSTYLEAT, tb))
    expected_fg = QColor(colors["syntax_comment"])
    assert QColor(
        fg_tb & 0xFF, (fg_tb >> 8) & 0xFF, (fg_tb >> 16) & 0xFF
    ).name().lower() == expected_fg.name().lower(), (
        "\\textbf inside comment should be comment colour"
    )

    # $E=mc^2$ inside comment
    math_in_comment = text.index("E=mc")
    s_math = sci.SendScintilla(sci.SCI_STYLEGETFORE,
                               sci.SendScintilla(sci.SCI_GETSTYLEAT, math_in_comment))
    assert QColor(
        s_math & 0xFF, (s_math >> 8) & 0xFF, (s_math >> 16) & 0xFF
    ).name().lower() == expected_fg.name().lower(), (
        "$math$ inside comment should be comment colour"
    )

    # \begin inside comment
    begin_in_comment = text.index("begin")
    s_begin = sci.SendScintilla(sci.SCI_STYLEGETFORE,
                                sci.SendScintilla(sci.SCI_GETSTYLEAT, begin_in_comment))
    assert QColor(
        s_begin & 0xFF, (s_begin >> 8) & 0xFF, (s_begin >> 16) & 0xFF
    ).name().lower() == expected_fg.name().lower(), (
        "\\begin inside comment should be comment colour"
    )
