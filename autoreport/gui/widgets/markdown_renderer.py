"""Markdown → Qt Rich Text renderer for agent messages.

Converts a subset of Markdown to HTML that Qt's QLabel rich text can display.
Uses Python-Markdown for parsing, then post-processes for Qt compatibility.
"""

import re
from html.parser import HTMLParser
from typing import Any
from xml.etree import ElementTree

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from ..theme import get_theme_colors


_LONG_TOKEN_RE = re.compile(r"\S{18,}")


def _with_soft_breaks(text: str | None, *, chunk_size: int = 12) -> str | None:
    """Insert break opportunities for Qt rich text table cells.

    QLabel's rich-text table engine ignores modern CSS such as
    ``overflow-wrap:anywhere`` for long unbroken tokens. A zero-width space is
    a real Unicode break opportunity that keeps the rendered text unchanged
    while allowing table cells to shrink to the available message width.
    """
    if not text:
        return text

    def _break_token(match: re.Match[str]) -> str:
        token = match.group(0)
        return "\u200b".join(
            token[i:i + chunk_size] for i in range(0, len(token), chunk_size)
        )

    return _LONG_TOKEN_RE.sub(_break_token, text)


def _soft_break_element_text(element: ElementTree.Element) -> None:
    element.text = _with_soft_breaks(element.text)
    for child in list(element):
        _soft_break_element_text(child)
        child.tail = _with_soft_breaks(child.tail)


def _first_table_column_count(table: ElementTree.Element) -> int:
    for row in table.iter("tr"):
        count = sum(1 for child in list(row) if child.tag in {"th", "td"})
        if count:
            return count
    return 1


class _QtCompatTreeprocessor(Treeprocessor):
    """Adjust HTML tree for Qt rich text compatibility."""

    def run(self, root: ElementTree.Element) -> Any:
        c = get_theme_colors()
        code_bg = c["card"]
        code_border = c["border"]
        code_fg = c["editor_fg"]
        inline_code_bg = c["bubble_bg"]
        inline_code_fg = c["editor_fg"]
        accent = c["buttonBlue"]
        muted = c["muted"]
        th_bg = c["markdown_table_header_bg"]

        # Qt rich text doesn't support <pre>, convert to styled <div>
        for pre in root.iter("pre"):
            pre.tag = "div"
            pre.set("style", f"background-color: {code_bg}; border: 1px solid {code_border}; "
                    "border-radius: 6px; padding: 8px 12px; margin: 4px 0; "
                    "font-family: 'Cascadia Code', 'SF Mono', 'Consolas', monospace; "
                    "font-size: 12px; white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; max-width: 100%;")

            for code in pre.iter("code"):
                code.tag = "span"
                code.set("style", f"color: {code_fg}; font-family: inherit; font-size: inherit; white-space: pre-wrap; word-wrap: break-word;")

        # Qt rich text doesn't support <h1>-<h6>, convert to styled <p>
        for i in range(1, 7):
            for h in root.iter(f"h{i}"):
                h.tag = "p"
                sizes = {1: 20, 2: 16, 3: 14, 4: 13, 5: 12, 6: 11}
                weight = "bold" if i <= 4 else "normal"
                h.set("style", f"font-size: {sizes[i]}px; font-weight: {weight}; "
                      f"margin: 0.8em 0 0.4em 0;")

        # Style <blockquote>
        for bq in root.iter("blockquote"):
            bq.set("style", f"border-left: 3px solid {accent}; padding-left: 12px; "
                   f"margin: 8px 0; color: {muted};")

        # Style <code> (inline)
        for code in root.iter("code"):
            if code.get("style") is None:
                code.tag = "span"
                code.set("style", f"background-color: {inline_code_bg}; border: 1px solid {code_border}; "
                        "border-radius: 4px; padding: 1px 4px; "
                        "font-family: 'Cascadia Code', 'SF Mono', 'Consolas', monospace; "
                        f"font-size: 12px; color: {inline_code_fg};")

        # Table styling
        for table in root.iter("table"):
            column_count = max(1, _first_table_column_count(table))
            column_width = f"{max(1, int(100 / column_count))}%"
            table.set("border", "1")
            table.set("cellpadding", "6")
            table.set("cellspacing", "0")
            table.set("width", "100%")
            table.set(
                "style",
                "margin: 8px 0; width: 100%; max-width: 100%; "
                "table-layout: fixed; overflow-wrap: anywhere; word-wrap: break-word;",
            )
            for row in table.iter("tr"):
                for cell in list(row):
                    if cell.tag in {"th", "td"}:
                        cell.set("width", column_width)
                        _soft_break_element_text(cell)
        for th in root.iter("th"):
            th.set("bgcolor", th_bg)
            th.set("style", "font-weight: bold; word-wrap: break-word; overflow-wrap: anywhere;")
        for td in root.iter("td"):
            td.set("style", "word-wrap: break-word; overflow-wrap: anywhere;")

        return root


class QtCompatExtension(Extension):
    """Markdown extension for Qt rich text compatibility."""

    def extendMarkdown(self, md):  # noqa: N802
        md.treeprocessors.register(_QtCompatTreeprocessor(md), "qt_compat", 175)


_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_HTML_TABLE_RE = re.compile(r"(?is)<table\b.*?</table>")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")


