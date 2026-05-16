"""QScintilla editor styling utilities.

Provides consistent styling for all QScintilla editors including:
- Line numbers (margins)
- Theme colors
- Font configuration
"""

from PyQt6.Qsci import QsciScintilla, QsciLexer
from PyQt6.QtGui import QColor, QFont
from loguru import logger

from .theme import get_theme_colors


def apply_scintilla_style(
    sci: QsciScintilla,
    object_name: str = "scintillaEditor",
    line_numbers: bool = True,
    margin_width: int | None = None,
    read_only: bool = False,
) -> None:
    """Apply consistent styling to a QScintilla editor.

    Args:
        sci: The QScintilla widget to style
        object_name: Object name for CSS styling
        line_numbers: Whether to show line numbers in margin 1
        margin_width: Width in pixels for line number margin (None for auto)
        read_only: Whether the editor should be read-only
    """
    c = get_theme_colors()

    sci.setObjectName(object_name)
    sci.setUtf8(True)

    # Configure margin 1 (line numbers)
    if line_numbers:
        sci.setMarginLineNumbers(1, True)
        # Calculate margin width based on line count
        if margin_width is None:
            line_count = sci.lines()
            # Calculate width needed for max line number
            char_width = sci.textWidth(QsciScintilla.TextWidthStyle.STYLE_DEFAULT, "8")
            digits = len(str(line_count))
            # Add padding
            margin_width = max(30, char_width * digits + 12)
        sci.setMarginWidth(1, margin_width)

    # Set margin colors - use a darker background for contrast
    sci.setMarginsBackgroundColor(QColor(c["editor_margin"]))
    sci.setMarginsForegroundColor(QColor(c["muted"]))

    # Set read-only
    sci.setReadOnly(read_only)

    # Apply stylesheet
    sci.setStyleSheet(f"""
        QsciScintilla#{object_name} {{
            background-color: {c["editor_bg"]};
            color: {c["fg"]};
            border: none;
            font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
            font-size: 13px;
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
    char_width = sci.textWidth(QsciScintilla.TextWidthStyle.STYLE_DEFAULT, "8")
    digits = len(str(line_count))
    margin_width = max(30, char_width * digits + 12)
    sci.setMarginWidth(1, margin_width)


def configure_lexer_colors(lexer: QsciLexer) -> None:
    """Configure a QScintilla lexer with theme colors.

    Args:
        lexer: The QLexer instance to configure
    """
    c = get_theme_colors()
    lexer.setColor(QColor(c["fg"]))
    lexer.setPaper(QColor(c["editor_bg"]))


def create_scintilla(
    lexer: QsciLexer | None = None,
    object_name: str = "scintillaEditor",
    line_numbers: bool = True,
    read_only: bool = False,
) -> QsciScintilla:
    """Create a QScintilla editor with consistent styling.

    Args:
        lexer: Optional lexer to apply (e.g., QsciLexerPython)
        object_name: Object name for CSS styling
        line_numbers: Whether to show line numbers
        read_only: Whether the editor should be read-only

    Returns:
        Configured QsciScintilla widget
    """
    sci = QsciScintilla()
    apply_scintilla_style(sci, object_name, line_numbers, read_only=read_only)

    if lexer:
        sci.setLexer(lexer)
        configure_lexer_colors(lexer)

    return sci
