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


def _set_style_if_present(lexer: QsciLexer, style_name: str, color: str) -> None:
    style = getattr(lexer, style_name, None)
    if style is None:
        return
    try:
        lexer.setColor(QColor(color), style)
    except Exception:
        return


def _apply_vscode_token_palette(lexer: QsciLexer) -> None:
    """Apply VSCode-like token palette with separate dark/light variants."""
    c = get_theme_colors()
    palette = {
        "keyword": c["syntax_keyword"],
        "string": c["syntax_string"],
        "comment": c["syntax_comment"],
        "number": c["syntax_number"],
        "operator": c["syntax_operator"],
        "identifier": c["syntax_identifier"],
        "class_name": c["syntax_class_name"],
        "function": c["syntax_function"],
    }

    # Python
    _set_style_if_present(lexer, "Keyword", palette["keyword"])
    _set_style_if_present(lexer, "DoubleQuotedString", palette["string"])
    _set_style_if_present(lexer, "SingleQuotedString", palette["string"])
    _set_style_if_present(lexer, "TripleDoubleQuotedString", palette["string"])
    _set_style_if_present(lexer, "TripleSingleQuotedString", palette["string"])
    _set_style_if_present(lexer, "Comment", palette["comment"])
    _set_style_if_present(lexer, "CommentBlock", palette["comment"])
    _set_style_if_present(lexer, "Number", palette["number"])
    _set_style_if_present(lexer, "Operator", palette["operator"])
    _set_style_if_present(lexer, "Identifier", palette["identifier"])
    _set_style_if_present(lexer, "ClassName", palette["class_name"])
    _set_style_if_present(lexer, "FunctionMethodName", palette["function"])
    _set_style_if_present(lexer, "Decorator", palette["class_name"])

    # JSON / YAML / Markdown / TeX lexers share some generic style names.
    _set_style_if_present(lexer, "Default", palette["identifier"])
    _set_style_if_present(lexer, "KeywordSet2", palette["keyword"])
    _set_style_if_present(lexer, "CommentLine", palette["comment"])
    _set_style_if_present(lexer, "Comment", palette["comment"])
    _set_style_if_present(lexer, "String", palette["string"])
    _set_style_if_present(lexer, "Number", palette["number"])
    _set_style_if_present(lexer, "Operator", palette["operator"])


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
    # Set paper + font without forcing a single foreground color, otherwise
    # lexer token colors are flattened and syntax highlighting disappears.
    lexer.setDefaultPaper(paper)
    lexer.setPaper(paper)
    lexer.setDefaultFont(font)
    # Apply to all styles via style=-1 to avoid per-style metric drift/overlap.
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
