"""Tests for StatusIndicator widget."""

from PyQt6.QtCore import Qt

from autoreport.gui.widgets.status_indicator import StatusIndicator, _SPINNER_FRAMES


def _make_indicator(qtbot):
    """Create a StatusIndicator and register it with qtbot."""
    indicator = StatusIndicator()
    qtbot.addWidget(indicator)
    return indicator


class TestStatusIndicatorInit:
    """Tests for initial state."""

    def test_initially_hidden(self, qtbot):
        indicator = _make_indicator(qtbot)
        assert indicator.isVisible() is False

    def test_initial_status_idle(self, qtbot):
        indicator = _make_indicator(qtbot)
        assert indicator._status == "idle"

    def test_initial_timer_not_running(self, qtbot):
        indicator = _make_indicator(qtbot)
        assert indicator.is_running() is False


class TestStatusIndicatorStart:
    """Tests for start() method."""

    def test_start_thinking_becomes_visible(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.start("thinking")
        assert indicator.isVisible() is True

    def test_start_thinking_is_running(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.start("thinking")
        assert indicator.is_running() is True

    def test_start_thinking_status_label(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.start("thinking")
        assert indicator._status_label.text() == "Thinking"

    def test_start_tool_shows_running_tool(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.start("tool")
        assert indicator._status_label.text() == "Running Tool"
        assert indicator._status == "tool"

    def test_start_running_tool_shows_running_tool(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.start("running_tool")
        assert indicator._status_label.text() == "Running Tool"

    def test_start_sets_status(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.start("thinking")
        assert indicator._status == "thinking"


class TestStatusIndicatorStop:
    """Tests for stop() method."""

    def test_stop_hides_indicator(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.start("thinking")
        indicator.stop()
        assert indicator.isVisible() is False

    def test_stop_is_not_running(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.start("thinking")
        indicator.stop()
        assert indicator.is_running() is False

    def test_stop_resets_status_to_idle(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.start("thinking")
        indicator.stop()
        assert indicator._status == "idle"
        assert indicator._status_label.text() == "Idle"


class TestStatusIndicatorSetStatus:
    """Tests for set_status() method."""

    def test_set_status_error(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.set_status("error", "Error")
        assert indicator._status == "error"
        assert indicator._status_label.text() == "Error"

    def test_set_status_error_changes_style(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.set_status("error", "Error")
        style = indicator.styleSheet()
        assert "#5a1a1a" in style  # error bg color

    def test_set_status_debug_mode(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.set_status("debug_mode", "Debug")
        assert indicator._status == "debug_mode"
        assert indicator._status_label.text() == "Debug"

    def test_set_status_debug_changes_style(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.set_status("debug", "Debug")
        style = indicator.styleSheet()
        assert "#3a1a5a" in style  # debug bg color

    def test_set_status_with_default_text(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.set_status("error")
        assert indicator._status_label.text() == "Error"

    def test_set_status_with_custom_text(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator.set_status("thinking", "Custom Status")
        assert indicator._status_label.text() == "Custom Status"


class TestStatusIndicatorTick:
    """Tests for _tick() spinner advancement."""

    def test_tick_advances_frame(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator._frame_idx = 0
        indicator._tick()
        assert indicator._frame_idx == 1
        assert indicator._spinner_label.text() == _SPINNER_FRAMES[1]

    def test_tick_wraps_around(self, qtbot):
        indicator = _make_indicator(qtbot)
        indicator._frame_idx = len(_SPINNER_FRAMES) - 1
        indicator._tick()
        assert indicator._frame_idx == 0
        assert indicator._spinner_label.text() == _SPINNER_FRAMES[0]

    def test_tick_cycles_through_all_frames(self, qtbot):
        indicator = _make_indicator(qtbot)
        seen = set()
        for _ in range(len(_SPINNER_FRAMES)):
            indicator._tick()
            seen.add(indicator._frame_idx)
        assert seen == set(range(len(_SPINNER_FRAMES)))
