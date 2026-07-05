"""Line-based patch engine ported from codex's ``apply_patch``.

This is a stripped-down, single-file, Python reimplementation of codex's
``apply_patch`` (see ``../codex/codex-rs/apply-patch/src/``). Differences from
codex:

- Operates on a single file. The file path is supplied by the caller; the patch
  body contains only hunks (no ``*** Begin Patch`` / ``*** Update File:`` envelope).
- Only **exact** line matching is supported. Codex's trailing-whitespace and
  Unicode-punctuation normalisation passes are intentionally dropped.
- Duplicate-line disambiguation works exactly like codex: a monotonically
  advancing cursor (each chunk searches forward from where the previous one
  ended) plus optional ``@@`` context anchors.

Patch body grammar::

    body    := { chunk }
    chunk   := [ "@@" [SP context] NL ] { hunk_line } [ blank_line ]
    hunk_line := (" " | "-" | "+") text NL | NL

A ``@@`` line (optionally followed by a context string) anchors the chunk: the
engine locates that single line in the file first, then searches for the
chunk's old lines strictly after it. Blank lines separate chunks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chunk:
    """One contiguous run of diff lines, optionally anchored by a ``@@`` line.

    ``old_lines`` are the context+removed lines (what must already be in the
    file); ``new_lines`` are the context+added lines (the replacement).
    """

    context: str | None = None
    old_lines: list[str] = field(default_factory=list)
    new_lines: list[str] = field(default_factory=list)


@dataclass
class ApplyResult:
    """Outcome of applying chunks to a list of lines.

    On success ``new_lines`` holds the result and ``error`` is None. On failure
    ``new_lines`` is empty, ``error`` describes the problem, and ``original``
    carries the untouched content so the caller can hand it back to the agent.
    """

    new_lines: list[str]
    replacements: list[tuple[int, int, list[str]]] = field(default_factory=list)
    error: str | None = None
    original: list[str] = field(default_factory=list)


class PatchError(Exception):
    """Raised when a patch body cannot be parsed."""


def parse_patch(body: str) -> list[Chunk]:
    """Parse a single-file patch body into chunks.

    Raises:
        PatchError: If the body is empty or contains an unrecognised line.
    """
    # Preserve a trailing empty line as a real (blank) hunk line by using
    # splitlines on the text without the final newline and tracking newline
    # presence separately is overkill; codex splits on '\n'. We mirror that:
    # a trailing newline does not create a spurious empty line.
    raw_lines = body.split("\n")
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()

    chunks: list[Chunk] = []
    current: Chunk | None = None

    for line in raw_lines:
        if line.startswith("@@"):
            # A new anchor always starts a new chunk.
            context = line[2:]
            if context.startswith(" "):
                context = context[1:]
            current = Chunk(context=context)
            chunks.append(current)
            continue

        if current is None:
            current = Chunk()
            chunks.append(current)

        if line == "":
            # Blank line: codex treats a fully-blank line inside a chunk as an
            # empty context line (pushed to both old and new). A blank line that
            # terminates a chunk is handled implicitly — pushing an empty line
            # to both sides is a no-op for matching as long as the file also
            # has a blank line there. To keep chunk boundaries crisp we instead
            # treat a blank line as a chunk separator.
            current = None
            continue

        prefix, rest = line[0], line[1:]
        if prefix == " ":
            current.old_lines.append(rest)
            current.new_lines.append(rest)
        elif prefix == "+":
            current.new_lines.append(rest)
        elif prefix == "-":
            current.old_lines.append(rest)
        else:
            raise PatchError(
                f"Unrecognised patch line (must start with ' ', '+', '-', or '@@'): {line!r}"
            )

    chunks = [c for c in chunks if c.old_lines or c.new_lines or c.context is not None]
    if not chunks:
        raise PatchError("Patch body is empty.")
    return chunks


def _seek(lines: list[str], pattern: list[str], start: int) -> int | None:
    """Return the index of the first exact match of ``pattern`` at/after ``start``."""
    if not pattern:
        return start
    n = len(lines)
    plen = len(pattern)
    if plen > n:
        return None
    for i in range(start, n - plen + 1):
        if lines[i : i + plen] == pattern:
            return i
    return None


def apply_chunks(original_lines: list[str], chunks: list[Chunk]) -> ApplyResult:
    """Apply ``chunks`` to ``original_lines`` with a monotonic cursor.

    Returns an :class:`ApplyResult`. On error nothing is mutated; ``original``
    carries the input so callers can echo it back.
    """
    replacements: list[tuple[int, int, list[str]]] = []
    line_index = 0

    for chunk in chunks:
        if chunk.context is not None:
            idx = _seek(original_lines, [chunk.context], line_index)
            if idx is None:
                return ApplyResult(
                    [],
                    [],
                    error=f"Context anchor not found: {chunk.context!r}",
                    original=original_lines,
                )
            line_index = idx + 1

        if not chunk.old_lines:
            # Pure addition — append at end of file.
            insert_at = len(original_lines)
            replacements.append((insert_at, 0, list(chunk.new_lines)))
            continue

        idx = _seek(original_lines, chunk.old_lines, line_index)
        if idx is None:
            return ApplyResult(
                [],
                [],
                error="Could not locate the following lines in the file:\n"
                + "\n".join(chunk.old_lines),
                original=original_lines,
            )
        replacements.append((idx, len(chunk.old_lines), list(chunk.new_lines)))
        line_index = idx + len(chunk.old_lines)

    # Apply in descending start order so earlier replacements don't shift later
    # positions (mirrors codex apply_replacements).
    replacements.sort(key=lambda r: r[0])
    out = list(original_lines)
    for start, old_len, new_seg in reversed(replacements):
        out[start : start + old_len] = new_seg

    return ApplyResult(out, replacements, error=None)


def apply_patch_to_text(text: str, body: str) -> ApplyResult:
    """Convenience: parse ``body`` and apply to ``text`` (split into lines).

    Trailing-newline handling mirrors codex: ``split('\\n')`` yields a trailing
    empty element for a final newline (and ``['']`` for the empty string), which
    is dropped before applying and re-added afterward so the result always ends
    in a single newline when non-empty.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    chunks = parse_patch(body)
    result = apply_chunks(lines, chunks)
    if result.error:
        return result

    out = list(result.new_lines)
    if out and out[-1] != "":
        out.append("")
    joined = "\n".join(out)
    # Re-pack the rejoined text as new_lines for the caller; keep replacements.
    return ApplyResult([joined], result.replacements, error=None)
