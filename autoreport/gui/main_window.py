"""Main application window."""

from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QSplitter,
    QHBoxLayout,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt, QTimer
from loguru import logger

from ...interfaces.types import Message
from ...interfaces.protocol import BackendAPI, GUIAPI
from .widgets.file_tree import FileTreeWidget
from .widgets.preview import PreviewWidget
from .widgets.agent_panel import AgentPanel


class MainWindow(QMainWindow, GUIAPI):
    """Main application window."""

    def __init__(self, backend: BackendAPI, workspace: Path):
        """Initialize main window.

        Args:
            backend: Backend API for communication.
            workspace: Project workspace directory.
        """
        super().__init__()
        self.backend = backend
        self.workspace = Path(workspace).resolve()

        self.setWindowTitle("AutoReport - 物理实验报告撰写系统")
        self.resize(1400, 900)

        # Setup UI
        self._setup_ui()

        # Subscribe to backend messages
        self.backend.subscribe_to_messages(self._handle_backend_message)

        logger.info("Main window initialized for workspace: {}", self.workspace)

    def _setup_ui(self) -> None:
        """Setup user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter for left/center/right sections
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter)

        # Left section: File tree
        self.file_tree = FileTreeWidget(self.workspace)
        self.file_tree.setMinimumWidth(200)
        self.file_tree.setMaximumWidth(400)
        self.file_tree.directory_selected.connect(self._on_directory_selected)
        main_splitter.addWidget(self.file_tree)

        # Center section: Preview
        self.preview = PreviewWidget(self.workspace)
        self.preview.setMinimumWidth(400)
        main_splitter.addWidget(self.preview)

        # Right section: Agent panels
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(right_splitter)

        # Top-right: Main agent panel
        self.main_agent_panel = AgentPanel("main", "Main Agent")
        self.main_agent_panel.setMinimumHeight(300)
        right_splitter.addWidget(self.main_agent_panel)

        # Bottom-right: Sub-agent panel
        self.sub_agent_panel = AgentPanel("sub", "Sub Agent")
        self.sub_agent_panel.setMinimumHeight(300)
        right_splitter.addWidget(self.sub_agent_panel)

        # Set splitter sizes
        main_splitter.setSizes([250, 500, 650])
        right_splitter.setSizes([300, 300])

        # Connect signals
        self.main_agent_panel.message_sent.connect(self._on_main_agent_message)
        self.sub_agent_panel.message_sent.connect(self._on_sub_agent_message)
        self.sub_agent_panel.debug_mode_toggled.connect(self._on_debug_mode_toggled)

        # Hide debug button on main agent panel (debug mode is for sub-agents only)
        self.main_agent_panel.hide_debug_button(hide=True)

    def _on_directory_selected(self, directory: str) -> None:
        """Handle directory selection.

        Args:
            directory: Selected directory name (data, refs, theory, code, tex).
        """
        self.preview.set_directory(directory)

        # Update sub-agent panel based on directory
        agent_map = {
            "data": "data_analysis",
            "refs": "main",
            "theory": "theory",
            "code": "plotting",
            "tex": "report",
        }
        agent_type = agent_map.get(directory, "sub")
        self.sub_agent_panel.set_agent_type(agent_type)

    async def _on_main_agent_message(self, content: str) -> None:
        """Handle main agent message send.

        Args:
            content: Message content.
        """
        await self.backend.send_user_message(content, "main")

    async def _on_sub_agent_message(self, content: str) -> None:
        """Handle sub-agent message send.

        Args:
            content: Message content.
        """
        agent_type = self.sub_agent_panel.agent_type
        await self.backend.send_user_message(content, agent_type)

    def _on_debug_mode_toggled(self, enabled: bool) -> None:
        """Handle debug mode toggle.

        Args:
            enabled: Whether debug mode is enabled.
        """
        agent_type = self.sub_agent_panel.agent_type
        self.backend.set_agent_debug_mode(agent_type, enabled)

    async def _handle_backend_message(self, message: Message) -> None:
        """Handle message from backend.

        Args:
            message: Message from backend.
        """
        from ...interfaces.types import (
            AgentResponse,
            ToolCall,
            ToolResult,
            StatusChange,
            Error,
            Checkpoint,
        )

        if isinstance(message, AgentResponse):
            await self._handle_agent_response(message)
        elif isinstance(message, ToolCall):
            await self._handle_tool_call(message)
        elif isinstance(message, ToolResult):
            await self._handle_tool_result(message)
        elif isinstance(message, StatusChange):
            await self._handle_status_change(message)
        elif isinstance(message, Error):
            await self._handle_error(message)
        elif isinstance(message, Checkpoint):
            await self._handle_checkpoint(message)

    async def _handle_agent_response(self, message: AgentResponse) -> None:
        """Handle agent response.

        Args:
            message: Agent response message.
        """
        panel = self._get_panel_for_agent(message.agent_type)
        panel.add_message("agent", message.content)

    async def _handle_tool_call(self, message: ToolCall) -> None:
        """Handle tool call.

        Args:
            message: Tool call message.
        """
        panel = self._get_panel_for_agent(message.agent_type)
        panel.add_tool_call(message.tool_name, message.arguments)

    async def _handle_tool_result(self, message: ToolResult) -> None:
        """Handle tool result.

        Args:
            message: Tool result message.
        """
        panel = self._get_panel_for_agent(message.agent_type)
        panel.add_tool_result(message.tool_name, message.result, message.error)

    async def _handle_status_change(self, message: StatusChange) -> None:
        """Handle status change.

        Args:
            message: Status change message.
        """
        panel = self._get_panel_for_agent(message.agent_type)
        panel.set_status(message.status, message.extra)

    async def _handle_error(self, message: Error) -> None:
        """Handle error.

        Args:
            message: Error message.
        """
        # Show error in relevant panel or main panel
        panel = self.main_agent_panel
        panel.add_error(message.source, message.message)

    async def _handle_checkpoint(self, message: Checkpoint) -> None:
        """Handle checkpoint.

        Args:
            message: Checkpoint message.
        """
        self.main_agent_panel.add_checkpoint(message.checkpoint_id, message.description)

    def _get_panel_for_agent(self, agent_type: str) -> AgentPanel:
        """Get agent panel for agent type.

        Args:
            agent_type: Agent type string.

        Returns:
            Corresponding agent panel.
        """
        if agent_type == "main":
            return self.main_agent_panel
        else:
            return self.sub_agent_panel

    # GUIAPI implementation

    async def display_agent_message(
        self,
        agent_type: str,
        content: str,
        message_id: str | None = None
    ) -> None:
        """Display an agent message in GUI."""
        panel = self._get_panel_for_agent(agent_type)
        panel.add_message("agent", content)

    async def show_tool_call(
        self,
        agent_type: str,
        tool_name: str,
        arguments: dict
    ) -> None:
        """Show a tool being executed."""
        panel = self._get_panel_for_agent(agent_type)
        panel.add_tool_call(tool_name, arguments)

    async def show_tool_result(
        self,
        agent_type: str,
        tool_name: str,
        result: Any,
        error: str | None = None
    ) -> None:
        """Show a tool result."""
        panel = self._get_panel_for_agent(agent_type)
        panel.add_tool_result(tool_name, result, error)

    async def update_agent_status(
        self,
        agent_type: str,
        status: str,
        extra: dict | None = None
    ) -> None:
        """Update agent status display."""
        panel = self._get_panel_for_agent(agent_type)
        panel.set_status(status, extra or {})

    async def show_error(
        self,
        source: str,
        message: str,
        details: dict | None = None
    ) -> None:
        """Show an error in GUI."""
        self.main_agent_panel.add_error(source, message)

    async def add_checkpoint(
        self,
        checkpoint_id: str,
        description: str,
        file_states: dict
    ) -> None:
        """Add a checkpoint to the timeline."""
        self.main_agent_panel.add_checkpoint(checkpoint_id, description)