def _separate_loose_list_blocks(text: str) -> str:
    """Make LLM-style "label\n- item" parse as a Markdown list.

    Python-Markdown follows the stricter rule that lists after a paragraph need
    a blank line. Chat models often omit it, while users still expect a list.
    """
    if not text:
        return text

    lines = text.splitlines(keepends=True)
    output: list[str] = []
    in_fence = False
    previous_content_line = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence

        is_list_line = bool(_LIST_MARKER_RE.match(line))
        previous_is_blank = previous_content_line.strip() == ""
        previous_is_list = bool(_LIST_MARKER_RE.match(previous_content_line))

        if (
            is_list_line
            and not in_fence
            and previous_content_line
            and not previous_is_blank
            and not previous_is_list
        ):
            output.append("\n")

        output.append(line)
        previous_content_line = line

    return "".join(output)


def _normalize_table_cell_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class _HTMLTableBlockParser(HTMLParser):
    """Extract table rows before Qt can render them as fixed-width tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[list[str], bool]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._row_has_header = False
        self._code_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
            self._row_has_header = False
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []
            if tag == "th":
                self._row_has_header = True
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")
        elif tag == "code" and self._cell is not None:
            self._cell.append("`")
            self._code_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "code" and self._cell is not None and self._code_depth:
            self._cell.append("`")
            self._code_depth -= 1
        elif tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(_normalize_table_cell_text("".join(self._cell)))
            self._cell = None
            self._code_depth = 0
        elif tag == "tr" and self._row is not None:
            if any(cell for cell in self._row):
                self.rows.append((self._row, self._row_has_header))
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _table_rows_to_markdown_blocks(
    headers: list[str] | None,
    rows: list[list[str]],
) -> str:
    if not rows:
        return ""

    output: list[str] = []
    for row_index, cells in enumerate(rows):
        if row_index:
            output.append("")

        if headers:
            for col_index, header in enumerate(headers):
                value = cells[col_index] if col_index < len(cells) else ""
                header_text = _with_soft_breaks(header) or ""
                value_text = _with_soft_breaks(value) or ""
                output.append(f"**{header_text}**: {value_text}")
        else:
            for cell in cells:
                value_text = _with_soft_breaks(cell) or ""
                if value_text:
                    output.append(f"- {value_text}")

    return "\n".join(output)


def _strip_html_tags(text: str) -> str:
    return _normalize_table_cell_text(re.sub(r"(?is)<[^>]+>", " ", text))


def _rewrite_html_tables_as_blocks(text: str) -> str:
    """Rewrite raw HTML tables to width-safe markdown blocks."""
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        parser = _HTMLTableBlockParser()
        table_html = match.group(0)
        parser.feed(table_html)
        if not parser.rows:
            return _with_soft_breaks(_strip_html_tags(table_html)) or ""

        first_row, first_row_is_header = parser.rows[0]
        headers = first_row if first_row_is_header else None
        rows = [row for row, _ in parser.rows[1:]] if first_row_is_header else [
            row for row, _ in parser.rows
        ]
        return _table_rows_to_markdown_blocks(headers, rows)

    return _HTML_TABLE_RE.sub(_replace, text)


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and not stripped.startswith("```")


def _rewrite_markdown_tables_as_blocks(text: str) -> str:
    """Rewrite pipe tables to width-safe markdown blocks.

    Qt QLabel's rich-text table layout can exceed the message column even with
    CSS/HTML width hints. Plain markdown paragraphs wrap reliably, so chat
    tables are rendered as repeated field blocks instead of HTML ``<table>``.
    """
    if not text:
        return text

    lines = text.splitlines()
    output: list[str] = []
    i = 0
    in_fence = False

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            in_fence = not in_fence
            output.append(line)
            i += 1
            continue

        if (
            not in_fence
            and i + 1 < len(lines)
            and _is_table_row(lines[i])
            and _TABLE_SEPARATOR_RE.match(lines[i + 1])
        ):
            headers = _split_table_row(lines[i])
            rows: list[list[str]] = []
            i += 2
            while i < len(lines) and _is_table_row(lines[i]):
                cells = _split_table_row(lines[i])
                if cells:
                    rows.append(cells)
                i += 1

            if output and output[-1].strip():
                output.append("")
            for row_index, cells in enumerate(rows):
                if row_index:
                    output.append("")
                for col_index, header in enumerate(headers):
                    value = cells[col_index] if col_index < len(cells) else ""
                    header_text = _with_soft_breaks(header) or ""
                    value_text = _with_soft_breaks(value) or ""
                    output.append(f"**{header_text}**: {value_text}")
            if rows:
                output.append("")
            continue

        output.append(line)
        i += 1

    return "\n".join(output)


def render_markdown(text: str) -> str:
    """Convert markdown text to Qt-compatible HTML."""
    md = markdown.Markdown(
        extensions=[
            "markdown.extensions.fenced_code",
            QtCompatExtension(),
        ],
        tab_length=2,
    )
    normalized = _rewrite_html_tables_as_blocks(text)
    normalized = _rewrite_markdown_tables_as_blocks(normalized)
    html = md.convert(_separate_loose_list_blocks(normalized))

    # Post-process: remove paragraph tags wrapping code blocks
    html = re.sub(r'<p>\s*(<div style="background-color)', r'\1', html)
    html = re.sub(r'(</div>)\s*</p>', r'\1', html)

    # Wrap in a div for proper rendering
    root_fg = get_theme_colors()["editor_fg"]
    return (
        "<div style=\"white-space: normal; overflow-wrap: anywhere; "
        f"word-wrap: break-word; word-break: break-word; color: {root_fg};\">{html}</div>"
    )
