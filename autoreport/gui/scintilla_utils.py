"""QScintilla editor styling utilities.

Provides consistent styling for all QScintilla editors including:
- Line numbers (margins)
- Theme colors
- Font configuration
"""

from PyQt6.Qsci import QsciLexer, QsciScintilla
from PyQt6.QtGui import QColor, QFont, QFontDatabase

from .theme import get_theme_colors

LINE_NUMBER_RIGHT_PADDING = 6
LINE_NUMBER_MARGIN_MIN_WIDTH = 26
# Extra blank space between line-number gutter and code text start.
CODE_TEXT_LEFT_MARGIN = 8
# Keep widest line number visually centered between editor edge and code start.
LINE_NUMBER_LEFT_PADDING = LINE_NUMBER_RIGHT_PADDING + CODE_TEXT_LEFT_MARGIN


def _code_font(size: int = 13) -> QFont:
    """Shared code font for editors and lexer tokens."""
    # Prefer fixed-pitch fonts only; mixed/fallback proportional glyph metrics can
    # cause horizontal overlap in Scintilla when lexer styles differ.
    preferred = ["Cascadia Mono", "Cascadia Code", "SF Mono", "Consolas", "Menlo", "Monaco"]
    available = set(QFontDatabase.families())
    family = next((name for name in preferred if name in available), "")
    font = QFont(family, size) if family else QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    font.setKerning(False)
    font.setItalic(False)
    return font


# Map lexer style *names* (QsciLexer.description()) to palette keys.
# Any style not listed falls back to the editor foreground. This matters
# because QScintilla lexers ship with hardcoded per-style colors meant for a
# light background — markdown's bright-magenta ``\\`` escapes, orange headers,
# JSON's neon cyan/purple, etc. Walking every style and defaulting the unknown
# ones to foreground neutralizes that crude rainbow so markdown/TeX/JSON/YAML
# stay as calm as VSCode instead of harsher than it.
_ACCENT_BY_NAME: dict[str, str] = {
    # Comments
    "Comment": "comment",
    "Comment block": "comment",
    "Comment line": "comment",
    "Line comment": "comment",
    "Block comment": "comment",
    # Strings (Python / JSON / YAML variants)
    "String": "string",
    "Double-quoted string": "string",
    "Single-quoted string": "string",
    "Triple single-quoted string": "string",
    "Triple double-quoted string": "string",
    "Double-quoted f-string": "string",
    "Single-quoted f-string": "string",
    "Triple single-quoted f-string": "string",
    "Triple double-quoted f-string": "string",
    "Unclosed string": "string",
    # Numbers (and JSON escape sequences like ``\n``)
    "Number": "number",
    "Escape sequence": "number",
    # Keywords
    "Keyword": "keyword",
    "JSON keyword": "keyword",
    "JSON-LD keyword": "keyword",
    "Document delimiter": "keyword",
    # Operators stay calm
    "Operator": "fg",
    # Structural keys (JSON properties / YAML keys): targeted soft blue
    "Property": "identifier",
    # Definitions
    "Class name": "class_name",
    "Function or method name": "function",
    "Decorator": "class_name",
    # Markdown — matches VSCode dark-modern / light-modern token colors.
    # Headings/bold keep their lexer bold via per-style font (see below).
    "Level 1 header": "md_heading",
    "Level 2 header": "md_heading",
    "Level 3 header": "md_heading",
    "Level 4 header": "md_heading",
    "Level 5 header": "md_heading",
    "Level 6 header": "md_heading",
    "Strong emphasis using double asterisks": "md_bold",
    "Strong emphasis using double underscores": "md_bold",
    "Code between backticks": "string",  # markup.inline.raw
    "Code between double backticks": "string",
    "Link": "md_link",
    "Horizontal rule": "muted",
    # Emphasis (italic), list items, block quotes, escapes → calm foreground;
    # structure is carried by the lexer's italic/bold, not by loud color.
}


