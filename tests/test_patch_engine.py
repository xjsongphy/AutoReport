from autoreport.core.tools.patch_engine import (
    apply_chunks,
    apply_patch_to_text,
    parse_patch,
)


def _apply(text: str, body: str):
    return apply_patch_to_text(text, body)


class TestParsePatch:
    def test_plus_minus_context_classified(self):
        chunks = parse_patch(
            "@@ def f()\n"
            " ctx\n"
            "-old\n"
            "+new\n"
        )
        assert len(chunks) == 1
        c = chunks[0]
        assert c.context == "def f()"
        assert c.old_lines == ["ctx", "old"]
        assert c.new_lines == ["ctx", "new"]

    def test_blank_line_splits_chunks(self):
        chunks = parse_patch("-a\n+b\n\n-c\n+d\n")
        assert len(chunks) == 2
        assert chunks[0].old_lines == ["a"] and chunks[0].new_lines == ["b"]
        assert chunks[1].old_lines == ["c"] and chunks[1].new_lines == ["d"]

    def test_pure_addition_chunk_has_empty_old(self):
        chunks = parse_patch("+line one\n+line two\n")
        assert len(chunks) == 1
        assert chunks[0].old_lines == []
        assert chunks[0].new_lines == ["line one", "line two"]


class TestApplyChunks:
    def test_exact_line_replacement(self):
        res = _apply("alpha\nbeta\ngamma\n", "-beta\n+BETA\n")
        assert res.error is None
        assert res.new_lines == ["alpha\nBETA\ngamma\n"]

    def test_context_anchor_disambiguates_duplicates(self):
        # Two identical 'return None' lines; the @@ anchor picks the second one.
        text = "def f():\n    return None\n\ndef g():\n    return None\n"
        body = "@@ def g():\n-    return None\n+    return 1\n"
        res = _apply(text, body)
        assert res.error is None
        assert "def g():\n    return 1" in res.new_lines[0]
        # The first 'return None' (under f) must be untouched.
        assert "def f():\n    return None" in res.new_lines[0]

    def test_sequential_cursor_picks_second_occurrence(self):
        # No anchor: two chunks, each targets a duplicated line in order.
        text = "x\nx\n"
        body = "-x\n+one\n\n-x\n+two\n"
        res = _apply(text, body)
        assert res.error is None
        assert res.new_lines == ["one\ntwo\n"]

    def test_pure_addition_appends(self):
        res = _apply("a\nb\n", "+c\n")
        assert res.error is None
        assert res.new_lines == ["a\nb\nc\n"]

    def test_not_found_is_error_and_unchanged(self):
        res = _apply("alpha\n", "-zzz\n+QQQ\n")
        assert res.error is not None
        assert "zzz" in res.error
        assert res.original == ["alpha"]

    def test_anchor_not_found_is_error(self):
        res = _apply("alpha\n", "@@ missing\n-x\n")
        assert res.error is not None
        assert "Context anchor" in res.error

    def test_multiline_block_match(self):
        # Remove a two-line block, add a two-line block.
        res = _apply("a\nb\nc\nd\n", "-b\n-c\n+B\n+C\n")
        assert res.error is None
        assert res.new_lines == ["a\nB\nC\nd\n"]


class TestApplyChunksDirect:
    """Drive apply_chunks with line lists directly (no text rejoin)."""

    def test_replacements_recorded(self):
        chunks = parse_patch("-b\n+B\n")
        res = apply_chunks(["a", "b", "c"], chunks)
        assert res.error is None
        assert res.new_lines == ["a", "B", "c"]
        assert len(res.replacements) == 1
        start, old_len, new_seg = res.replacements[0]
        assert (start, old_len, new_seg) == (1, 1, ["B"])
