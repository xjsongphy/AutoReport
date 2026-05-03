"""Tests for agent message routing: main vs sub-agent panels."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from autoreport.core.conversations import ConversationStore
from autoreport.interfaces.types import (
    AgentResponse,
    AgentStatus,
    AgentType,
    StatusChange,
    ToolCall as ToolCallMsg,
    ToolResult as ToolResultMsg,
    UserMessage,
)


class TestAgentRoutingInStore:
    """Verify conversation history is correctly isolated per agent type."""

    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ConversationStore(Path(tmpdir))

    def test_main_and_sub_isolated(self, store):
        """Main and sub-agent messages are stored separately."""
        store.append_message("main", "user", "main user msg")
        store.append_message("main", "agent", "main agent reply")
        store.append_message("data_analysis", "user", "da user msg")
        store.append_message("data_analysis", "agent", "da agent reply")

        main_msgs = store.load_messages("main")
        da_msgs = store.load_messages("data_analysis")

        assert len(main_msgs) == 2
        assert main_msgs[0]["role"] == "user"
        assert main_msgs[0]["content"] == "main user msg"
        assert main_msgs[1]["role"] == "agent"
        assert main_msgs[1]["content"] == "main agent reply"

        assert len(da_msgs) == 2
        assert da_msgs[0]["content"] == "da user msg"
        assert da_msgs[1]["content"] == "da agent reply"

    def test_all_agent_types_have_separate_history(self, store):
        """Each agent type has independent conversation history."""
        for at in ["main", "data_analysis", "plotting", "theory", "report"]:
            store.append_message(at, "user", f"msg to {at}")

        for at in ["main", "data_analysis", "plotting", "theory", "report"]:
            msgs = store.load_messages(at)
            assert len(msgs) == 1
            assert msgs[0]["content"] == f"msg to {at}"

    def test_empty_agent_returns_empty_list(self, store):
        """Agent with no messages returns empty list."""
        assert store.load_messages("theory") == []

    def test_tool_calls_isolated_per_agent(self, store):
        """Tool calls are stored per agent."""
        store.append_tool_call("main", "list_dir", {"path": "/"})
        store.append_tool_call("data_analysis", "read_file", {"path": "data.csv"})

        main_msgs = store.load_messages("main")
        da_msgs = store.load_messages("data_analysis")

        assert len(main_msgs) == 1
        assert main_msgs[0]["role"] == "tool_call"

        assert len(da_msgs) == 1
        assert da_msgs[0]["role"] == "tool_call"
        assert da_msgs[0]["content"] == "read_file"

    def test_sessions_isolated_per_agent_type(self, store):
        """New session creates fresh history for a specific agent."""
        store.append_message("main", "user", "first")
        sid1 = store.new_session("Session 2", agent_type="main")
        # New session — no messages yet
        msgs = store.load_messages("main")
        assert len(msgs) == 0

    def test_lazy_session_no_file_until_message(self, store):
        """No session file created until actual message is appended."""
        assert not store._sessions_file.exists()
        store.append_message("main", "user", "hello")
        assert store._sessions_file.exists()


class TestAgentTypeStringConversion:
    """AgentType enum value for routing."""

    def test_main_agent_type_value(self):
        assert AgentType.MAIN.value == "main"

    def test_sub_agent_type_values(self):
        assert AgentType.DATA_ANALYSIS.value == "data_analysis"
        assert AgentType.PLOTTING.value == "plotting"
        assert AgentType.THEORY.value == "theory"
        assert AgentType.REPORT.value == "report"

    def test_all_types_distinct(self):
        all_types = {
            AgentType.MAIN.value,
            AgentType.DATA_ANALYSIS.value,
            AgentType.PLOTTING.value,
            AgentType.THEORY.value,
            AgentType.REPORT.value,
        }
        assert len(all_types) == 5  # All distinct


class TestMessageTypesForRouting:
    """Verify message types carry correct agent_type for panel routing."""

    def test_agent_response_has_agent_type(self):
        msg = AgentResponse(
            agent_type=AgentType.DATA_ANALYSIS,
            content="result",
            streaming=False,
        )
        assert msg.agent_type == AgentType.DATA_ANALYSIS
        assert str(msg.agent_type) == "data_analysis"

    def test_status_change_has_agent_type(self):
        msg = StatusChange(
            agent_type=AgentType.PLOTTING,
            status="thinking",
        )
        assert msg.agent_type == AgentType.PLOTTING

    def test_tool_call_has_agent_type(self):
        msg = ToolCallMsg(
            agent_type=AgentType.THEORY,
            tool_name="read_file",
            arguments={"path": "ref.pdf"},
        )
        assert msg.agent_type == AgentType.THEORY

    def test_tool_result_has_agent_type(self):
        msg = ToolResultMsg(
            agent_type=AgentType.REPORT,
            tool_name="exec",
            result="OK",
        )
        assert msg.agent_type == AgentType.REPORT

    def test_user_message_defaults_to_main(self):
        msg = UserMessage(content="hello")
        assert msg.agent_type == AgentType.MAIN
