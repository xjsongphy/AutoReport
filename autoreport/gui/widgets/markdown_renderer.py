"""Markdown → Qt Rich Text renderer for agent messages.

Converts a subset of Markdown to HTML that Qt's QLabel rich text can display.
Uses Python-Markdown for parsing, then post-processes for Qt compatibility.
"""

import re
from typing import Any
from xml.etree import ElementTree

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from ..theme import get_theme_colors


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
            table.set("border", "1")
            table.set("cellpadding", "6")
            table.set("cellspacing", "0")
            table.set("style", "margin: 8px 0; width: 100%; table-layout: fixed;")
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


def render_markdown(text: str) -> str:
    """Convert markdown text to Qt-compatible HTML."""
    md = markdown.Markdown(
        extensions=[
            "markdown.extensions.fenced_code",
            "markdown.extensions.tables",
            QtCompatExtension(),
        ],
        tab_length=2,
    )
    html = md.convert(text)

    # Post-process: remove paragraph tags wrapping code blocks
    html = re.sub(r'<p>\s*(<div style="background-color)', r'\1', html)
    html = re.sub(r'(</div>)\s*</p>', r'\1', html)

    # Wrap in a div for proper rendering
    root_fg = get_theme_colors()["editor_fg"]
    return (
        "<div style=\"white-space: normal; overflow-wrap: anywhere; "
        f"word-wrap: break-word; word-break: break-word; color: {root_fg};\">{html}</div>"
    )
