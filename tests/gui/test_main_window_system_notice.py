"""Tests for SystemNotice and ReportMessage rendering in MainWindow."""

from types import SimpleNamespace

from autoreport.gui.main_window import MainWindow
from autoreport.interfaces.types import AgentType, ReportMessage, SystemNotice


def test_system_notice_renders_in_target_agent_panel():
    """SystemNotice should render a left-aligned system bubble in the target agent panel."""
    panel_calls: list[tuple[str, tuple, dict]] = []
    store_calls: list[tuple[str, tuple, dict]] = []

    class _Panel:
        def add_message(self, *args, **kwargs):
            panel_calls.append(("message", args, kwargs))

    class _Store:
        def append_message(self, *args, **kwargs):
            store_calls.append(("message", args, kwargs))

    fake = SimpleNamespace()
    fake._conv_store = _Store()
    fake.current_agent_type = "main"
    fake._is_visible_agent = lambda agent_type: agent_type == "main"
    fake._get_panel_for_agent = lambda agent_type: _Panel()
    fake._get_agent_display_name = lambda agent_type: str(agent_type).replace("_", " ").title()
    fake._build_inter_agent_title = lambda prefix, content: MainWindow._build_inter_agent_title(
        fake, prefix, content
    )

    MainWindow._handle_system_notice(
        fake,
        SystemNotice(agent_type=AgentType.MAIN, content="本轮需要调用 Respond 向 Main 回复"),
    )

    # Check panel was called with correct bubble parameters
    assert len(panel_calls) == 1
    call_name, args, kwargs = panel_calls[0]
    assert call_name == "message"
    assert args[0] == "agent"
    assert args[1] == "本轮需要调用 Respond 向 Main 回复"
    assert kwargs["source"] == "system"
    assert kwargs["display_mode"] == "bubble"
    assert kwargs["bubble_align"] == "left"
    assert kwargs["bubble_on_timeline"] is False
    assert kwargs["bubble_collapsible"] is True
    assert kwargs["bubble_title"] is None

    # Check store was called with persistence parameters
    assert len(store_calls) == 1
    call_name, args, kwargs = store_calls[0]
    assert call_name == "message"
    assert args[0] == "main"
    assert args[1] == "agent"
    assert args[2] == "本轮需要调用 Respond 向 Main 回复"
    assert kwargs["extra"]["source"] == "system"
    assert kwargs["extra"]["display_mode"] == "bubble"
    assert kwargs["extra"]["bubble_align"] == "left"
    assert kwargs["extra"]["bubble_on_timeline"] is False
    assert kwargs["extra"]["bubble_collapsible"] is True
    assert kwargs["extra"]["system_notice"] is True


def test_report_message_renders_in_main_panel():
    """ReportMessage should render a collapsed bubble in the main panel."""
    panel_calls: list[tuple[str, tuple, dict]] = []
    store_calls: list[tuple[str, tuple, dict]] = []

    class _Panel:
        def add_message(self, *args, **kwargs):
            panel_calls.append(("message", args, kwargs))

    class _Store:
        def append_message(self, *args, **kwargs):
            store_calls.append(("message", args, kwargs))

    fake = SimpleNamespace()
    fake._conv_store = _Store()
    fake.current_agent_type = "main"
    fake._is_visible_agent = lambda agent_type: agent_type == "main"
    fake._get_panel_for_agent = lambda agent_type: _Panel()
    fake.agent_panel = _Panel()  # ReportMessage renders in main panel
    fake._get_agent_display_name = lambda agent_type: "Plotting"
    fake._build_inter_agent_title = lambda prefix, content: MainWindow._build_inter_agent_title(
        fake, prefix, content
    )

    MainWindow._handle_report_message(
        fake,
        ReportMessage(
            agent_type=AgentType.PLOTTING,
            task_id="tk1",
            report_type="missing_data",
            content="Need x column data",
        ),
    )

    # Check panel was called with correct bubble parameters
    assert len(panel_calls) == 1
    call_name, args, kwargs = panel_calls[0]
    assert call_name == "message"
    assert args[0] == "agent"
    assert args[1] == "Need x column data"
    assert kwargs["source"] == "plotting"
    assert kwargs["display_mode"] == "bubble"
    assert kwargs["bubble_align"] == "left"
    assert kwargs["bubble_on_timeline"] is False
    assert kwargs["bubble_collapsible"] is True
    assert kwargs["bubble_title"] == "Sub to Main"

    # Check store was called with persistence parameters
    assert len(store_calls) == 1
    call_name, args, kwargs = store_calls[0]
    assert call_name == "message"
    assert args[0] == "main"
    assert args[1] == "agent"
    assert args[2] == "Need x column data"
    assert kwargs["extra"]["source"] == "plotting"
    assert kwargs["extra"]["display_mode"] == "bubble"
    assert kwargs["extra"]["bubble_align"] == "left"
    assert kwargs["extra"]["bubble_on_timeline"] is False
    assert kwargs["extra"]["bubble_collapsible"] is True
    assert kwargs["extra"]["report_type"] == "missing_data"
    assert kwargs["extra"]["task_id"] == "tk1"


