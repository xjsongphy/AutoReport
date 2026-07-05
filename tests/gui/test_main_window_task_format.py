"""Tests for manage_tasks result formatting in MainWindow."""

from types import SimpleNamespace

from autoreport.gui.main_window import MainWindow
from autoreport.core.tools.task_board import TaskBoard
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


def test_manage_tasks_format_uses_distinct_wait_marker():
    summary, detail, expandable = MainWindow._format_manage_tasks_result(
        None,
        {
            "status": "ok",
            "todolist": [{"brief": "Process data", "status": "pending"}],
            "waitlist": [{"brief": "Plot figures", "status": "pending"}],
        },
        None,
    )

    assert summary == "<b>Task</b>\nTodo\n☐ Process data\n\nWait\n○ Plot figures"
    assert detail is None
    assert expandable is False


def test_invisible_manage_tasks_result_persists_augmented_task_summary():
    board = TaskBoard()
    board.create_task(AgentType.THEORY, AgentType.THEORY, "derive local formula", task_id="tk1")

    store_calls: list[tuple[str, tuple, dict]] = []

    class _Store:
        def get_current_session_id(self, agent_type):
            return None

        def append_tool_result(self, *args, **kwargs):
            store_calls.append(("tool_result", args, kwargs))

    fake = SimpleNamespace()
    fake.backend = SimpleNamespace(loop_manager=SimpleNamespace(_task_board=board))
    fake._conv_store = _Store()
    fake._is_visible_agent = lambda agent_type: False
    fake._state_for_agent = lambda agent_type: SimpleNamespace(phase="idle")
    fake._augment_manage_tasks_result = lambda agent_str, result: MainWindow._augment_manage_tasks_result(
        fake, agent_str, result
    )
    fake._format_manage_tasks_result = lambda result, error: MainWindow._format_manage_tasks_result(
        fake, result, error
    )
    fake._format_send_to_agent_bubble = lambda result, error: MainWindow._format_send_to_agent_bubble(
        fake, result, error
    )
    fake._format_respond_bubble = lambda result, error, agent_str="sub": MainWindow._format_respond_bubble(
        fake, result, error, agent_str=agent_str
    )

    MainWindow._handle_tool_result(
        fake,
        ToolResult(
            agent_type=AgentType.THEORY,
            tool_name="manage_tasks",
            result={"status": "ok", "message": "listed"},
        ),
    )

    assert len(store_calls) == 1
    _, args, kwargs = store_calls[0]
    assert args[0] == "theory"
    assert args[1] == "manage_tasks"
    assert "Task" in args[2]
    assert "derive local formula" in args[2]
    assert kwargs["extra"]["summary"] == args[2]


def test_send_to_agent_tool_result_does_not_append_delegate_bubble():
    panel_calls: list[tuple[str, tuple, dict]] = []
    store_calls: list[tuple[str, tuple, dict]] = []

    class _Panel:
        def add_tool_call(self, *args, **kwargs):
            panel_calls.append(("tool_call", args, kwargs))

        def add_tool_result(self, *args, **kwargs):
            panel_calls.append(("tool_result", args, kwargs))

        def add_message(self, *args, **kwargs):
            panel_calls.append(("message", args, kwargs))

    class _Store:
        def append_tool_call(self, *args, **kwargs):
            store_calls.append(("tool_call", args, kwargs))

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
    fake._send_to_agent_result_arguments = lambda result: MainWindow._send_to_agent_result_arguments(
        fake, result
    )

    MainWindow._handle_tool_result(
        fake,
        ToolResult(
            agent_type=AgentType.MAIN,
            tool_name="send_to_agent",
            result={"status": "delegated", "agent_type": "plotting", "message": "delegated"},
        ),
    )

    assert [call[0] for call in panel_calls] == ["tool_call", "tool_result"]
    assert [call[0] for call in store_calls] == ["tool_call", "tool_result"]


def test_send_to_agent_tool_call_is_deferred_until_after_task_update():
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

    assert panel_calls == []
    assert store_calls == []


def test_respond_tool_result_displays_summary_and_detail():
    summary, detail = MainWindow._format_respond_bubble(
        None,
        {
            "status": "ok",
            "report_type": "reply",
            "summary": "Plot complete",
            "content": "full response",
        },
        None,
        agent_str="plotting",
    )

    assert summary == "Plot complete"
    assert detail == "full response"


def test_send_to_agent_result_displays_response_summary_and_detail():
    summary, detail = MainWindow._format_send_to_agent_bubble(
        None,
        {
            "status": "success",
            "agent_type": "theory",
            "summary": "Derive formula",
            "response_summary": "Theory complete",
            "response": "full theory response",
        },
        None,
    )

    assert summary == "Theory complete"
    assert detail == "full theory response"


def test_manage_tasks_tool_call_displays_task_summary():
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
    fake._is_visible_agent = lambda agent_type: agent_type == "theory"
    fake._get_panel_for_agent = lambda agent_type: _Panel()
    fake._state_for_agent = lambda agent_type: SimpleNamespace(phase="idle")

    MainWindow._handle_tool_call(
        fake,
        ToolCallMessage(
            agent_type=AgentType.THEORY,
            tool_name="manage_tasks",
            arguments={"action": "list"},
        ),
    )

    assert panel_calls[0][2]["summary"] == "<b>Task</b>"


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
