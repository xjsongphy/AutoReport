"""Markdown → Qt Rich Text renderer for agent messages.

Converts a subset of Markdown to HTML that Qt's QLabel rich text can display.
Uses Python-Markdown for parsing, then post-processes for Qt compatibility.
"""

import re
from typing import Any

import markdown
from markdown.extensions import Extension
from markdown.postprocessors import Postprocessor
from markdown.treeprocessors import Treeprocessor
from xml.etree import ElementTree as etree


class _QtCompatTreeprocessor(Treeprocessor):
    """Adjust HTML tree for Qt rich text compatibility."""

    def run(self, root: etree.Element) -> Any:
        # Qt rich text doesn't support <pre>, convert to styled <div>
        for pre in root.iter("pre"):
            pre.tag = "div"
            pre.set("style", "background-color: #1e1e1e; border: 1px solid #3c3c3c; "
                    "border-radius: 6px; padding: 8px 12px; margin: 4px 0; "
                    "font-family: 'Cascadia Code', 'SF Mono', 'Consolas', monospace; "
                    "font-size: 12px; white-space: pre-wrap;")

            # Convert <code> inside <pre> to <span>
            for code in pre.iter("code"):
                code.tag = "span"
                code.set("style", "color: #cccccc; font-family: inherit; font-size: inherit;")

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
            bq.set("style", "border-left: 3px solid #58a6ff; padding-left: 12px; "
                   "margin: 8px 0; color: #8b949e;")

        # Style <code> (inline)
        for code in root.iter("code"):
            if code.get("style") is None:  # Skip pre-wrapped code that was already styled
                code.tag = "span"
                code.set("style", "background-color: #2a2a2a; border: 1px solid #3c3c3c; "
                        "border-radius: 4px; padding: 1px 4px; "
                        "font-family: 'Cascadia Code', 'SF Mono', 'Consolas', monospace; "
                        "font-size: 12px; color: #e6edf3;")

        # Qt rich text supports <table> HTML attributes but not border-collapse.
        # Use HTML attributes: border, cellpadding, cellspacing.
        for table in root.iter("table"):
            table.set("border", "1")
            table.set("cellpadding", "6")
            table.set("cellspacing", "0")
            table.set("style", "margin: 8px 0;")
        for th in root.iter("th"):
            th.set("bgcolor", "#252526")
            th.set("style", "font-weight: bold;")
        for td in root.iter("td"):
            td.set("style", "")

        return root


class QtCompatExtension(Extension):
    """Markdown extension for Qt rich text compatibility."""

    def extendMarkdown(self, md):
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
    return f"<div>{html}</div>"
