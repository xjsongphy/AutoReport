"""Tests for manage_tasks result formatting in MainWindow."""

from types import SimpleNamespace

from autoreport.gui.main_window import MainWindow
from autoreport.gui.widgets.agent_panel import AgentPanel
from autoreport.core.tools.task_board import TaskBoard
from autoreport.interfaces.types import AgentResponse, AgentType, ToolCallMessage, ToolResult


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


def test_manage_tasks_format_keeps_completed_wait_but_pending_followup_todo():
    summary, detail, expandable = MainWindow._format_manage_tasks_result(
        None,
        {
            "status": "ok",
            "todolist": [{"brief": "Check Report completed: Saying hello", "status": "pending"}],
            "waitlist": [{"brief": "Saying hello", "status": "completed"}],
        },
        None,
    )

    assert summary == (
        "<b>Task</b>\n"
        "Todo\n☐ Check Report completed: Saying hello\n\n"
        "Wait\n☑ Saying hello"
    )
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


def test_manage_tasks_result_matching_live_snapshot_is_not_appended_twice():
    board = TaskBoard()
    board.create_task(AgentType.THEORY, AgentType.THEORY, "derive local formula", task_id="tk1")
    panel_calls: list[tuple[str, tuple, dict]] = []
    store_calls: list[tuple[str, tuple, dict]] = []

    class _Store:
        def get_current_session_id(self, agent_type):
            return None

        def append_tool_result(self, *args, **kwargs):
            store_calls.append(("tool_result", args, kwargs))

        def load_messages(self, agent_type):
            return [
                {
                    "role": "tool_result",
                    "content": "manage_tasks",
                    "summary": "<b>Task</b>\nTodo\n☐ derive local formula",
                    "result": "<b>Task</b>\nTodo\n☐ derive local formula",
                    "task_snapshot": True,
                }
            ]

    class _Panel:
        def add_tool_result(self, *args, **kwargs):
            panel_calls.append(("tool_result", args, kwargs))

    fake = SimpleNamespace()
    fake.backend = SimpleNamespace(loop_manager=SimpleNamespace(_task_board=board))
    fake._conv_store = _Store()
    fake._is_visible_agent = lambda agent_type: True
    fake._get_panel_for_agent = lambda agent_type: _Panel()
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
    fake._latest_persisted_task_summary = lambda agent_type: MainWindow._latest_persisted_task_summary(
        fake, agent_type
    )

    MainWindow._handle_tool_result(
        fake,
        ToolResult(
            agent_type=AgentType.THEORY,
            tool_name="manage_tasks",
            result={"status": "ok", "message": "listed"},
        ),
    )

    assert panel_calls == []
    assert store_calls == []


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

    assert [call[0] for call in panel_calls] == ["tool_result"]
    assert [call[0] for call in store_calls] == ["tool_result"]


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

    assert len(panel_calls) == 1
    assert panel_calls[0][0] == "tool_call"
    assert panel_calls[0][2]["summary"] == "Main to Plotting"
    assert len(store_calls) == 1
    assert store_calls[0][0] == "tool_call"


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

    assert summary == "Respond"
    assert detail == "full response"


def test_send_to_agent_result_displays_response_summary_and_detail():
    summary, detail = MainWindow._format_send_to_agent_bubble(
        None,
        {
            "status": "success",
            "agent_type": "theory",
            "summary": "Derive formula",
            "content": "Derive the formula for X given Y.",
            "response_summary": "Theory complete",
            "response": "full theory response",
        },
        None,
    )

    # Dot shows the route; detail carries only the dispatched request text.
    # The sub-agent's reply is a separate bubble — not bundled here.
    assert summary == "Main to Theory"
    assert detail == "Derive the formula for X given Y."


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


def test_final_thinking_snapshot_after_answer_does_not_create_duplicate_thought(qtbot, tmp_path):
    thought = (
        'The user is just saying "hi" - this is a greeting/communication test. '
        "I should respond directly without using tools."
    )
    panel = AgentPanel(panel_id="main", title="Main", workspace=tmp_path)
    qtbot.addWidget(panel)

    fake = SimpleNamespace()
    fake._turn_state = {}
    fake._is_visible_agent = lambda agent_type: agent_type == "main"
    fake._get_panel_for_agent = lambda agent_type: panel
    fake._state_for_agent = lambda agent_type: MainWindow._state_for_agent(fake, agent_type)
    fake._conv_store = SimpleNamespace(append_message=lambda *args, **kwargs: None)

    MainWindow._handle_agent_response(
        fake,
        AgentResponse(
            agent_type=AgentType.MAIN,
            content="",
            message_id="msg-1",
            streaming=True,
            thinking=thought,
        ),
    )
    MainWindow._handle_agent_response(
        fake,
        AgentResponse(
            agent_type=AgentType.MAIN,
            content="Hi! How can I help?",
            message_id="msg-1",
            streaming=True,
        ),
    )
    MainWindow._handle_agent_response(
        fake,
        AgentResponse(
            agent_type=AgentType.MAIN,
            content="",
            message_id="msg-1",
            streaming=True,
            thinking=thought,
        ),
    )

    rows = panel._messages_area.get_message_rows()
    thought_rows = [row for row in rows if getattr(row, "_display_mode", "") == "thought"]
    answer_rows = [row for row in rows if getattr(row, "_display_mode", "") == "agent_markdown"]

    assert len(thought_rows) == 1
    assert len(answer_rows) == 1
    assert rows.index(thought_rows[0]) < rows.index(answer_rows[0])


