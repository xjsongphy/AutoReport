"""QScintilla editor styling utilities.

Provides consistent styling for all QScintilla editors including:
- Line numbers (margins)
- Theme colors
- Font configuration
"""

import re

from loguru import logger

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
    # TeX — QScintilla lumps \commands into "Text", so "Command" is unused by
    # the lexer; we repurpose it as the command-color bucket (VSCode scopes
    # \commands as support.function.general.tex, i.e. the function color) and
    # fill it via post-processing (apply_tex_command_coloring).
    "Command": "function",
    # Markdown — matches VSCode dark-modern / light-modern token colors.
    # markup.heading / markup.bold (bold kept via per-style font below).
    "Level 1 header": "md_heading",
    "Level 2 header": "md_heading",
    "Level 3 header": "md_heading",
    "Level 4 header": "md_heading",
    "Level 5 header": "md_heading",
    "Level 6 header": "md_heading",
    "Strong emphasis using double asterisks": "md_bold",
    "Strong emphasis using double underscores": "md_bold",
    # markup.inline.raw (inline `code`) -> string orange.
    "Code between backticks": "string",
    "Code between double backticks": "string",
    # punctuation.definition.list / quote markers.
    "Unordered list item": "md_list",
    "Ordered list item": "md_list",
    "Block quote": "md_quote",
    # Everything else (links, horizontal rule, escapes, emphasis, code blocks,
    # prose) -> foreground. VSCode's themes define NO token color for markdown
    # links, so they render as plain foreground (the clickable blue is a
    # separate editor decoration, not token coloring).
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
        "md_list": c["md_list"],
        "md_quote": c["md_quote"],
    }
    fg = palette["fg"]

    # Lexer-level default color used for the STYLE_DEFAULT fallback.
    try:
        lexer.setDefaultColor(QColor(fg))
    except Exception as e:
        logger.debug("Scintilla lexer default color failed: {}", e)

    for style in range(128):
        name = lexer.description(style)
        if not name:  # lexers return "" past their last defined style
            break
        color = palette[_ACCENT_BY_NAME[name]] if name in _ACCENT_BY_NAME else fg
        try:
            lexer.setColor(QColor(color), style)
        except Exception as e:
            logger.debug("Scintilla lexer color for style {} failed: {}", style, e)
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


# --- TeX command coloring ------------------------------------------------
# QScintilla's TeX lexer lumps ``\commands`` together with body text and math
# into a single "Text" style, so it cannot color commands. VSCode's LaTeX
# grammar scopes ``\command`` as ``support.function.general.tex`` (the function
# token color). We fill the lexer's unused "Command" style with that color and
# re-style every ``\<name>`` sequence into it after the lexer.
_TEX_COMMAND = re.compile(r"\\[a-zA-Z@]+")


def _char_to_byte_offsets(text: str) -> list[int]:
    """UTF-8 byte offset of each character (Scintilla works in byte positions)."""
    offsets = [0]
    extend = offsets.append
    for ch in text:
        extend(offsets[-1] + len(ch.encode("utf-8")))
    return offsets


def _find_style_index(lexer: QsciLexer, name: str) -> int | None:
    """Index of the lexer style whose description equals ``name``."""
    if not hasattr(lexer, "description"):
        return None
    for style in range(128):
        desc = lexer.description(style)
        if not desc:
            break
        if desc == name:
            return style
    return None


def apply_tex_command_coloring(sci: QsciScintilla) -> None:
    """Color LaTeX ``\\command`` sequences like VSCode (function color).

    Runs after the lexer; re-run on every edit (see
    ``attach_tex_command_coloring``).
    """
    lexer = sci.lexer()
    if lexer is None or "TeX" not in type(lexer).__name__:
        return
    command_style = _find_style_index(lexer, "Command")
    if command_style is None:
        return

    sci.SendScintilla(sci.SCI_COLOURISE, 0, -1)
    text = sci.text()
    if "\\" not in text:
        return

    byte_off = _char_to_byte_offsets(text)
    for m in _TEX_COMMAND.finditer(text):
        bstart = byte_off[m.start()]
        blen = byte_off[m.end()] - bstart
        if blen <= 0:
            continue
        sci.SendScintilla(sci.SCI_STARTSTYLING, bstart)
        sci.SendScintilla(sci.SCI_SETSTYLING, blen, command_style)


def attach_tex_command_coloring(sci: QsciScintilla) -> None:
    """Color ``\\command`` sequences now and on every text change."""
    apply_tex_command_coloring(sci)
    sci.textChanged.connect(lambda: apply_tex_command_coloring(sci))


# --- Markdown fenced-code highlighting -----------------------------------
# VSCode embeds language grammars inside ```lang fenced blocks (e.g. inside a
# ```python block it runs the Python grammar), which is where markdown gets
# most of its non-blue color. QScintilla's markdown lexer styles the whole
# block as one "Code block", so we post-process: run the matching sub-lexer on
# each block's content and copy its token colors onto free style indices.
_FENCE = re.compile(
    r"(?ms)^(?P<fence>```|~~~)[ \t]*(?P<lang>[\w+-]*)[^\n]*\n"
    r"(?P<content>.*?)^(?P=fence)[ \t]*$"
)
_FENCE_LEXERS = {
    "python": "QsciLexerPython", "py": "QsciLexerPython",
    "json": "QsciLexerJSON",
    "yaml": "QsciLexerYAML", "yml": "QsciLexerYAML",
    "tex": "QsciLexerTeX", "latex": "QsciLexerTeX",
    "bibtex": "QsciLexerBibTeX",
}
_SUB_LEXER_CACHE: dict[str, tuple[QsciScintilla, QsciLexer]] = {}
_VIRTUAL_STYLES: dict[int, dict[str, int]] = {}  # id(sci) -> {color: style idx}
_VIRTUAL_START = 40
_VIRTUAL_MAX = 128


