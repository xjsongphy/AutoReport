"""Tests for loop manager (agent lifecycle coordination)."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoreport.config.schema import ApiConfig, AppConfig
from autoreport.core.loops.bus import MessageBus
from autoreport.core.loops.manager import LoopManager
from autoreport.interfaces.types import AgentType


@pytest.fixture
def workspace():
    import shutil
    ws = Path(tempfile.mkdtemp()).resolve()
    for d in ["data", "data/processed", "code", "theory", "tex", "references"]:
        (ws / d).mkdir(parents=True, exist_ok=True)
    yield ws
    shutil.rmtree(ws, ignore_errors=True)


@pytest.fixture
def config_manager():
    cm = MagicMock()
    cm.config = AppConfig()
    cm.config.providers.configurations.append(
        ApiConfig(
            id="test-provider",
            name="Test",
            provider="anthropic",
            api_key="sk-test-key",
            enabled=True,
        )
    )
    return cm


@pytest.fixture
def gui():
    return AsyncMock()


@pytest.fixture
def manager(workspace, config_manager, gui):
    bus = MessageBus()
    return LoopManager(
        workspace=workspace,
        config_manager=config_manager,
        bus=bus,
    )


def test_init(manager):
    assert not manager.is_running


def test_subscribes_to_restart(manager):
    assert manager.is_running is False
    # Verify bus subscription
    from autoreport.interfaces.types import RestartRequest
    assert RestartRequest in manager.bus._subscribers


def test_create_tools_for_main(manager):
    tools = manager._create_tools_for_agent(AgentType.MAIN)
    tool_names = {t.name for t in tools.get_all().values()}
    assert "read" in tool_names
    assert "write_file" in tool_names
    # MAIN delegates — it does not get the exec/shell tool.
    assert "exec" not in tool_names
    # MAIN is the only agent that can dispatch to sub-agents.
    assert "send_to_agent" in tool_names
    assert "report_issue" not in tool_names


def test_create_tools_for_data_analysis(manager):
    tools = manager._create_tools_for_agent(AgentType.DATA_ANALYSIS)
    tool_names = {t.name for t in tools.get_all().values()}
    # Shell execution tool is now named "exec" (formerly "bash").
    assert "exec" in tool_names
    assert "parse_pdf" in tool_names


def test_create_tools_for_theory(manager):
    tools = manager._create_tools_for_agent(AgentType.THEORY)
    tool_names = {t.name for t in tools.get_all().values()}
    assert "read" in tool_names
    assert "write_file" in tool_names
    # THEORY has no shell execution tool.
    assert "exec" not in tool_names
    assert "parse_pdf" in tool_names


def test_create_tools_for_plotting(manager):
    tools = manager._create_tools_for_agent(AgentType.PLOTTING)
    tool_names = {t.name for t in tools.get_all().values()}
    assert "exec" in tool_names
    # PLOTTING never reads reference PDFs directly.
    assert "parse_pdf" not in tool_names


def test_create_tools_write_dirs_main(manager, workspace):
    tools = manager._create_tools_for_agent(AgentType.MAIN)
    write_tool = tools.get("write_file")
    assert write_tool is not None


@pytest.mark.asyncio
@patch("autoreport.core.loops.manager.ProviderFactory")
async def test_start_creates_loops(mock_factory, manager):
    mock_provider = AsyncMock()
    mock_factory.create_provider.return_value = mock_provider

    await manager.start()
    assert manager.is_running
    assert len(manager._loops) == len(AgentType)

    await manager.stop()


@pytest.mark.asyncio
@patch("autoreport.core.loops.manager.ProviderFactory")
async def test_stop_clears_loops(mock_factory, manager):
    mock_provider = AsyncMock()
    mock_factory.create_provider.return_value = mock_provider

    await manager.start()
    assert len(manager._loops) > 0

    await manager.stop()
    assert not manager.is_running
    assert len(manager._loops) == 0


@pytest.mark.asyncio
async def test_start_idempotent(manager):
    manager._running = True
    await manager.start()
    assert manager._running is True


@pytest.mark.asyncio
async def test_stop_idempotent(manager):
    await manager.stop()
    assert not manager.is_running


@pytest.mark.asyncio
async def test_create_checkpoint(manager, gui):
    checkpoint_id = await manager.create_checkpoint("main", "Test checkpoint")
    assert checkpoint_id.startswith("cp_main_")


@pytest.mark.asyncio
async def test_set_agent_debug_mode(manager):
    # Manually add a mock loop
    mock_loop = MagicMock()
    manager._loops[AgentType.DATA_ANALYSIS] = mock_loop

    manager.set_agent_debug_mode("data_analysis", True)
    mock_loop.set_debug_mode.assert_called_once_with(True)


def test_get_agent_debug_mode_not_found(manager):
    assert manager.get_agent_debug_mode("data_analysis") is False


def test_get_agent_debug_mode(manager):
    mock_loop = MagicMock()
    mock_loop.debug_mode = True
    manager._loops[AgentType.DATA_ANALYSIS] = mock_loop

    assert manager.get_agent_debug_mode("data_analysis") is True
