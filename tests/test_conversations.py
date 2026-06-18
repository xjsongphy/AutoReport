"""Tests for ConversationStore multi-session support."""

import json
import tempfile
from datetime import datetime, timedelta
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
        """new_session should set a new in-memory current session id.

        Lazy design: new_session only stages the id in memory; it does not persist
        metadata to sessions.json. The session becomes visible in get_sessions()
        only once a message is appended to it.
        """
        sid = store.new_session("Test session")
        assert store.get_current_session_id("main") == sid
        # Lazy: nothing persisted yet, so get_sessions() is still empty.
        assert store.get_sessions() == []
        # sessions.json is not written until a message is appended.
        assert not store._sessions_file.exists()

    def test_switch_session(self, store: ConversationStore):
        """switch_session should change current session (only for persisted sessions).

        switch_session looks up the id in sessions.json, so both sessions must be
        persisted (via append_message) before switching.
        """
        # Create two persisted sessions by appending a message to each.
        store.append_message("main", "user", "first session msg")
        sid1 = store.get_current_session_id("main")

        store.new_session("Second")
        store.append_message("main", "user", "second session msg")
        sid2 = store.get_current_session_id("main")
        assert sid2 != sid1

        assert store.switch_session(sid1, "main") is True
        assert store.get_current_session_id("main") == sid1

    def test_switch_nonexistent_session(self, store: ConversationStore):
        """switch_session with invalid ID should return False."""
        assert store.switch_session("nonexistent-id") is False

    def test_rename_session(self, store: ConversationStore):
        """rename_session should update the session name for a persisted session.

        rename_session looks up the id in sessions.json, so the session must first
        be persisted via append_message.
        """
        store.append_message("main", "user", "hello")
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
        """Deleting the only persisted session should reassign current id and stay empty.

        Lazy design: after deleting the only session, sessions.json is empty and
        get_sessions() returns []. delete_session reassigns the in-memory current
        session id to a fresh UUID (different from the deleted one) so the next
        append_message will start a brand-new session.
        """
        store.append_message("main", "user", "only msg")
        sid = store.get_current_session_id("main")
        store.delete_session(sid)

        # No persisted sessions remain.
        sessions = store.get_sessions()
        assert sessions == []
        # Current id is reassigned to a fresh UUID (not the deleted one).
        assert store.get_current_session_id("main") != sid
        # Appending to the fresh id creates a brand-new persisted session.
        store.append_message("main", "user", "new session msg")
        sessions = store.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] != sid

    def test_sessions_sorted_newest_first(self, store: ConversationStore):
        """get_sessions should return sessions newest first.

        Lazy design: a session only appears in get_sessions() after a message is
        appended. To create two persisted sessions with distinct names we append a
        message to each, then rename so the names survive (appending auto-renames
        the main session from its first message, so we rename afterward).
        """
        store.new_session("Second")
        store.append_message("main", "user", "second msg")
        store.rename_session(store.get_current_session_id("main"), "Second")

        store.new_session("Third")
        store.append_message("main", "user", "third msg")
        store.rename_session(store.get_current_session_id("main"), "Third")

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
        store.append_tool_call("main", "read", {"path": "test.py"}, extra={"summary": "Read"})
        store.append_tool_result("main", "read", result="content", extra={"summary": "Done"})

        msgs = store.load_messages("main")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "tool_call"
        assert msgs[0]["content"] == "read"
        assert msgs[0]["summary"] == "Read"
        assert msgs[1]["role"] == "tool_result"
        assert msgs[1]["summary"] == "Done"

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
        """Auto-name should only apply when name is still '新对话'.

        Lazy design: the session must be persisted (via append_message) before it
        can be renamed. First message auto-names it; an explicit rename after that
        must survive a subsequent user message.
        """
        store.append_message("main", "user", "initial msg")
        sid = store.get_current_session_id("main")
        assert store.rename_session(sid, "Custom") is True
        store.append_message("main", "user", "Should not rename")
        sessions = store.get_sessions()
        assert sessions[0]["name"] == "Custom"

    def test_sub_agent_no_auto_name(self, store: ConversationStore):
        """Sub-agent messages should not trigger auto-naming.

        Auto-naming (rename_current_session_from_first_message) only fires for the
        main agent, so the persisted metadata name stays '新对话'. Note: get_sessions()
        derives a *display* name from the first user message when the stored name is
        the default, so we assert against the persisted metadata directly.
        """
        store.append_message("data_analysis", "user", "Data analysis request")
        sessions = store.get_sessions()
        assert len(sessions) == 1
        # Persisted metadata name is unchanged (auto-naming did not fire).
        meta = store._load_sessions_metadata()
        assert meta[0]["name"] == "新对话"
        # The display name returned by get_sessions() is derived from the message,
        # but that is presentation only — the underlying stored name is the default.
        assert sessions[0]["name"] == "Data analysis request"


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


