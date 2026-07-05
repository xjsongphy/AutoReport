"""Tests for manage_tasks result formatting in MainWindow."""

from types import SimpleNamespace

from autoreport.gui.main_window import MainWindow
from autoreport.interfaces.types import AgentType, ToolCallMessage, ToolResult


def test_manage_tasks_format_omits_empty_sections():
    summary, detail, expandable = MainWindow._format_manage_tasks_result(
        None,
        {
            "status": "ok",
            "todolist": [
                {
                    "brief": "DATA_ANALYSIS: Process measurements",
                    "status": "pending",
                }
            ],
            "waitlist": [],
        },
        None,
    )

    assert summary == "<b>Task</b>\nTodo\n☐ DATA_ANALYSIS: Process measurements"
    assert detail is None
    assert expandable is False


def test_manage_tasks_format_omits_all_empty_task_sections():
    summary, detail, expandable = MainWindow._format_manage_tasks_result(
        None,
        {
            "status": "ok",
            "todolist": [],
            "waitlist": [],
        },
        None,
    )

    assert summary == "<b>Task</b>"
    assert detail is None
    assert expandable is False


def test_send_to_agent_tool_result_does_not_append_delegate_bubble():
    panel_calls: list[tuple[str, tuple, dict]] = []
    store_calls: list[tuple[str, tuple, dict]] = []

    class _Panel:
        def add_tool_result(self, *args, **kwargs):
            panel_calls.append(("tool_result", args, kwargs))

        def add_message(self, *args, **kwargs):
            panel_calls.append(("message", args, kwargs))

    class _Store:
        def append_tool_result(self, *args, **kwargs):
            store_calls.append(("tool_result", args, kwargs))

        def append_message(self, *args, **kwargs):
            store_calls.append(("message", args, kwargs))

    fake = SimpleNamespace()
    fake._conv_store = _Store()
    fake._format_send_to_agent_bubble = lambda result, error: MainWindow._format_send_to_agent_bubble(
        fake, result, error
    )
    fake._get_agent_display_name = lambda agent_type: str(agent_type).replace("_", " ").title()
    fake._is_visible_agent = lambda agent_type: agent_type == "main"
    fake._get_panel_for_agent = lambda agent_type: _Panel()
    fake._state_for_agent = lambda agent_type: SimpleNamespace(phase="idle")
    fake._augment_manage_tasks_result = lambda agent_str, result: result

    MainWindow._handle_tool_result(
        fake,
        ToolResult(
            agent_type=AgentType.MAIN,
            tool_name="send_to_agent",
            result={"status": "delegated", "agent_type": "plotting", "message": "delegated"},
        ),
    )

    assert [call[0] for call in panel_calls] == ["tool_result"]
    assert [call[0] for call in store_calls] == ["tool_result"]


def test_send_to_agent_tool_call_displays_main_to_sub_summary():
    panel_calls: list[tuple[str, tuple, dict]] = []
    store_calls: list[tuple[str, tuple, dict]] = []

    class _Panel:
        def finish_thinking(self):
            pass

        def add_tool_call(self, *args, **kwargs):
            panel_calls.append(("tool_call", args, kwargs))

    class _Store:
        def append_tool_call(self, *args, **kwargs):
            store_calls.append(("tool_call", args, kwargs))

    fake = SimpleNamespace()
    fake._conv_store = _Store()
    fake._is_visible_agent = lambda agent_type: agent_type == "main"
    fake._get_panel_for_agent = lambda agent_type: _Panel()
    fake._state_for_agent = lambda agent_type: SimpleNamespace(phase="idle")

    MainWindow._handle_tool_call(
        fake,
        ToolCallMessage(
            agent_type=AgentType.MAIN,
            tool_name="send_to_agent",
            arguments={"agent_type": "plotting"},
        ),
    )

    assert panel_calls[0][2]["summary"] == "Main to Sub"
    assert store_calls[0][2]["extra"]["summary"] == "Main to Sub"


def test_respond_tool_result_displays_sub_to_main_summary_and_detail():
    summary, detail = MainWindow._format_respond_bubble(
        None,
        {"status": "ok", "report_type": "reply", "content": "full response"},
        None,
    )

    assert summary == "Sub to Main"
    assert detail == "full response"


def test_rollback_finished_truncates_current_session_and_refreshes_visible_panel():
    calls: dict[str, object] = {}

    class _Future:
        def result(self):
            return {"restored_files": 1}

    fake = SimpleNamespace()
    fake._pending_rollbacks = {
        "main": {
            "message_id": "msg-1",
            "content": "hello",
            "role": "user",
        }
    }
    fake._conv_store = SimpleNamespace(
        truncate_from_message=lambda agent_type, **kwargs: calls.setdefault(
            "truncate", (agent_type, kwargs)
        )
    )
    fake._is_visible_agent = lambda agent_type: agent_type == "main"
    fake._show_current_agent_conversation = lambda: calls.setdefault("show", True)
    fake.file_tree = SimpleNamespace(refresh=lambda: calls.setdefault("refresh", True))
    fake.preview = SimpleNamespace(current_file=None)

    MainWindow._on_rollback_finished(fake, "main", _Future())

    assert calls["truncate"] == (
        "main",
        {"message_id": "msg-1", "content": "hello", "role": "user"},
    )
    assert calls["show"] is True
    assert calls["refresh"] is True