def test_render_task_block_skips_when_backend_has_no_task_board():
    fake = SimpleNamespace()
    fake.current_agent_type = "main"
    fake._agent_queue_cache = {}
    fake._agent_status_cache = {}
    fake._debug_agents = set()
    fake.agent_panel = SimpleNamespace(
        finish_thinking=lambda: None,
        set_queue_preview=lambda _q: None,
        set_status=lambda _s, _e: None,
        set_debug_mode=lambda _e: None,
    )
    fake.backend = SimpleNamespace(
        loop_manager=None,  # No loop manager → no task board
    )
    fake._sync_task_snapshot_for_agent = lambda agent_type, render: MainWindow._sync_task_snapshot_for_agent(
        fake, agent_type, render=render
    )

    # Must not crash; the guard exits early.
    MainWindow._render_task_block_for_current_agent(fake)


def test_render_task_block_skips_when_todolist_and_waitlist_empty():
    fake = SimpleNamespace()
    fake.current_agent_type = "main"
    fake._agent_queue_cache = {}
    fake._agent_status_cache = {}
    fake._debug_agents = set()
    panel = SimpleNamespace(
        finish_thinking=lambda: None,
        set_queue_preview=lambda _q: None,
        set_status=lambda _s, _e: None,
        set_debug_mode=lambda _e: None,
        add_task_block=lambda *a, **kw: setattr(panel, "_called", True),
    )
    fake.agent_panel = panel
    fake._conv_store = SimpleNamespace(
        get_current_session_id=lambda agent_type: "s1",
    )

    class _Task:
        def __init__(self, brief, status):
            self.brief = brief
            self.status = SimpleNamespace(value=status)

    class _FakeTB:
        def get_todolist(self, agent, session_id=None):
            return []

        def get_waitlist(self, agent, session_id=None):
            return []

    fake.backend = SimpleNamespace(
        loop_manager=SimpleNamespace(_task_board=_FakeTB()),
    )
    fake._sync_task_snapshot_for_agent = lambda agent_type, render: MainWindow._sync_task_snapshot_for_agent(
        fake, agent_type, render=render
    )

    MainWindow._render_task_block_for_current_agent(fake)
    assert not getattr(panel, "_called", False)


def test_render_task_block_skips_when_latest_persisted_snapshot_matches_live_state():
    fake = SimpleNamespace()
    fake.current_agent_type = "main"
    panel = SimpleNamespace(
        add_task_block=lambda *a, **kw: setattr(panel, "_called", True),
    )
    fake.agent_panel = panel
    fake._conv_store = SimpleNamespace(
        get_current_session_id=lambda agent_type: "s1",
        load_messages=lambda agent_type: [
            {
                "role": "tool_result",
                "content": "manage_tasks",
                "summary": "<b>Task</b>\nTodo\n☐ Process data",
                "result": "<b>Task</b>\nTodo\n☐ Process data",
                "task_snapshot": True,
            }
        ],
    )

    class _Task:
        def __init__(self, brief, status):
            self.brief = brief
            self.status = SimpleNamespace(value=status)

    class _FakeTB:
        def get_todolist(self, agent, session_id=None):
            return [_Task("Process data", "pending")]

        def get_waitlist(self, agent, session_id=None):
            return []

    fake.backend = SimpleNamespace(
        loop_manager=SimpleNamespace(_task_board=_FakeTB()),
    )
    fake._latest_persisted_task_summary = lambda agent_type: MainWindow._latest_persisted_task_summary(
        fake, agent_type
    )
    fake._format_manage_tasks_result = lambda result, error: MainWindow._format_manage_tasks_result(
        fake, result, error
    )
    fake._sync_task_snapshot_for_agent = lambda agent_type, render: MainWindow._sync_task_snapshot_for_agent(
        fake, agent_type, render=render
    )

    MainWindow._render_task_block_for_current_agent(fake)
    assert not getattr(panel, "_called", False)


