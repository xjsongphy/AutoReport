"""Tests for DebugPanel widget."""

import pytest
import os
import tempfile
from datetime import datetime
from autoreport.gui.widgets.debug_panel import DebugPanel


def test_add_debug_entry(qtbot):
    """Adding entry should update display."""
    widget = DebugPanel()
    qtbot.addWidget(widget)

    widget.add_entry(
        timestamp=datetime.now(),
        model="claude-sonnet-4-20250514",
        tokens_in=1000,
        tokens_out=500,
        duration_ms=1500,
        status="success",
    )

    assert widget.entry_count() == 1
    summary = widget.get_summary_text()
    assert "1 call" in summary or "1" in summary


def test_fifo_eviction(qtbot):
    """Should evict oldest entries when exceeding max 50."""
    widget = DebugPanel()
    qtbot.addWidget(widget)

    # Add 52 entries with unique names to avoid substring matches
    for i in range(52):
        widget.add_entry(
            timestamp=datetime.now(),
            model=f"model-{i:02d}",  # Zero-pad to avoid "model-1" in "model-10"
            tokens_in=100 + i,
            tokens_out=50 + i,
            duration_ms=1000 + i * 10,
            status="success",
        )

    # Should only have 50 entries (FIFO eviction)
    assert widget.entry_count() == 50

    # First two entries should be evicted
    summary = widget.get_summary_text()
    assert "model-00" not in summary
    assert "model-01" not in summary
    # Last entry should be present
    assert "model-51" in summary


def test_clear_all(qtbot):
    """Clear button should remove all entries."""
    widget = DebugPanel()
    qtbot.addWidget(widget)

    # Add some entries
    for i in range(5):
        widget.add_entry(
            timestamp=datetime.now(),
            model=f"model-{i}",
            tokens_in=100,
            tokens_out=50,
            duration_ms=1000,
            status="success",
        )

    assert widget.entry_count() == 5

    # Clear all
    widget.clear_all()

    assert widget.entry_count() == 0
    assert widget.get_summary_text() == ""


def test_entry_with_error(qtbot):
    """Entry with error status should display error message."""
    widget = DebugPanel()
    qtbot.addWidget(widget)

    widget.add_entry(
        timestamp=datetime.now(),
        model="claude-sonnet-4-20250514",
        tokens_in=1000,
        tokens_out=0,
        duration_ms=5000,
        status="error",
        error="Rate limit exceeded",
    )

    assert widget.entry_count() == 1
    summary = widget.get_summary_text()
    assert "error" in summary.lower()
    assert "Rate limit exceeded" in summary


def test_export_json(qtbot):
    """Export should create valid JSON file."""
    widget = DebugPanel()
    qtbot.addWidget(widget)

    # Add test entries
    widget.add_entry(
        timestamp=datetime(2025, 5, 1, 12, 30, 45),
        model="claude-sonnet-4-20250514",
        tokens_in=1000,
        tokens_out=500,
        duration_ms=1500,
        status="success",
    )

    widget.add_entry(
        timestamp=datetime(2025, 5, 1, 12, 31, 0),
        model="gpt-4",
        tokens_in=2000,
        tokens_out=1000,
        duration_ms=3000,
        status="success",
    )

    # Export to file using tempfile in current directory
    import tempfile
    import json

    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir=".")
    temp_file_path = temp_file.name
    temp_file.close()

    try:
        widget.export_to_json(temp_file_path)

        # Verify file exists and contains valid JSON
        assert os.path.exists(temp_file_path)
        with open(temp_file_path, "r") as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["model"] == "claude-sonnet-4-20250514"
        assert data[0]["tokens_in"] == 1000
        assert data[1]["model"] == "gpt-4"
        assert data[1]["tokens_in"] == 2000
    finally:
        # Clean up
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