def _fence_sublexer(lang: str) -> tuple[QsciScintilla, QsciLexer] | None:
    """Cached off-screen sub-lexer for a fenced-block language, or None."""
    name = _FENCE_LEXERS.get(lang.lower())
    if name is None:
        return None
    if lang not in _SUB_LEXER_CACHE:
        mod = __import__("PyQt6.Qsci", fromlist=[name])
        cls = getattr(mod, name)
        sub = QsciScintilla()
        lx = cls(sub)
        sub.setLexer(lx)
        configure_lexer_colors(lx)
        _SUB_LEXER_CACHE[lang] = (sub, lx)
    return _SUB_LEXER_CACHE[lang]


def _virtual_style_for(sci: QsciScintilla, color_hex: str, font: QFont,
                       paper_hex: str) -> int:
    """Allocate (or reuse) a free style index colored ``color_hex`` on ``sci``."""
    cache = _VIRTUAL_STYLES.setdefault(id(sci), {})
    if color_hex in cache:
        return cache[color_hex]
    idx = _VIRTUAL_START + len(cache)
    if idx >= _VIRTUAL_MAX:
        return 0  # exhausted -> fall back to default
    fg = QColor(color_hex)
    sci.SendScintilla(sci.SCI_STYLESETFORE, idx, fg.red() | (fg.green() << 8) | (fg.blue() << 16))
    bg = QColor(paper_hex)
    sci.SendScintilla(sci.SCI_STYLESETBACK, idx, bg.red() | (bg.green() << 8) | (bg.blue() << 16))
    sci.SendScintilla(sci.SCI_STYLESETFONT, idx, font.family().encode("utf-8"))
    sci.SendScintilla(sci.SCI_STYLESETSIZE, idx, font.pointSize())
    sci.SendScintilla(sci.SCI_STYLESETBOLD, idx, 0)
    sci.SendScintilla(sci.SCI_STYLESETITALIC, idx, 0)
    cache[color_hex] = idx
    return idx


_HEADING = re.compile(r"(?m)^(#{1,6})(\s+)(.*)$")


def apply_markdown_post_styling(sci: QsciScintilla) -> None:
    """Post-process markdown to match VSCode where QScintilla's lexer can't.

    Two things:
    * Heading text — the lexer only colors the ``#`` marker; VSCode colors the
      whole heading line (markup.heading). We restyle the heading text into the
      lexer's header style (color + bold).
    * Fenced code blocks — VSCode embeds the language grammar inside ```lang
      blocks; we run the matching sub-lexer and copy its token colors onto free
      style indices so code is multi-colored, not flat.

    Runs after the lexer; re-run on every edit (see
    ``attach_markdown_post_styling``).
    """
    lexer = sci.lexer()
    if lexer is None or "Markdown" not in type(lexer).__name__:
        return
    sci.SendScintilla(sci.SCI_COLOURISE, 0, -1)
    text = sci.text()
    byte_off = _char_to_byte_offsets(text)

    # --- Heading text -> header style (whole line, like VSCode) ---
    header_style = _find_style_index(lexer, "Level 1 header")
    if header_style is not None:
        for m in _HEADING.finditer(text):
            bstart = byte_off[m.start(2)]  # from the space after #'s to line end
            blen = byte_off[m.end()] - bstart
            if blen > 0:
                sci.SendScintilla(sci.SCI_STARTSTYLING, bstart)
                sci.SendScintilla(sci.SCI_SETSTYLING, blen, header_style)

    # --- Fenced code blocks -> embedded language highlighting ---
    if "```" not in text and "~~~" not in text:
        return
    colors = get_theme_colors()
    paper = colors["editor_bg"]
    font = _code_font()

    for m in _FENCE.finditer(text):
        pair = _fence_sublexer(m.group("lang"))
        if pair is None:
            continue
        sub, sublx = pair
        content = m.group("content")
        sub.setText(content)
        sub.SendScintilla(sub.SCI_COLOURISE, 0, -1)

        base = byte_off[m.start("content")]  # content's UTF-8 bytes == doc bytes here
        clen = len(content.encode("utf-8"))
        style_color: dict[int, str] = {}

        # Build maximal runs of identical token color over the block's bytes.
        runs: list[tuple[int, int, str]] = []
        cur_color = ""
        cur_start = 0
        for k in range(clen):
            s = sub.SendScintilla(sub.SCI_GETSTYLEAT, k)
            c = style_color.get(s)
            if c is None:
                c = sublx.color(s).name()
                style_color[s] = c
            if c != cur_color:
                if cur_color:
                    runs.append((cur_start, k, cur_color))
                cur_color, cur_start = c, k
        if cur_color:
            runs.append((cur_start, clen, cur_color))

        for rs, re_, col in runs:
            vidx = _virtual_style_for(sci, col, font, paper)
            sci.SendScintilla(sci.SCI_STARTSTYLING, base + rs)
            sci.SendScintilla(sci.SCI_SETSTYLING, re_ - rs, vidx)


def attach_markdown_post_styling(sci: QsciScintilla) -> None:
    """Apply markdown post-styling now and on every text change."""
    apply_markdown_post_styling(sci)
    sci.textChanged.connect(lambda: apply_markdown_post_styling(sci))


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
