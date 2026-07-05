"""Tests for agent loop processing engine."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from autoreport.config.schema import AgentDefaults
from autoreport.core.loops.agent_loop import AgentLoop
from autoreport.core.loops.bus import MessageBus
from autoreport.core.providers.base import LLMResponse, LLMToolCall
from autoreport.interfaces.types import (
    AgentStatus,
    AgentType,
    QueueUpdateMessage,
    ReportMessage,
    SystemNotice,
    TaskUpdateMessage,
    UserMessage,
)


@pytest.fixture
def mock_gui():
    gui = AsyncMock()
    return gui


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.model = "test-model"
    provider.chat.return_value = LLMResponse(
        content="I will help you.",
        tool_calls=[],
        usage={"input_tokens": 10, "output_tokens": 5},
    )

    # Add streaming support mock (async generator that yields chunks then done)
    async def mock_chat_stream(*args, **kwargs):
        from autoreport.core.providers.base import LLMStreamChunk
        yield LLMStreamChunk(delta="I will help you.")
        yield LLMStreamChunk(delta=None, done=True)

    provider.chat_stream = mock_chat_stream
    return provider


@pytest.fixture
def mock_prompt_loader():
    loader = MagicMock()
    loader.load_prompt.return_value = "You are a test agent.\n\n## Core Rules\n\nDo your job well."
    loader.load_shared_context.return_value = None  # No Common.md in test fixture
    return loader


@pytest.fixture
def config():
    return AgentDefaults(max_tool_iterations=5)


@pytest.fixture
def workspace():
    import shutil
    import tempfile
    ws = Path(tempfile.mkdtemp()).resolve()
    for d in ["data", "plots", "theory", "tex", "references"]:
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
        config=config,
        llm_provider=mock_provider,
        prompt_loader=mock_prompt_loader,
        loop_manager=None,  # Not needed for tests
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
async def test_system_prompt_first_call_loads_and_caches(agent_loop, mock_prompt_loader):
    prompt = await agent_loop._get_system_prompt()
    mock_prompt_loader.load_prompt.assert_called_once_with("main")
    assert "test agent" in prompt


@pytest.mark.asyncio
async def test_system_prompt_second_call_uses_cache(agent_loop, mock_prompt_loader):
    await agent_loop._get_system_prompt()  # first call — loads & caches
    prompt = await agent_loop._get_system_prompt()  # second call — cached
    # load_prompt should still only be called once
    assert mock_prompt_loader.load_prompt.call_count == 1
    assert "test agent" in prompt


@pytest.mark.asyncio
async def test_system_prompt_cached_across_calls(agent_loop, mock_prompt_loader):
    await agent_loop._get_system_prompt()  # first call
    await agent_loop._get_system_prompt()  # second call
    await agent_loop._get_system_prompt()  # third call
    assert mock_prompt_loader.load_prompt.call_count == 1  # Cached — not called again


@pytest.mark.asyncio
async def test_process_message(agent_loop, mock_provider, mock_gui):
    msg = UserMessage(content="Hello", agent_type=AgentType.MAIN)
    await agent_loop._process_message(msg)

    # Agent publishes AgentResponse to bus (not GUI call)
    assert agent_loop.status == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_process_message_passes_message_id_to_pre_checkpoint(agent_loop):
    manager = MagicMock()
    manager.create_checkpoint = AsyncMock(return_value="cp_main_0001")
    agent_loop._loop_manager = manager

    msg = UserMessage(
        content="Hello",
        agent_type=AgentType.MAIN,
        message_id="msg-rollback-1",
    )
    await agent_loop._process_message(msg)

    manager.create_checkpoint.assert_awaited_once()
    assert manager.create_checkpoint.await_args.kwargs["message_id"] == "msg-rollback-1"


@pytest.mark.asyncio
async def test_process_message_with_tool_calls(agent_loop, mock_provider, mock_gui):
    tc = LLMToolCall(id="call_1", name="read", arguments={"path": "test.txt"})

    # Mock streaming: first yields chunks, then tool calls at end
    async def mock_chat_stream_with_tools(*args, **kwargs):
        from autoreport.core.providers.base import LLMStreamChunk
        yield LLMStreamChunk(delta="Reading file...")
        # At end, yield tool calls
        yield LLMStreamChunk(delta=None, tool_calls=[tc], done=True)

    mock_provider.chat_stream = mock_chat_stream_with_tools

    # Second call (after tool execution) returns final response
    mock_provider.chat.return_value = LLMResponse(content="Done!", tool_calls=[])

    tool_called = []
    async def mock_tool(**kwargs):
        tool_called.append(kwargs)
        return {"content": "file data"}

    agent_loop.tools.get = lambda name: mock_tool if name == "read" else None

    msg = UserMessage(content="Read file", agent_type=AgentType.MAIN)
    await agent_loop._process_message(msg)

    # Tool was executed with correct arguments
    assert len(tool_called) == 1
    assert tool_called[0] == {"path": "test.txt"}


@pytest.mark.asyncio
async def test_process_message_error(agent_loop, mock_provider, mock_gui):
    # Make chat_stream raise an error
    async def mock_chat_stream_error(*args, **kwargs):
        raise RuntimeError("API error")
        yield  # Never reached, but makes this an async generator

    mock_provider.chat_stream = mock_chat_stream_error

    msg = UserMessage(content="Hello", agent_type=AgentType.MAIN)
    await agent_loop._process_message(msg)

    assert agent_loop.status == AgentStatus.ERROR
    # Error is published to bus (not GUI call)


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


@pytest.mark.asyncio
async def test_handle_user_message_publishes_queue_update(agent_loop):
    msg = UserMessage(content="Hello", agent_type=AgentType.MAIN)
    await agent_loop._handle_user_message(msg)

    published = list(agent_loop.bus._queue._queue)
    assert any(isinstance(item, QueueUpdateMessage) for item in published)


@pytest.mark.asyncio
async def test_local_task_update_does_not_queue_llm_turn(agent_loop):
    msg = TaskUpdateMessage(
        task_id="tk001",
        action="completed",
        source_agent=AgentType.MAIN,
        target_agent=AgentType.MAIN,
        brief="local bookkeeping",
    )

    await agent_loop._handle_task_update(msg)

    assert agent_loop._message_queue.empty()


@pytest.mark.asyncio
async def test_delegated_task_update_still_queues_relevant_llm_turn(agent_loop):
    msg = TaskUpdateMessage(
        task_id="tk002",
        action="completed",
        source_agent=AgentType.MAIN,
        target_agent=AgentType.REPORT,
        brief="delegated report",
    )

    await agent_loop._handle_task_update(msg)

    queued = await agent_loop._message_queue.get()
    assert queued.source == "system"
    assert "report 已完成" in queued.content


def test_format_tool_result_dict(agent_loop):
    result = agent_loop._format_tool_result({"key": "value"})
    assert "key" in result


def test_format_tool_result_strips_ui_only_fields(agent_loop):
    result = agent_loop._format_tool_result({
        "status": "ok",
        "completion_summary": "visible in tool result",
        "_ui_summary": "ui only",
        "_ui_detail": "detail only",
    })
    assert "status" in result
    assert "completion_summary" not in result
    assert "_ui_summary" not in result
    assert "_ui_detail" not in result


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


@pytest.mark.asyncio
async def test_loop_marks_turn_reported_on_own_report(agent_loop):
    """A ReportMessage from this agent sets _turn_reported = True."""
    assert agent_loop._turn_reported is False
    await agent_loop.bus.publish(ReportMessage(
        agent_type=agent_loop.agent_type,
        task_id="tk1",
        report_type="reply",
        content="done",
    ))
    msg = await asyncio.wait_for(agent_loop.bus._queue.get(), timeout=1)
    await agent_loop.bus._notify_subscribers(msg)
    assert agent_loop._turn_reported is True


@pytest.mark.asyncio
async def test_loop_ignores_report_from_other_agent(agent_loop):
    """A ReportMessage from a different agent does not set our flag."""
    agent_loop._turn_reported = False
    await agent_loop.bus.publish(ReportMessage(
        agent_type=AgentType.PLOTTING,  # fixture loop is MAIN
        task_id="tk1",
        report_type="reply",
        content="done",
    ))
    msg = await asyncio.wait_for(agent_loop.bus._queue.get(), timeout=1)
    await agent_loop.bus._notify_subscribers(msg)
    assert agent_loop._turn_reported is False


def _sub_loop(workspace, config, mock_provider, mock_prompt_loader, board):
    """A sub-agent (plotting) loop with a real task board, for guard tests."""
    from autoreport.core.loops.agent_loop import AgentLoop
    bus = MessageBus()
    tools = MagicMock()
    tools.get_definitions.return_value = []
    loop = AgentLoop(
        agent_type=AgentType.PLOTTING,
        workspace=workspace,
        tools=tools,
        bus=bus,
        config=config,
        llm_provider=mock_provider,
        prompt_loader=mock_prompt_loader,
        loop_manager=None,
        task_board=board,
    )
    return loop


async def _drain_bus(bus) -> None:
    """Deliver queued messages to subscribers (no process_loop in tests)."""
    while True:
        try:
            msg = bus._queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        await bus._notify_subscribers(msg)


@pytest.mark.asyncio
async def test_sub_guard_reprompts_when_no_report(workspace, config, mock_provider, mock_prompt_loader):
    """A sub-agent ending a Main-dispatched turn without report is re-prompted."""
    from autoreport.core.tools.task_board import TaskBoard
    board = TaskBoard()
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    loop = _sub_loop(workspace, config, mock_provider, mock_prompt_loader, board)

    notices = []
    loop.bus.subscribe(SystemNotice, lambda m: notices.append(m))

    msg = UserMessage(content="draw plot", agent_type=AgentType.PLOTTING, source="main_agent")
    await loop._process_message(msg)
    await _drain_bus(loop.bus)

    # mock_provider returns text-only (no tool call), so report is never called.
    # The guard should fire and publish at least one SystemNotice before going IDLE.
    assert any("report" in n.content for n in notices)


@pytest.mark.asyncio
async def test_main_guard_blocks_idle_with_blocked_tasks(workspace, config, mock_provider, mock_prompt_loader):
    """Main may not go IDLE while it has BLOCKED tasks; a SystemNotice is published."""
    from autoreport.core.tools.task_board import TaskBoard
    board = TaskBoard()
    bus = MessageBus()
    tools = MagicMock()
    tools.get_definitions.return_value = []
    from autoreport.core.loops.agent_loop import AgentLoop
    loop = AgentLoop(
        agent_type=AgentType.MAIN, workspace=workspace, tools=tools, bus=bus,
        config=config, llm_provider=mock_provider, prompt_loader=mock_prompt_loader,
        loop_manager=None, task_board=board,
    )
    board.create_task(AgentType.MAIN, AgentType.PLOTTING, "draw", task_id="tk1")
    board.block_task("tk1", target_agent=AgentType.PLOTTING)

    notices = []
    bus.subscribe(SystemNotice, lambda m: notices.append(m))

    msg = UserMessage(content="coordinate", agent_type=AgentType.MAIN, source="user")
    await loop._process_message(msg)
    await _drain_bus(bus)

    assert any("被阻塞" in n.content for n in notices)
