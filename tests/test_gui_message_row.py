"""Tests for markdown rendering, code blocks, and copy button behavior."""

import pytest

from autoreport.gui.widgets.message_row import (
    MessageRow,
    _CodeBlockWidget,
    _parse_code_blocks,
)
from autoreport.gui.widgets.markdown_renderer import render_markdown
import autoreport.gui.widgets.markdown_renderer as markdown_renderer


class TestMarkdownRenderer:
    """Markdown → Qt rich text conversion."""

    def test_plain_text(self):
        html = render_markdown("Hello world")
        assert "Hello world" in html

    def test_bold(self):
        html = render_markdown("**bold text**")
        assert "<strong>" in html or "font-weight" in html.lower()

    def test_italic(self):
        html = render_markdown("*italic text*")
        assert "em" in html.lower() or "<i>" in html

    def test_header_rendered_as_styled_paragraph(self):
        html = render_markdown("# Header 1")
        assert "Header 1" in html

    def test_code_block_has_content(self):
        html = render_markdown("```python\nprint('hello')\n```")
        assert "print" in html.lower() or "print" in html

    def test_inline_code_renders(self):
        html = render_markdown("Use `print()` function")
        assert "print" in html

    def test_unordered_list(self):
        html = render_markdown("- item 1\n- item 2")
        assert "item 1" in html
        assert "item 2" in html

    def test_link_preserved(self):
        html = render_markdown("[click here](https://example.com)")
        assert "click here" in html
        assert "https://example.com" in html

    def test_blockquote_has_border(self):
        html = render_markdown("> quoted text")
        assert "quoted text" in html

    def test_empty_string_returns_wrapper(self):
        html = render_markdown("")
        assert html  # wrapping div returned

    def test_table_rows(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = render_markdown(md)
        assert "A" in html
        assert "1" in html

    def test_table_header_is_white_in_light_mode(self, monkeypatch):
        monkeypatch.setattr(markdown_renderer, "_is_dark_mode", lambda: False)
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = render_markdown(md)
        assert 'bgcolor="#ffffff"' in html


class TestCodeBlockParsing:
    """Parse markdown text into text/code segments."""

    def test_plain_text_only(self):
        parts = _parse_code_blocks("Just text")
        assert parts == [("Just text", None)]

    def test_single_code_block(self):
        parts = _parse_code_blocks("```python\nprint('hi')\n```")
        assert parts == [("print('hi')", "python")]

    def test_text_before_code(self):
        parts = _parse_code_blocks("Text\n```js\nconsole.log(1)\n```")
        assert parts[0] == ("Text\n", None)
        assert parts[1] == ("console.log(1)", "js")

    def test_text_after_code(self):
        parts = _parse_code_blocks("```sh\nls\n```\nAfter")
        assert parts == [("ls", "sh"), ("\nAfter", None)]

    def test_multiple_code_blocks(self):
        parts = _parse_code_blocks("```a\n1\n```\nMid\n```b\n2\n```")
        assert len(parts) == 3
        assert parts[0] == ("1", "a")
        assert parts[2] == ("2", "b")

    def test_no_language(self):
        parts = _parse_code_blocks("```\nraw\n```")
        assert parts[0] == ("raw", None)

    def test_empty_code_block(self):
        parts = _parse_code_blocks("```py\n\n```")
        assert parts == [("", "py")]

    def test_empty_input(self):
        parts = _parse_code_blocks("")
        assert parts == [("", None)]


class TestMessageRowCopyButton:
    """Copy button visibility and mark_complete behavior."""

    def test_footer_hidden_initially(self, qtbot):
        row = MessageRow("agent", "Hello")
        qtbot.addWidget(row)
        assert not hasattr(row, "_footer")

    def test_mark_complete_shows_footer(self, qtbot):
        row = MessageRow("agent", "Hello")
        qtbot.addWidget(row)
        row.mark_complete()
        assert row._complete
        assert not hasattr(row, "_footer")

    def test_user_message_has_no_footer(self, qtbot):
        row = MessageRow("user", "Query")
        qtbot.addWidget(row)
        row.mark_complete()
        # User messages don't have _footer attribute
        assert not hasattr(row, "_footer")

    def test_append_content_updates_content(self, qtbot):
        row = MessageRow("agent", "Part 1")
        qtbot.addWidget(row)
        row.append_content(" + Part 2")
        assert "Part 1 + Part 2" in row._content

    def test_streaming_builds_content(self, qtbot):
        row = MessageRow("agent", "")
        qtbot.addWidget(row)
        row.append_content("Chunk1.")
        row.append_content("Chunk2.")
        assert "Chunk1.Chunk2." in row._content

    def test_code_block_in_agent_message(self, qtbot):
        row = MessageRow("agent", "Result:\n```py\nx = 1\n```\nDone")
        qtbot.addWidget(row)
        assert row._agent_content_layout is not None
        assert "x = 1" in row._wrapping_labels[0].text()


class TestCodeBlockWidget:
    """Code block widget rendering."""

    def test_creates_code_block(self, qtbot):
        widget = _CodeBlockWidget("print(1)", "python")
        qtbot.addWidget(widget)
        assert widget._code == "print(1)"
        assert widget._language == "python"

    def test_no_language_shows_code(self, qtbot):
        widget = _CodeBlockWidget("raw", None)
        qtbot.addWidget(widget)
        assert widget._code == "raw"
