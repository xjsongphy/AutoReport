"""Tests for AgentLoop API debug message publishing."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoreport.core.loops.agent_loop import AgentLoop
from autoreport.core.loops.bus import MessageBus
from autoreport.core.tools.registry import ToolRegistry
from autoreport.config.schema import AgentDefaults
from autoreport.interfaces.types import ApiDebugMessage, UserMessage, AgentType, AgentResponse


@pytest.fixture
def message_bus():
    """Create a message bus for testing."""
    return MessageBus()


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    provider = MagicMock()
    provider.model = "test-model"
    provider.api_key = "test-key"
    provider.chat_stream = AsyncMock()

    # Mock streaming response
    async def mock_stream(*args, **kwargs):
        from autoreport.core.providers.base import LLMStreamChunk
        chunks = [
            LLMStreamChunk(delta="Hello", tool_calls=None, done=False),
            LLMStreamChunk(delta=" world", tool_calls=None, done=False),
            LLMStreamChunk(delta="!", tool_calls=None, done=True),
        ]
        for chunk in chunks:
            yield chunk

    provider.chat_stream = mock_stream
    return provider


@pytest.fixture
def tool_registry():
    """Create a tool registry for testing."""
    return ToolRegistry()


@pytest.fixture
def agent_config():
    """Create agent configuration for testing."""
    return AgentDefaults(
        temperature=0.7,
        max_tokens=4096,
        max_tool_iterations=5,
    )


@pytest.mark.asyncio
async def test_api_debug_message_published_on_success(message_bus, mock_llm_provider, tool_registry, agent_config):
    """AgentLoop should publish ApiDebugMessage on successful API call."""
    workspace = Path("/tmp/test_workspace")
    agent_loop = AgentLoop(
        agent_type=AgentType.MAIN,
        workspace=workspace,
        tools=tool_registry,
        bus=message_bus,
        config=agent_config,
        llm_provider=mock_llm_provider,
    )

    # Track published messages
    debug_messages = []

    async def track_debug(msg):
        if isinstance(msg, ApiDebugMessage):
            debug_messages.append(msg)

    message_bus.subscribe(ApiDebugMessage, track_debug)

    # Start the message bus processing
    bus_task = asyncio.create_task(message_bus.process_queue())

    # Start the agent loop
    await agent_loop.start()

    # Send a user message
    user_msg = UserMessage(
        content="Hello, agent!",
        agent_type=AgentType.MAIN,
    )
    await message_bus.publish(user_msg)

    # Wait for processing
    await asyncio.sleep(0.5)

    # Stop the agent loop
    await agent_loop.stop()

    # Stop the bus
    message_bus.shutdown()
    try:
        await asyncio.wait_for(bus_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Check that ApiDebugMessage was published
    assert len(debug_messages) > 0, "Should publish at least one ApiDebugMessage"

    debug_msg = debug_messages[0]
    assert debug_msg.model == "test-model"
    assert debug_msg.status == "success"
    assert debug_msg.duration_ms >= 0  # Can be 0 for very fast mocks
    assert debug_msg.tokens_in > 0
    assert debug_msg.tokens_out >= 0
    assert debug_msg.error is None


@pytest.mark.asyncio
async def test_api_debug_message_published_on_error(message_bus, tool_registry, agent_config):
    """AgentLoop should publish ApiDebugMessage with error status on API failure."""
    workspace = Path("/tmp/test_workspace")

    # Create a mock provider that raises an error
    error_provider = MagicMock()
    error_provider.model = "error-model"
    error_provider.api_key = "test-key"

    async def mock_stream_error(*args, **kwargs):
        # Yield one chunk then raise error
        from autoreport.core.providers.base import LLMStreamChunk
        yield LLMStreamChunk(delta="Hello", tool_calls=None, done=False)
        raise RuntimeError("API rate limit exceeded")

    error_provider.chat_stream = mock_stream_error

    agent_loop = AgentLoop(
        agent_type=AgentType.MAIN,
        workspace=workspace,
        tools=tool_registry,
        bus=message_bus,
        config=agent_config,
        llm_provider=error_provider,
    )

    # Track published messages
    debug_messages = []

    async def track_debug(msg):
        if isinstance(msg, ApiDebugMessage):
            debug_messages.append(msg)

    message_bus.subscribe(ApiDebugMessage, track_debug)

    # Start the message bus processing
    bus_task = asyncio.create_task(message_bus.process_queue())

    # Start the agent loop
    await agent_loop.start()

    # Send a user message
    user_msg = UserMessage(
        content="Hello, agent!",
        agent_type=AgentType.MAIN,
    )
    await message_bus.publish(user_msg)

    # Wait for processing
    await asyncio.sleep(0.5)

    # Stop the agent loop
    await agent_loop.stop()

    # Stop the bus
    message_bus.shutdown()
    try:
        await asyncio.wait_for(bus_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Check that ApiDebugMessage was published with error status
    assert len(debug_messages) > 0, "Should publish ApiDebugMessage even on error"

    debug_msg = debug_messages[0]
    assert debug_msg.model == "error-model"
    assert debug_msg.status == "error"
    assert "rate limit" in debug_msg.error.lower() or "API rate limit exceeded" in debug_msg.error
    assert debug_msg.duration_ms >= 0


@pytest.mark.asyncio
async def test_api_debug_message_timing(message_bus, mock_llm_provider, tool_registry, agent_config):
    """ApiDebugMessage should include accurate timing information."""
    workspace = Path("/tmp/test_workspace")
    agent_loop = AgentLoop(
        agent_type=AgentType.MAIN,
        workspace=workspace,
        tools=tool_registry,
        bus=message_bus,
        config=agent_config,
        llm_provider=mock_llm_provider,
    )

    # Track published messages
    debug_messages = []

    async def track_debug(msg):
        if isinstance(msg, ApiDebugMessage):
            debug_messages.append(msg)

    message_bus.subscribe(ApiDebugMessage, track_debug)

    # Start the message bus processing
    bus_task = asyncio.create_task(message_bus.process_queue())

    # Start the agent loop
    await agent_loop.start()

    # Send a user message
    user_msg = UserMessage(
        content="Hello, agent!",
        agent_type=AgentType.MAIN,
    )
    await message_bus.publish(user_msg)

    # Wait for processing
    await asyncio.sleep(0.5)

    # Stop the agent loop
    await agent_loop.stop()

    # Stop the bus
    message_bus.shutdown()
    try:
        await asyncio.wait_for(bus_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Check timing
    debug_msg = debug_messages[0]
    # Duration should be reasonable (less than 1 second for mock)
    assert debug_msg.duration_ms < 1000
    # Should be greater than or equal to 0 (can be 0 for very fast mocks)
    assert debug_msg.duration_ms >= 0
