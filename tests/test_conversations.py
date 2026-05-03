"""Tests for ConversationStore multi-session support."""

import json
import tempfile
from pathlib import Path

import pytest

from autoreport.core.conversations import ConversationStore


@pytest.fixture
def store() -> ConversationStore:
    """Create a ConversationStore with a temp workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ConversationStore(Path(tmpdir))


class TestSessionManagement:
    """Session CRUD operations."""

    def test_initial_session_created(self, store: ConversationStore):
        """Sessions are lazily created — no session on init without messages."""
        sessions = store.get_sessions()
        assert len(sessions) == 0  # Lazy: no session until first message

    def test_session_created_on_first_message(self, store: ConversationStore):
        """First append_message should auto-create a session and rename from content."""
        store.append_message("main", "user", "hello")
        sessions = store.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["name"] == "hello"  # Renamed from first message content

    def test_sessions_file_not_created_on_init(self, store: ConversationStore):
        """sessions.json should NOT exist until first message is saved."""
        assert not store._sessions_file.exists()

    def test_new_session(self, store: ConversationStore):
        """new_session should create and switch to a new session."""
        sid = store.new_session("Test session")
        assert store.get_current_session_id("main") == sid
        sessions = store.get_sessions()
        assert len(sessions) == 1  # Lazy: only the explicitly created one
        assert sessions[0]["id"] == sid
        assert sessions[0]["name"] == "Test session"

    def test_switch_session(self, store: ConversationStore):
        """switch_session should change current session."""
        sid1 = store.get_current_session_id("main")
        sid2 = store.new_session("Second")
        assert store.get_current_session_id("main") == sid2

        assert store.switch_session(sid1, "main") is True
        assert store.get_current_session_id("main") == sid1

    def test_switch_nonexistent_session(self, store: ConversationStore):
        """switch_session with invalid ID should return False."""
        assert store.switch_session("nonexistent-id") is False

    def test_rename_session(self, store: ConversationStore):
        """rename_session should update the session name."""
        sid = store.get_current_session_id("main")
        assert store.rename_session(sid, "Renamed") is True
        sessions = store.get_sessions()
        assert sessions[0]["name"] == "Renamed"

    def test_rename_nonexistent_session(self, store: ConversationStore):
        """rename_session with invalid ID should return False."""
        assert store.rename_session("nonexistent-id", "X") is False

    def test_delete_session(self, store: ConversationStore):
        """delete_session should remove the session and its files."""
        sid1 = store.get_current_session_id("main")
        store.append_message("main", "user", "hello")
        sid2 = store.new_session("To delete")

        store.delete_session(sid2)
        sessions = store.get_sessions()
        assert all(s["id"] != sid2 for s in sessions)
        # Current should have switched back
        assert store.get_current_session_id("main") == sid1

    def test_delete_only_session_creates_new(self, store: ConversationStore):
        """Deleting the only session should create a new one."""
        sid = store.get_current_session_id("main")
        store.delete_session(sid)
        sessions = store.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] != sid

    def test_sessions_sorted_newest_first(self, store: ConversationStore):
        """get_sessions should return sessions newest first."""
        store.new_session("Second")
        store.new_session("Third")
        sessions = store.get_sessions()
        assert len(sessions) == 2
        assert sessions[0]["name"] == "Third"
        assert sessions[1]["name"] == "Second"


class TestMessagePersistence:
    """Message read/write with session support."""

    def test_append_and_load(self, store: ConversationStore):
        """append_message + load_messages round-trip."""
        store.append_message("main", "user", "Hello")
        store.append_message("main", "agent", "World")

        msgs = store.load_messages("main")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello"
        assert msgs[1]["role"] == "agent"

    def test_messages_isolated_per_session(self, store: ConversationStore):
        """Messages in different sessions should be isolated."""
        store.append_message("main", "user", "Session A")
        sid_a = store.get_current_session_id("main")

        store.new_session("Session B")
        store.append_message("main", "user", "Session B")

        store.switch_session(sid_a, "main")
        msgs_a = store.load_messages("main")
        assert any(m["content"] == "Session A" for m in msgs_a)
        assert not any(m["content"] == "Session B" for m in msgs_a)

    def test_messages_isolated_per_agent(self, store: ConversationStore):
        """Messages for different agent types should be in separate files."""
        store.append_message("main", "user", "Main msg")
        store.append_message("data_analysis", "user", "Data msg")

        main_msgs = store.load_messages("main")
        data_msgs = store.load_messages("data_analysis")
        assert len(main_msgs) == 1
        assert main_msgs[0]["content"] == "Main msg"
        assert len(data_msgs) == 1
        assert data_msgs[0]["content"] == "Data msg"

    def test_tool_call_round_trip(self, store: ConversationStore):
        """append_tool_call and append_tool_result should be readable."""
        store.append_tool_call("main", "read_file", {"path": "test.py"})
        store.append_tool_result("main", "read_file", result="content")

        msgs = store.load_messages("main")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "tool_call"
        assert msgs[0]["content"] == "read_file"
        assert msgs[1]["role"] == "tool_result"

    def test_load_empty_agent(self, store: ConversationStore):
        """load_messages for an agent with no messages should return []."""
        assert store.load_messages("plotting") == []

    def test_extra_fields_preserved(self, store: ConversationStore):
        """Extra fields passed to append_message should be preserved."""
        store.append_message("main", "user", "hi", extra={"source": "main_agent"})
        msgs = store.load_messages("main")
        assert msgs[0]["source"] == "main_agent"

    def test_load_messages_limit(self, store: ConversationStore):
        """load_messages should respect the limit parameter."""
        for i in range(10):
            store.append_message("main", "user", f"msg {i}")
        msgs = store.load_messages("main", limit=5)
        assert len(msgs) == 5
        # Should be the most recent 5
        assert msgs[0]["content"] == "msg 5"


class TestAutoNaming:
    """Auto-name session from first user message."""

    def test_auto_name_from_first_message(self, store: ConversationStore):
        """Session should be auto-named from the first main agent user message."""
        store.append_message("main", "user", "分析这个实验数据")
        sessions = store.get_sessions()
        assert sessions[0]["name"] == "分析这个实验数据"

    def test_auto_name_truncates(self, store: ConversationStore):
        """Auto-name should truncate to 30 characters."""
        long_msg = "A" * 50
        store.append_message("main", "user", long_msg)
        sessions = store.get_sessions()
        assert len(sessions[0]["name"]) == 30

    def test_auto_name_only_once(self, store: ConversationStore):
        """Auto-name should only apply when name is still '新对话'."""
        store.rename_session(store.get_current_session_id("main"), "Custom")
        store.append_message("main", "user", "Should not rename")
        sessions = store.get_sessions()
        assert sessions[0]["name"] == "Custom"

    def test_sub_agent_no_auto_name(self, store: ConversationStore):
        """Sub-agent messages should not trigger auto-naming."""
        store.append_message("data_analysis", "user", "Data analysis request")
        sessions = store.get_sessions()
        assert sessions[0]["name"] == "新对话"


class TestClearAndLifecycle:
    """clear / clear_current_session."""

    def test_clear_agent(self, store: ConversationStore):
        """clear should remove messages for a specific agent."""
        store.append_message("main", "user", "hello")
        store.clear("main")
        assert store.load_messages("main") == []

    def test_clear_current_session(self, store: ConversationStore):
        """clear_current_session should clear all agents for current session."""
        store.append_message("main", "user", "m1")
        store.append_message("data_analysis", "user", "m2")
        store.clear_current_session()
        assert store.load_messages("main") == []
        assert store.load_messages("data_analysis") == []

    def test_get_agent_types_with_history(self, store: ConversationStore):
        """Should list agent types that have messages."""
        assert store.get_agent_types_with_history() == []
        store.append_message("main", "user", "hi")
        store.append_message("data_analysis", "user", "hi")
        result = store.get_agent_types_with_history()
        assert "main" in result
        assert "data_analysis" in result

    def test_get_last_user_message(self, store: ConversationStore):
        """Should return the last user message."""
        store.append_message("main", "agent", "response")
        store.append_message("main", "user", "first")
        store.append_message("main", "user", "second")
        assert store.get_last_user_message("main") == "second"


class TestMigration:
    """Migration from old flat-file format."""

    def test_migrate_old_files(self):
        """Old flat .jsonl files should be migrated to session subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            conv_dir = workspace / ".autoreport" / "conversations"
            conv_dir.mkdir(parents=True)

            for agent in ["main", "data_analysis"]:
                path = conv_dir / f"{agent}.jsonl"
                path.write_text(
                    json.dumps({"role": "user", "content": "old msg"}, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

            store = ConversationStore(workspace)

            assert not (conv_dir / "main.jsonl").exists()

            msgs = store.load_messages("main")
            assert len(msgs) == 1
            assert msgs[0]["content"] == "old msg"

            sessions = store.get_sessions()
            assert sessions[0]["name"] == "历史对话"

    def test_no_migration_when_sessions_exist(self):
        """If sessions.json already exists, old files should not be migrated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            conv_dir = workspace / ".autoreport" / "conversations"
            conv_dir.mkdir(parents=True)

            (conv_dir / "sessions.json").write_text("[]", encoding="utf-8")
            (conv_dir / "main.jsonl").write_text("{}", encoding="utf-8")

            ConversationStore(workspace)

            assert (conv_dir / "main.jsonl").exists()
