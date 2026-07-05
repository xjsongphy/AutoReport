"""Helpers for parsing and filtering editor-context wrappers in user messages."""

from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any


def _display_filename(path_text: str) -> str:
    normalized = str(path_text or "").strip().rstrip("/\\")
    if not normalized:
        return ""
    try:
        return PurePath(normalized).name or normalized
    except Exception:
        return normalized


def parse_editor_context(content: str) -> dict[str, Any]:
    """Parse an editor-context wrapped message.

    Returns a dict with:
    - has_context: bool
    - bubble_text: user-visible plain message text
    - chip_text/chip_tooltip: compact UI chip fields
    - context: structured context payload or None
    """
    text = str(content or "")
    result = {
        "has_context": False,
        "bubble_text": text,
        "chip_text": None,
        "chip_tooltip": None,
        "context": None,
    }
    if not text.startswith("Editor context: "):
        return result

    lines = text.splitlines()
    if len(lines) < 2:
        return result

    context_type = lines[0].split(":", 1)[1].strip().lower()
    body_start = None
    chip_text = None
    chip_tooltip = None
    context: dict[str, Any] | None = None

    if context_type == "selection" and len(lines) >= 3:
        file_match = re.match(r"^File:\s*(.+)$", lines[1])
        line_match = re.match(r"^Selected lines:\s*(.+)$", lines[2])
        if file_match and line_match:
            file_path = file_match.group(1).strip()
            line_span = line_match.group(1).strip()
            chip_text = f"{_display_filename(file_path)}#{line_span}"
            chip_tooltip = f"{file_path}#{line_span}"
            context = {
                "type": "selection",
                "file": file_path,
                "selected_lines": line_span,
            }
            body_start = 3
    elif context_type == "file" and len(lines) >= 2:
        file_match = re.match(r"^Current file:\s*(.+)$", lines[1])
        if file_match:
            file_path = file_match.group(1).strip()
            chip_text = _display_filename(file_path)
            chip_tooltip = file_path
            context = {
                "type": "file",
                "file": file_path,
            }
            body_start = 2

    if body_start is None:
        return result

    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    bubble_text = "\n".join(lines[body_start:]).strip()

    result["has_context"] = True
    result["bubble_text"] = bubble_text
    result["chip_text"] = chip_text
    result["chip_tooltip"] = chip_tooltip
    result["context"] = context
    return result


def user_visible_content(content: str) -> str:
    parsed = parse_editor_context(content)
    if parsed["has_context"]:
        return str(parsed["bubble_text"] or "")
    return str(content or "")


def build_editor_context_message(context: dict[str, Any] | None, bubble_text: str) -> str:
    """Build wrapped user text from structured editor context metadata."""
    text = str(bubble_text or "").strip()
    if not context:
        return text

    context_type = str(context.get("type", "")).strip().lower()
    file_path = str(context.get("file", "")).strip()
    if context_type == "selection":
        selected = str(context.get("selected_lines", "")).strip()
        if file_path and selected:
            return (
                "Editor context: selection\n"
                f"File: {file_path}\n"
                f"Selected lines: {selected}\n\n"
                f"{text}"
            ).strip()
    elif context_type == "file":
        if file_path:
            return (
                "Editor context: file\n"
                f"Current file: {file_path}\n\n"
                f"{text}"
            ).strip()
    return text