def test_local_sub_task_update_does_not_sync_main_snapshot():
    calls: list[tuple[str, bool]] = []
    fake = SimpleNamespace()
    fake.current_agent_type = "main"
    fake._sync_task_snapshot_for_agent = lambda agent_type, render: calls.append((agent_type, render))

    MainWindow._handle_task_update_msg(
        fake,
        SimpleNamespace(
            source_agent=AgentType.THEORY,
            target_agent=AgentType.THEORY,
        ),
    )

    assert calls == [("theory", False)]


def test_main_dispatched_task_update_still_syncs_main_snapshot():
    calls: list[tuple[str, bool]] = []
    fake = SimpleNamespace()
    fake.current_agent_type = "main"
    fake._sync_task_snapshot_for_agent = lambda agent_type, render: calls.append((agent_type, render))

    MainWindow._handle_task_update_msg(
        fake,
        SimpleNamespace(
            source_agent=AgentType.MAIN,
            target_agent=AgentType.THEORY,
        ),
    )

    assert set(calls) == {("main", True), ("theory", False)}


def test_send_to_agent_result_detail_omits_badge_headers():
    """The dot shows "Main to {Sub}", the expandable detail carries only the
    dispatched request content. The sub-agent's reply is rendered as a separate
    bubble (not bundled into the send_to_agent detail)."""
    summary, detail = MainWindow._format_send_to_agent_bubble(
        None,
        {
            "status": "success",
            "agent_type": "theory",
            "content": "Derive the formula for X.",
            "response": "E = mc^2",
            "summary": "Derive formula",
        },
        None,
    )
    assert summary == "Main to Theory"
    assert detail == "Derive the formula for X."
    # No badge header lines; no response leaked into the dot detail.
    assert "E = mc^2" not in detail
    assert "▶" not in detail
    assert "◀" not in detail


def test_edit_resend_truncates_syncs_clears_queue_and_resends():
    calls: dict[str, object] = {}

    class _Panel:
        def set_queue_preview(self, queued):
            calls["queue_preview"] = list(queued)

        def _send_content(self, content):
            calls["send_content"] = content

    class _Store:
        def truncate_from_message(self, agent_type, **kwargs):
            calls["truncate"] = (agent_type, kwargs)
            return True

        def get_current_session_id(self, agent_type):
            return "s1"

    fake = SimpleNamespace()
    fake.agent_panel = _Panel()
    fake._conv_store = _Store()
    fake._agent_queue_cache = {"main": ["stale queued"]}
    fake.backend = SimpleNamespace(
        loop_manager=SimpleNamespace(
            cancel_current_operation=lambda agent_type: calls.setdefault("cancel", agent_type)
        ),
        sync_agent_conversation=lambda agent_type, messages, session_id=None, clear_pending=False: (
            "sync",
            agent_type,
            messages,
            session_id,
            clear_pending,
        ),
    )
    fake._records_to_backend_messages = lambda agent_type: [{"role": "user", "content": "trimmed"}]
    fake._submit_coroutine = lambda coro: calls.setdefault("submitted", coro)
    fake._get_panel_for_agent = lambda agent_type: fake.agent_panel
    fake._is_visible_agent = lambda agent_type: True

    row = SimpleNamespace(_message_id="msg-1", _content="old user", _role="user")

    MainWindow._on_message_edit_resend_requested(fake, "main", "new user", row)

    assert calls["truncate"] == (
        "main",
        {"message_id": "msg-1", "content": "old user", "role": "user"},
    )
    assert calls["cancel"] == "main"
    assert calls["submitted"] == ("sync", "main", [{"role": "user", "content": "trimmed"}], "s1", True)
    assert fake._agent_queue_cache["main"] == []
    assert calls["queue_preview"] == []
    assert calls["send_content"] == "new user"


def test_records_to_backend_messages_skips_system_notices_and_tool_results():
    fake = SimpleNamespace()
    fake._conv_store = SimpleNamespace(
        load_messages=lambda agent_type: [
            {"role": "user", "content": "hello"},
            {
                "role": "agent",
                "content": "Interrupted",
                "source": "system",
                "display_mode": "inline_notice",
                "system_notice": True,
                "muted_italic": True,
            },
            {
                "role": "tool_result",
                "content": "send_to_agent",
                "result": "delegated result",
            },
            {"role": "agent", "content": "world"},
        ]
    )

    converted = MainWindow._records_to_backend_messages(fake, "main")

    assert converted == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
