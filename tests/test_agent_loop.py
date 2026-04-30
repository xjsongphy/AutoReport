"""Tests for agent loop processing engine."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoreport.config.schema import AgentDefaults
from autoreport.core.loops.agent_loop import AgentLoop
from autoreport.core.loops.bus import MessageBus
from autoreport.core.providers.base import LLMResponse, Message as LLMMessage, ToolCall
from autoreport.interfaces.types import AgentStatus, AgentType, UserMessage


@pytest.fixture
def mock_gui():
    gui = AsyncMock()
    return gui


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content="I will help you.",
        tool_calls=[],
        usage={"input_tokens": 10, "output_tokens": 5},
    )
    return provider


@pytest.fixture
def mock_prompt_loader():
    loader = MagicMock()
    loader.load_identity.return_value = "You are a test agent."
    loader.load_full.return_value = "Full instructions for testing."
    return loader


@pytest.fixture
def config():
    return AgentDefaults(max_tool_iterations=5)


@pytest.fixture
def workspace():
    import shutil
    import tempfile
    ws = Path(tempfile.mkdtemp()).resolve()
    for d in ["data", "code", "theory", "tex", "references"]:
        (ws / d).mkdir()
    yield ws
    shutil.rmtree(ws, ignore_errors=True)


@pytest.fixture
def agent_loop(workspace, config, mock_gui, mock_provider, mock_prompt_loader):
    bus = MessageBus()
    tools = MagicMock()
    tools.get_definitions.return_value = []

    loop = AgentLoop(
        agent_type=AgentType.MAIN,
        workspace=workspace,
        tools=tools,
        bus=bus,
        gui=mock_gui,
        config=config,
        llm_provider=mock_provider,
        prompt_loader=mock_prompt_loader,
    )
    return loop


def test_init_subscribes_to_bus(agent_loop):
    """AgentLoop subscribes to UserMessage on init."""
    assert UserMessage in agent_loop.bus._subscribers


def test_status_initial(agent_loop):
    assert agent_loop.status == AgentStatus.IDLE


def test_debug_mode_default_off(agent_loop):
    assert agent_loop.debug_mode is False


def test_set_debug_mode_enabled(agent_loop):
    agent_loop.set_debug_mode(True)
    assert agent_loop.debug_mode is True
    # Should unsubscribe from bus
    assert len(agent_loop.bus._subscribers.get(UserMessage, [])) == 0


def test_set_debug_mode_disabled(agent_loop):
    agent_loop.set_debug_mode(True)
    agent_loop.set_debug_mode(False)
    assert agent_loop.debug_mode is False
    # Should re-subscribe to bus
    assert len(agent_loop.bus._subscribers.get(UserMessage, [])) == 1


@pytest.mark.asyncio
async def test_progressive_prompt_first_call(agent_loop, mock_prompt_loader):
    prompt = await agent_loop._get_system_prompt()
    mock_prompt_loader.load_identity.assert_called_once_with("main")
    assert prompt == "You are a test agent."


@pytest.mark.asyncio
async def test_progressive_prompt_second_call(agent_loop, mock_prompt_loader):
    await agent_loop._get_system_prompt()  # identity
    prompt = await agent_loop._get_system_prompt()  # full
    mock_prompt_loader.load_full.assert_called_once_with("main")
    assert "test agent" in prompt
    assert "Full instructions" in prompt


@pytest.mark.asyncio
async def test_progressive_prompt_cached(agent_loop, mock_prompt_loader):
    await agent_loop._get_system_prompt()  # identity
    await agent_loop._get_system_prompt()  # full
    prompt = await agent_loop._get_system_prompt()  # cached
    assert mock_prompt_loader.load_full.call_count == 1  # Not called again


@pytest.mark.asyncio
async def test_process_message(agent_loop, mock_provider, mock_gui):
    msg = UserMessage(content="Hello", agent_type=AgentType.MAIN)
    await agent_loop._process_message(msg)

    mock_provider.chat.assert_called_once()
    mock_gui.display_agent_message.assert_called_once()
    assert agent_loop.status == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_process_message_with_tool_calls(agent_loop, mock_provider, mock_gui):
    tc = ToolCall(id="call_1", name="read_file", arguments={"path": "test.txt"})
    mock_provider.chat.return_value = LLMResponse(
        content="",
        tool_calls=[tc],
    )

    # Second call returns final response
    mock_provider.chat.side_effect = [
        LLMResponse(content="", tool_calls=[tc]),
        LLMResponse(content="Done!", tool_calls=[]),
    ]

    mock_tool = AsyncMock(return_value={"content": "file data"})
    agent_loop.tools.get.return_value = mock_tool

    msg = UserMessage(content="Read file", agent_type=AgentType.MAIN)
    await agent_loop._process_message(msg)

    assert mock_provider.chat.call_count == 2


@pytest.mark.asyncio
async def test_process_message_error(agent_loop, mock_provider, mock_gui):
    mock_provider.chat.side_effect = RuntimeError("API error")

    msg = UserMessage(content="Hello", agent_type=AgentType.MAIN)
    await agent_loop._process_message(msg)

    assert agent_loop.status == AgentStatus.ERROR
    mock_gui.show_error.assert_called_once()


@pytest.mark.asyncio
async def test_handle_user_message_filters_by_agent_type(agent_loop):
    msg = UserMessage(content="Hello", agent_type=AgentType.THEORY)
    await agent_loop._handle_user_message(msg)
    assert agent_loop._message_queue.empty()


@pytest.mark.asyncio
async def test_handle_user_message_debug_mode_filters_main_agent(agent_loop):
    agent_loop.set_debug_mode(True)
    msg = UserMessage(
        content="Coordinate",
        agent_type=AgentType.MAIN,
        source="main_agent",
    )
    await agent_loop._handle_user_message(msg)
    assert agent_loop._message_queue.empty()


@pytest.mark.asyncio
async def test_handle_user_message_queues(agent_loop):
    msg = UserMessage(content="Hello", agent_type=AgentType.MAIN)
    await agent_loop._handle_user_message(msg)
    assert not agent_loop._message_queue.empty()


def test_format_tool_result_dict(agent_loop):
    result = agent_loop._format_tool_result({"key": "value"})
    assert "key" in result


def test_format_tool_result_string(agent_loop):
    result = agent_loop._format_tool_result("plain text")
    assert result == "plain text"


def test_get_agent_type_str(agent_loop):
    assert agent_loop._get_agent_type_str() == "main"


@pytest.mark.asyncio
async def test_start_stop(agent_loop):
    await agent_loop.start()
    assert agent_loop._running is True

    await agent_loop.stop()
    assert agent_loop._running is False


@pytest.mark.asyncio
async def test_start_idempotent(agent_loop):
    await agent_loop.start()
    await agent_loop.start()
    assert agent_loop._running is True
    await agent_loop.stop()