def test_system_notice_for_invisible_agent_skips_panel():
    """SystemNotice for invisible agent should only persist to store, not render panel."""
    panel_calls: list[tuple[str, tuple, dict]] = []
    store_calls: list[tuple[str, tuple, dict]] = []

    class _Panel:
        def add_message(self, *args, **kwargs):
            panel_calls.append(("message", args, kwargs))

    class _Store:
        def append_message(self, *args, **kwargs):
            store_calls.append(("message", args, kwargs))

    fake = SimpleNamespace()
    fake._conv_store = _Store()
    fake.current_agent_type = "main"  # Only main is visible
    fake._is_visible_agent = lambda agent_type: agent_type == "main"
    fake._get_panel_for_agent = lambda agent_type: _Panel()
    fake._get_agent_display_name = lambda agent_type: str(agent_type).replace("_", " ").title()
    fake._build_inter_agent_title = lambda prefix, content: MainWindow._build_inter_agent_title(
        fake, prefix, content
    )

    MainWindow._handle_system_notice(
        fake,
        SystemNotice(agent_type=AgentType.PLOTTING, content="正在处理数据"),
    )

    # Panel should not be called since plotting agent is not visible
    assert len(panel_calls) == 0

    # But store should still persist
    assert len(store_calls) == 1
    call_name, args, kwargs = store_calls[0]
    assert call_name == "message"
    assert args[0] == "plotting"


def test_report_message_for_invisible_main_skips_panel():
    """ReportMessage when main is invisible should only persist to store."""
    panel_calls: list[tuple[str, tuple, dict]] = []
    store_calls: list[tuple[str, tuple, dict]] = []

    class _Panel:
        def add_message(self, *args, **kwargs):
            panel_calls.append(("message", args, kwargs))

    class _Store:
        def append_message(self, *args, **kwargs):
            store_calls.append(("message", args, kwargs))

    fake = SimpleNamespace()
    fake._conv_store = _Store()
    fake.current_agent_type = "plotting"  # Only plotting is visible
    fake._is_visible_agent = lambda agent_type: agent_type == "plotting"
    fake._get_panel_for_agent = lambda agent_type: _Panel()
    fake._get_agent_display_name = lambda agent_type: "Data Analysis"
    fake._build_inter_agent_title = lambda prefix, content: MainWindow._build_inter_agent_title(
        fake, prefix, content
    )

    MainWindow._handle_report_message(
        fake,
        ReportMessage(
            agent_type=AgentType.DATA_ANALYSIS,
            task_id="tk2",
            report_type="quality",
            content="Data quality check passed",
        ),
    )

    # Panel should not be called since main is not visible
    assert len(panel_calls) == 0

    # But store should still persist to main
    assert len(store_calls) == 1
    call_name, args, kwargs = store_calls[0]
    assert call_name == "message"
    assert args[0] == "main"