def _apply_vscode_token_palette(lexer: QsciLexer) -> None:
    """Apply VSCode-like token palette with separate dark/light variants.

    Iterates *every* lexer style (by index) so none retain QScintilla's harsh
    built-in colors. Plain text, plain identifiers, prose and unrecognized
    markdown structures use the editor foreground — exactly like VSCode, where
    markdown source is nearly monochrome — while recognized code tokens get a
    VSCode accent. Variables/identifiers in Python render as foreground rather
    than cyan, so the body reads as calm gray with tasteful accents.
    """
    # Test doubles may not implement description(); nothing to theme then.
    if not hasattr(lexer, "description"):
        return

    c = get_theme_colors()
    palette = {
        "fg": c["editor_fg"],
        "muted": c["muted"],
        "keyword": c["syntax_keyword"],
        "string": c["syntax_string"],
        "comment": c["syntax_comment"],
        "number": c["syntax_number"],
        "operator": c["syntax_operator"],
        "identifier": c["syntax_identifier"],
        "class_name": c["syntax_class_name"],
        "function": c["syntax_function"],
        "md_heading": c["md_heading"],
        "md_bold": c["md_bold"],
        "md_link": c["md_link"],
    }
    fg = palette["fg"]

    # Lexer-level default color used for the STYLE_DEFAULT fallback.
    try:
        lexer.setDefaultColor(QColor(fg))
    except Exception:
        pass

    for style in range(128):
        name = lexer.description(style)
        if not name:  # lexers return "" past their last defined style
            break
        color = palette[_ACCENT_BY_NAME[name]] if name in _ACCENT_BY_NAME else fg
        try:
            lexer.setColor(QColor(color), style)
        except Exception:
            continue


def apply_scintilla_style(
    sci: QsciScintilla,
    object_name: str = "scintillaEditor",
    line_numbers: bool = True,
    margin_width: int | None = None,
    read_only: bool = False,
    content_bg: str | None = None,
) -> None:
    """Apply consistent styling to a QScintilla editor.

    Args:
        sci: The QScintilla widget to style
        object_name: Object name for CSS styling
        line_numbers: Whether to show line numbers in margin 1
        margin_width: Width in pixels for line number margin (None for auto)
        read_only: Whether the editor should be read-only
        content_bg: Optional editor content background override
    """
    c = get_theme_colors()
    paper_color = content_bg or c["editor_bg"]

    sci.setObjectName(object_name)
    sci.setUtf8(True)

    # Configure margin 1 (line numbers)
    if line_numbers:
        # Keep symbol margin disabled so the left side can be truly compact.
        sci.setMarginWidth(0, 0)
        sci.setMarginLineNumbers(1, True)
        # Calculate margin width based on line count
        if margin_width is None:
            line_count = sci.lines()
            # Calculate width needed for max line number
            char_width = sci.SendScintilla(sci.SCI_TEXTWIDTH, sci.STYLE_DEFAULT, b"8")
            digits = len(str(line_count))
            margin_width = max(
                LINE_NUMBER_MARGIN_MIN_WIDTH,
                char_width * digits + LINE_NUMBER_LEFT_PADDING + LINE_NUMBER_RIGHT_PADDING,
            )
        sci.setMarginWidth(1, margin_width)

    # Keep gutter distinct and give the caret a deterministic theme color.
    sci.setMarginsBackgroundColor(QColor(c["editor_margin"]))
    sci.setMarginsForegroundColor(QColor(c["muted"]))
    sci.setCaretForegroundColor(QColor(c["editor_caret_fg"]))
    sci.setColor(QColor(c["editor_fg"]))
    sci.setPaper(QColor(paper_color))
    sci.setFont(_code_font())
    # Decouple gutter spacing from code start position so we can keep line
    # numbers visually closer to the left border while giving code more room.
    sci.SendScintilla(sci.SCI_SETMARGINLEFT, 0, CODE_TEXT_LEFT_MARGIN)
    # Adaptive line width: wrap long lines to the editor viewport.
    sci.setWrapMode(QsciScintilla.WrapMode.WrapWord)
    sci.setWrapVisualFlags(QsciScintilla.WrapVisualFlag.WrapFlagNone)
    sci.setWrapIndentMode(QsciScintilla.WrapIndentMode.WrapIndentSame)

    # Set read-only
    sci.setReadOnly(read_only)

    # Apply stylesheet
    sci.setStyleSheet(f"""
        QsciScintilla#{object_name} {{
            background-color: {paper_color};
            color: {c["editor_fg"]};
            border: none;
        }}
        QsciScintilla#{object_name}::margin {{
            background-color: {c["editor_margin"]};
            color: {c["muted"]};
        }}
    """)


