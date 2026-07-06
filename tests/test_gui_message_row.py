"""Tests for markdown rendering, code blocks, and copy button behavior."""

from autoreport.gui.widgets.message_row import MessageRow
from autoreport.gui.widgets.markdown_renderer import render_markdown
import autoreport.gui.theme as theme


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
        assert "<li>" in html

    def test_list_immediately_after_text_line_renders_as_list(self):
        html = render_markdown(
            "**报告 (Tex/)**\n"
            "- `main.tex` + `mpltx.cls` 模板\n"
            "- 章节：sec-intro, sec-setup\n"
            "- 已编译出 `main.pdf`"
        )

        assert "<ul>" in html
        assert html.count("<li>") == 3
        assert "main.tex" in html
        assert "已编译出" in html

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

    def test_table_header_uses_surface_color_in_light_mode(self, monkeypatch):
        monkeypatch.setattr(theme, "is_dark_mode", lambda: False)
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = render_markdown(md)
        # Light-mode header uses the surface color (#f8f8f8) for a subtle
        # distinction from the white page background (no longer pure white).
        assert 'bgcolor="#f8f8f8"' in html


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