class TestGetSessionsStaleFilter:
    """get_sessions filters out empty sessions (no .jsonl with content).

    NOTE: The current implementation does NOT perform timestamp-based stale
    filtering. A session appears in get_sessions() if and only if at least one of
    its per-agent .jsonl files exists and is non-empty, regardless of timestamp.
    These tests exercise that actual behavior.
    """

    def _write_sessions_json(self, conv_dir: Path, sessions: list[dict]) -> None:
        """Helper: write sessions.json directly."""
        with open(conv_dir / "sessions.json", "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)

    def test_fresh_empty_session_is_filtered(self, tmp_path):
        """A newly created (in-memory) empty session does NOT appear in get_sessions.

        new_session() only stages an id in memory; it neither writes sessions.json
        nor any .jsonl. get_sessions() therefore returns nothing until a message
        is appended.
        """
        store = ConversationStore(tmp_path)
        store.new_session("Fresh empty session")

        sessions = store.get_sessions()
        assert sessions == []

    def test_stale_empty_session_is_filtered(self, tmp_path):
        """A session present in sessions.json but with no .jsonl is excluded."""
        conv_dir = tmp_path / ".autoreport" / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)

        stale_ts = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
        self._write_sessions_json(conv_dir, [
            {"id": "stale-session-1", "name": "Old empty", "timestamp": stale_ts, "preview": ""},
        ])

        store = ConversationStore(tmp_path)
        sessions = store.get_sessions()
        assert len(sessions) == 0

    def test_session_with_messages_always_kept(self, tmp_path):
        """A session with messages should be kept even if its timestamp is old."""
        conv_dir = tmp_path / ".autoreport" / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)

        stale_ts = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        session_id = "old-but-not-empty"
        self._write_sessions_json(conv_dir, [
            {"id": session_id, "name": "Has messages", "timestamp": stale_ts, "preview": ""},
        ])

        # Create a non-empty jsonl for the main agent
        main_dir = conv_dir / "main"
        main_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = main_dir / f"{session_id}.jsonl"
        jsonl_path.write_text(
            json.dumps({"role": "user", "content": "hello"}) + "\n",
            encoding="utf-8",
        )

        store = ConversationStore(tmp_path)
        sessions = store.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == session_id

    def test_mix_of_empty_and_nonempty(self, tmp_path):
        """Only sessions with a non-empty .jsonl are kept; empty ones are filtered."""
        conv_dir = tmp_path / ".autoreport" / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)

        stale_ts = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
        fresh_ts = datetime.now().isoformat(timespec="seconds")
        old_ts = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")

        nonempty_id = "nonempty-session"
        self._write_sessions_json(conv_dir, [
            {"id": "stale-empty", "name": "Stale", "timestamp": stale_ts, "preview": ""},
            {"id": "fresh-empty", "name": "Fresh", "timestamp": fresh_ts, "preview": ""},
            {"id": nonempty_id, "name": "HasMsg", "timestamp": old_ts, "preview": ""},
        ])

        # Add a message only to the non-empty session.
        main_dir = conv_dir / "main"
        main_dir.mkdir(parents=True, exist_ok=True)
        (main_dir / f"{nonempty_id}.jsonl").write_text(
            json.dumps({"role": "user", "content": "msg"}) + "\n",
            encoding="utf-8",
        )

        store = ConversationStore(tmp_path)
        sessions = store.get_sessions()
        ids = [s["id"] for s in sessions]
        # Both empty sessions are filtered regardless of timestamp.
        assert "stale-empty" not in ids
        assert "fresh-empty" not in ids
        assert nonempty_id in ids
        assert len(sessions) == 1

    def test_empty_jsonl_session_is_filtered(self, tmp_path):
        """A session whose .jsonl exists but is empty (0 bytes) is excluded."""
        conv_dir = tmp_path / ".autoreport" / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)

        self._write_sessions_json(conv_dir, [
            {"id": "bad-ts", "name": "Bad timestamp", "timestamp": "not-a-date", "preview": ""},
        ])

        # Empty .jsonl for the main agent — exists but 0 bytes.
        main_dir = conv_dir / "main"
        main_dir.mkdir(parents=True, exist_ok=True)
        (main_dir / "bad-ts.jsonl").write_text("", encoding="utf-8")

        store = ConversationStore(tmp_path)
        sessions = store.get_sessions()
        assert sessions == []