def update_margin_width(sci: QsciScintilla) -> None:
    """Update margin width based on current line count.

    Args:
        sci: The QScintilla widget to update
    """
    line_count = sci.lines()
    char_width = sci.SendScintilla(sci.SCI_TEXTWIDTH, sci.STYLE_DEFAULT, b"8")
    digits = len(str(line_count))
    margin_width = max(
        LINE_NUMBER_MARGIN_MIN_WIDTH,
        char_width * digits + LINE_NUMBER_LEFT_PADDING + LINE_NUMBER_RIGHT_PADDING,
    )
    sci.setMarginWidth(1, margin_width)


def configure_lexer_colors(lexer: QsciLexer, paper_color: str | None = None) -> None:
    """Configure a QScintilla lexer with theme colors.

    Args:
        lexer: The QLexer instance to configure
        paper_color: Optional background color override for lexer styles
    """
    c = get_theme_colors()
    paper = QColor(paper_color or c["editor_bg"])
    font = _code_font()
    # Set paper + default font without forcing a single foreground color,
    # otherwise lexer token colors are flattened and syntax highlighting dies.
    lexer.setDefaultPaper(paper)
    lexer.setPaper(paper)
    lexer.setDefaultFont(font)
    if hasattr(lexer, "description"):
        # Force a uniform monospace family/size on every style (avoids the
        # per-style metric drift/overlap that mismatched fonts cause), but
        # PRESERVE each style's own weight/italic so markdown keeps its bold
        # headers and italic emphasis — exactly how VSCode renders it.
        for style in range(128):
            if not lexer.description(style):
                break
            style_font = QFont(lexer.font(style))
            style_font.setFamily(font.family())
            style_font.setPointSize(font.pointSize())
            style_font.setFixedPitch(True)
            style_font.setStyleHint(QFont.StyleHint.Monospace)
            style_font.setKerning(False)
            lexer.setFont(style_font, style)
            lexer.setPaper(paper, style)
    else:
        # Test doubles: no per-style API — fall back to global assignment.
        lexer.setFont(font, -1)
        lexer.setPaper(paper, -1)
    _apply_vscode_token_palette(lexer)


def create_scintilla(
    lexer: QsciLexer | None = None,
    object_name: str = "scintillaEditor",
    line_numbers: bool = True,
    read_only: bool = False,
    content_bg: str | None = None,
) -> QsciScintilla:
    """Create a QScintilla editor with consistent styling.

    Args:
        lexer: Optional lexer to apply (e.g., QsciLexerPython)
        object_name: Object name for CSS styling
        line_numbers: Whether to show line numbers
        read_only: Whether the editor should be read-only
        content_bg: Optional editor content background override

    Returns:
        Configured QsciScintilla widget
    """
    sci = QsciScintilla()
    apply_scintilla_style(
        sci,
        object_name,
        line_numbers,
        read_only=read_only,
        content_bg=content_bg,
    )

    if lexer:
        sci.setLexer(lexer)
        configure_lexer_colors(lexer, paper_color=content_bg)

    return sci
