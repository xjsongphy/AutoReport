"""Main application window."""

import asyncio
import sys
from pathlib import Path

from loguru import logger
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core.conversations import ConversationStore
from ..interfaces.protocol import BackendAPI
from ..interfaces.types import (
    AgentFeedback,
    AgentResponse,
    Checkpoint,
    Error,
    Message,
    QueueUpdateMessage,
    StatusChange,
    ToolCall,
    ToolResult,
    UserMessage,
)
from ..utils.agent_labels import get_agent_badge, get_agent_title
from ..utils.logging_config import ui_logger
from .scale import dpi_scale
from .theme import get_theme_colors
from .title_bar import TitleBar
from .widgets.agent_panel import AgentPanel
from .widgets.file_tree import FileTreeWidget
from .widgets.preview import PreviewWidget
from .widgets.ui_utils import combo_box_qss, compact_tooltip_qss


class MainWindow(QMainWindow):
    """Main application window.

    Implements the GUIAPI protocol via duck-typing (cannot use multiple
    inheritance with QMainWindow because of metaclass conflict).
    """

    _message_signal = pyqtSignal(object)
    _rollback_finished_signal = pyqtSignal(str, object)

    def __init__(
        self,
        backend: BackendAPI,
        workspace: Path,
        debug_agents: list[str] | None = None,
    ):
        super().__init__()
        self.backend = backend
        self.workspace = Path(workspace).resolve()
        self._async_loop: asyncio.AbstractEventLoop | None = None
        self._debug_agents = {str(a) for a in (debug_agents or [])}
        self._agent_status_cache: dict[str, tuple[str, dict]] = {}
        self._title_bar: TitleBar | None = None
        self._splitter_sizes_initialized = False

        self.setWindowTitle("AutoReport")
        self.resize(1400, 900)

        # Set frameless window flag for custom title bar
        # Different handling for each platform
        if sys.platform == "darwin":
            # macOS: Use CustomizeWindowHint without FramelessWindowHint
            # This keeps the window draggable but allows custom title bar
            # We'll hide system buttons via the custom title bar
            flags = self.windowFlags() | Qt.WindowType.CustomizeWindowHint
            self.setWindowFlags(flags)
        else:
            # Windows/Linux: Use full FramelessWindowHint
            flags = self.windowFlags() | Qt.WindowType.FramelessWindowHint
            self.setWindowFlags(flags)

        # Add window shadow for depth (platform-specific)
        self._apply_window_shadow()

        self._conv_store = ConversationStore(workspace)

        self._apply_theme()
        self._setup_ui()
        QTimer.singleShot(0, self._apply_splitter_sizes)
        QTimer.singleShot(100, self._apply_splitter_sizes)
        # Load persisted histories for main and currently selected sub-agent.
        # Do an immediate load plus a deferred reload after the first event-loop
        # tick to avoid startup ordering glitches in the sub-agent selector.
        self._load_conversations()
        QTimer.singleShot(0, self._load_conversations)

        self._message_signal.connect(self._dispatch_backend_message)
        self.backend.subscribe_to_messages(self._on_bus_message)
        self._subscribe_to_debug_messages()

        logger.info("Main window initialized for workspace: {}", self.workspace)

    def _apply_window_shadow(self) -> None:
        """Apply window shadow effect for platform-appropriate appearance."""
        if sys.platform == "win32":
            # Windows: Use native DWM shadow
            import ctypes
            from ctypes import wintypes

            # Enable DWM blur behind window
            try:
                hwnd = int(self.winId())
                attribute = ctypes.c_int(2)  # DWMWA_EXTENDED_FRAME_BOUNDS
                if hasattr(ctypes, "windll"):
                    # This is a simplified version - full implementation would
                    # use DwmExtendFrameIntoClientArea for proper Aero glass effect
                    pass
            except Exception:
                pass
        elif sys.platform == "darwin":
            # macOS: Shadow is automatic for windows
            pass

    def _apply_theme(self) -> None:
        """Apply theme matching VS Code Copilot Chat color variables."""
        s = dpi_scale()

        # Helper: scale pixel value for DPI
        def px(v: int) -> str:
            return f"{round(v * s)}px"

        # Get unified theme colors
        c = get_theme_colors()
        self._theme_colors = c

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {c["bg"]};
                color: {c["fg"]};
            }}
            QWidget {{
                color: {c["fg"]};
                font-family: "SF Pro Text", "PingFang SC", "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
                font-size: {px(13)};
            }}
            QSplitter::handle {{
                background-color: {c["border"]};
            }}
            QSplitter::handle:horizontal {{
                width: {px(1)};
            }}
            QSplitter::handle:vertical {{
                height: {px(1)};
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: {px(8)};
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c["scrollbar"]};
                min-height: {px(30)};
                border-radius: {px(4)};
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {c["scrollbar_hover"]};
            }}
            QScrollBar::handle:vertical:pressed {{
                background-color: {c["scrollbar_hover"]};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background-color: transparent;
                height: {px(8)};
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {c["scrollbar"]};
                min-width: {px(30)};
                border-radius: {px(4)};
            }}
            QScrollBar::handle:horizontal:hover,
            QScrollBar::handle:horizontal:pressed {{
                background-color: {c["scrollbar_hover"]};
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
            {compact_tooltip_qss("QToolTip")}

            /* ---- Panel Header ---- */
            #panelHeader {{
                background-color: {c["panel_bg"]};
                border-bottom: 1px solid {c["border"]};
                padding-right: 1px;
            }}
            /* Agent Panel background */
            AgentPanel {{
                background-color: {c["panel_bg"]};
            }}
            #panelTitle {{
                font-size: {px(13)};
                font-weight: {c["fw_semibold"]};
                color: {c["fg"]};
                font-family: "SF Pro Text", "PingFang SC", "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
            }}
            #panelStatus {{
                font-size: {px(11)};
                color: {c["status_idle"]};
            }}
            {combo_box_qss(
                "#subAgentSelector",
                border_color=c["border"],
                background_color=c["surface"],
                foreground_color=c["fg"],
                hover_border_color=c["focus"],
                selection_bg=c["selection"],
                selection_fg=c["fg"],
                font_size=12,
                padding="2px 24px 2px 8px",
                radius=c["radius_md"],
                popup_radius=c["radius_md"],
                item_radius=c["radius_sm"],
            )}
            #headerAction {{
                background-color: transparent;
                color: {c["header_action"]};
                border: none;
                border-radius: {px(4)};
                font-size: {px(13)};
            }}
            #headerAction:hover {{
                background-color: {c["hover"]};
                color: {c["header_action_hover"]};
            }}
            /* ---- Input Container (with working border space) ---- */
            #composerHost {{
                background-color: {c["panel_bg"]};
            }}
            #inputContainer {{
                background-color: {c["panel_bg"]};
                border: 1px solid {c["border"]};
                border-radius: {px(10)};
                margin: {px(8)} 0 0 0;
            }}
            #composerInputTop {{
                background-color: {c["input_bg"]};
                border-top-left-radius: {px(8)};
                border-top-right-radius: {px(8)};
            }}
            #composerDivider {{
                background-color: {c["border"]};
                margin: 0;
            }}

            /* ---- Input Bar ---- */
            #inputBar {{
                background-color: transparent;
            }}

            /* ---- Secondary Toolbar ---- */
            #secondaryToolbar {{
                background-color: {c["input_bg"]};
                border-bottom-left-radius: {px(8)};
                border-bottom-right-radius: {px(8)};
            }}
            #composerBottomGap {{
                background-color: {c["panel_bg"]};
            }}
            #secondaryBtn {{
                background-color: transparent;
                color: {c["muted"]};
                border: none;
                border-radius: {px(4)};
                font-size: {px(14)};
            }}
            #secondaryBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}
            #secondaryStatus {{
                font-size: {px(11)};
                color: {c["muted"]};
            }}
            /* VS Code send button */
            #sendBtn {{
                background-color: {c["send_bg"]};
                color: {c["primaryBtnFg"]};
                border: 1px solid {c["send_bg"]};
                border-radius: {px(6)};
                font-size: {px(14)};
                font-weight: {c["fw_bold"]};
                padding: 0;
                min-width: {px(22)};
                min-height: {px(22)};
                max-width: {px(22)};
                max-height: {px(22)};
            }}
            #sendBtn:hover {{
                background-color: {c["send_hover"]};
                border-color: {c["send_hover"]};
            }}
            #stopBtn {{
                background-color: transparent;
                color: {c["status_error"]};
                border: 1px solid {c["status_error"]};
                border-radius: {px(6)};
                font-size: {px(14)};
                font-weight: {c["fw_bold"]};
                padding: 0;
                min-width: {px(22)};
                min-height: {px(22)};
                max-width: {px(22)};
                max-height: {px(22)};
            }}
            #stopBtn:hover {{
                background-color: {c["hover"]};
            }}

            #contextSeparator {{
                font-size: {px(11)};
                color: {c["muted"]};
                padding: 0 {px(2)};
            }}
            #contextAttachmentBtn {{
                background-color: transparent;
                border: none;
                border-radius: {px(4)};
                color: {c["muted"]};
                font-size: {px(11)};
                padding: 0 {px(3)};
                min-height: {px(22)};
                max-height: {px(22)};
            }}
            #contextAttachmentBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}

            /* ---- User Message — right-aligned bubble ---- */
            #userMessageRow {{
                background-color: transparent;
            }}
            #userMessageBubble {{
                background-color: {c["bubble_bg"]};
                border: 1px solid {c["border"]};
                border-radius: {px(12)};
            }}
            #userMessageBubble:hover {{
                background-color: {c["bubble_hover"]};
            }}
            #userEditBubble {{
                background-color: {c["edit_bubble_bg"]};
                border: 1px solid {c["edit_bubble_border"]};
                border-radius: {px(12)};
            }}
            #userMessageText {{
                color: {c["editor_fg"]};
                font-size: {px(13)};
                line-height: 1.5;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
            }}
            #userMessageBubbleContainer {{
                background-color: transparent;
            }}
            #userMsgFooter {{
                background-color: transparent;
                padding-top: {px(2)};
            }}
            #userEditBtn, #userCopyBtn {{
                background-color: transparent;
                color: {c["muted"]};
                border: none;
                border-radius: {px(4)};
                padding: 0;
                font-size: {px(15)};
            }}
            #userEditBtn:hover, #userCopyBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}
            #userSaveBtn {{
                background-color: {c["primary"]};
                color: {c["primaryBtnFg"]};
                border: none;
                border-radius: {px(4)};
                padding: {px(4)} {px(10)};
                font-size: {px(12)};
                font-weight: {c["fw_semibold"]};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
            }}
            #userSaveBtn:hover {{
                background-color: {c["primary_hover"]};
            }}
            #userSaveBtn:disabled {{
                background-color: {c["muted"]};
                opacity: 0.5;
            }}
            #userCancelBtn {{
                background-color: transparent;
                color: {c["fg"]};
                border: 1px solid {c["border"]};
                border-radius: {px(4)};
                padding: {px(4)} {px(10)};
                font-size: {px(12)};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
            }}
            #userCancelBtn:hover {{
                background-color: {c["hover"]};
                border-color: {c["muted"]};
            }}
            #queuePreview {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
            }}
            #queueTitle {{
                font-size: {px(11)};
                color: {c["muted"]};
                font-weight: {c["fw_semibold"]};
            }}
            #queueItems {{
                font-size: {px(12)};
                color: {c["fg"]};
                line-height: 1.4;
            }}

            /* ---- Agent Message — flat with avatar ---- */
            #agentHeader {{
                background-color: transparent;
            }}
            #agentAvatar {{
                background-color: {c["avatar_bg"]};
                color: {c["avatar_fg"]};
                border-radius: {px(12)};
                font-size: {px(12)};
            }}
            #agentUsername {{
                font-size: {px(13)};
                font-weight: {c["fw_semibold"]};
                color: {c["fg"]};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
            }}
            #agentMessageRow {{
                background-color: transparent;
            }}
            #agentMessageText {{
                color: {c["editor_fg"]};
                font-size: {px(13)};
                line-height: 1.5;
                background-color: transparent;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
            }}
            #msgCoordination {{
                font-size: {px(11)};
                color: {c["muted"]};
                font-style: italic;
                padding-left: 0;
                margin-bottom: {px(4)};
            }}

            /* ---- Message Footer (hover toolbar) ---- */
            #msgFooter {{
                background-color: transparent;
                padding-top: {px(4)};
            }}
            #copyBtn {{
                background-color: transparent;
                color: {c["muted"]};
                border: none;
                border-radius: {px(4)};
                padding: 0;
                font-size: {px(15)};
            }}
            #copyBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]};
            }}

            /* ---- Code Block ---- */
            #codeBlockCard {{
                background-color: {c["card"]};
                border: 1px solid {c["border"]};
                border-radius: {px(6)};
                margin: {px(4)} 0;
            }}
            #codeBlockHeader {{
                background-color: transparent;
                border-bottom: 1px solid {c["border"]};
            }}
            #codeBlockLang {{
                font-size: {px(11)};
                color: {c["muted"]};
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
            }}
            #codeBlockCopyBtn {{
                background-color: transparent;
                color: transparent;
                border: none;
                border-radius: {px(4)};
                font-size: {px(15)};
                padding: 0;
            }}
            #codeBlockCard:hover #codeBlockCopyBtn {{
                color: {c["muted"]};
            }}
            #codeBlockCopyBtn:hover {{
                background-color: {c["hover"]};
                color: {c["fg"]} !important;
            }}
            #codeBlockContent {{
                color: {c["fg"]};
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
                font-size: {px(12)};
            }}

            /* ---- Tool Call Group ---- */
            #toolCallHeader {{
                background-color: transparent;
                border: none;
                border-radius: {px(4)};
            }}
            #toolCallHeader:hover {{
                background-color: {c["hover"]};
            }}
            #toolCallHeaderText {{
                color: {c["tool_fg"]};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
                font-size: {px(12)};
                font-weight: {c["fw_medium"]};
            }}
            #toolCallDetail {{
                color: {c["tool_detail"]};
                font-family: "Segoe UI", "SF Pro", -apple-system, sans-serif;
                font-size: {px(11)};
                padding: {px(1)} 0 {px(2)} {px(12)};
            }}
            #bashDetailCard {{
                background-color: #23272f;
                border: 1px solid #353b46;
                border-radius: {px(8)};
                margin-left: {px(12)};
            }}
            #bashDetailRow {{
                background-color: transparent;
            }}
            #bashDetailTag {{
                color: #9aa3b2;
                font-size: {px(10)};
                font-weight: {c["fw_semibold"]};
                min-width: {px(20)};
            }}
            #bashDetailText {{
                color: #d5dbe5;
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
                font-size: {px(11)};
            }}
            #bashDetailDivider {{
                background-color: #353b46;
                border: none;
            }}
            #bashCopyBtn {{
                background-color: transparent;
                border: none;
                color: #9aa3b2;
                font-size: {px(10)};
                padding: {px(2)} {px(4)};
            }}
            #bashCopyBtn:hover {{
                color: #e2e8f0;
            }}

            /* ---- Status Indicator ---- */
            #statusSpinner {{
                color: {c["spinner_fg"]};
                font-size: {px(13)};
            }}
            #statusHeader {{
                color: {c["muted"]};
                font-size: 12px;
            }}
        """)

    def _setup_menu_bar(self, menubar: QMenuBar) -> None:
        """Setup the application menu bar."""
        menubar.setObjectName("mainMenuBar")

        # File menu
        file_menu = menubar.addMenu("文件")
        file_menu.setObjectName("fileMenu")

        logger.info("Menu bar created - File menu added")

        # Add menu items
        new_file_act = file_menu.addAction("新建文件")
        new_file_act.triggered.connect(self._on_new_file)

        new_folder_act = file_menu.addAction("新建文件夹")
        new_folder_act.triggered.connect(self._on_new_folder)

        file_menu.addSeparator()

        open_file_act = file_menu.addAction("打开文件...")
        open_file_act.triggered.connect(self._on_open_file)

        open_folder_act = file_menu.addAction("打开文件夹...")
        open_folder_act.triggered.connect(self._on_open_folder)

        file_menu.addSeparator()

        save_act = file_menu.addAction("保存")
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self._on_save_file)

        file_menu.addSeparator()

        new_window_act = file_menu.addAction("新建窗口")
        new_window_act.triggered.connect(self._on_new_window)

        file_menu.addSeparator()
        quit_act = QAction("退出 AutoReport", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.setMenuRole(QAction.MenuRole.QuitRole)
        quit_act.triggered.connect(QApplication.closeAllWindows)
        file_menu.addAction(quit_act)

        # Set window title bar color (Windows only)
        if hasattr(self, "setWindowProperty"):
            self.setWindowProperty("Appearance", "DWMWindowAccentPolicy", 0)  # Disable accent

    def _update_window_title(self) -> None:
        """Update window title to show current file."""
        base_title = "AutoReport"

        # Check if preview exists (may not during initialization)
        if not hasattr(self, 'preview'):
            self.setWindowTitle(base_title)
            return

        current_file = self.preview.current_file

        if current_file:
            rel_path = current_file.relative_to(self.workspace)
            self.setWindowTitle(f"{rel_path} - {base_title}")
        else:
            self.setWindowTitle(base_title)

    def _on_new_file(self) -> None:
        """Handle new file action."""
        # Delegate to file tree
        self.file_tree._new_file()

    def _on_new_folder(self) -> None:
        """Handle new folder action."""
        # Delegate to file tree
        self.file_tree._new_folder()

    def _on_open_file(self) -> None:
        """Handle open file action."""
        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(self, "打开文件")
        if file_path:
            # TODO: Import/open the file
            logger.info("Open file requested: {}", file_path)

    def _on_open_folder(self) -> None:
        """Handle open folder action."""
        from PyQt6.QtWidgets import QFileDialog

        folder_path = QFileDialog.getExistingDirectory(self, "打开文件夹")
        if folder_path:
            # TODO: Switch workspace
            logger.info("Open folder requested: {}", folder_path)

    def _on_save_file(self) -> None:
        """Save the active file in the preview panel."""
        if not self.preview.save_current_file():
            logger.debug("Save skipped: no editable active file")

    def _on_new_window(self) -> None:
        """Handle new window action."""
        # TODO: Launch new window
        logger.info("New window requested")

    def _setup_ui(self) -> None:
        # Create container
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        if sys.platform == "darwin":
            # macOS: Use native title bar with system menu bar
            main_layout = QHBoxLayout(central_widget)
            main_layout.setContentsMargins(0, 0, 0, 0)

            # Use system menu bar
            self._setup_menu_bar(self.menuBar())
            self._title_bar = None

            main_splitter = QSplitter(Qt.Orientation.Horizontal)
            main_splitter.setChildrenCollapsible(False)
            main_layout.addWidget(main_splitter)
        else:
            # Windows/Linux: Use custom title bar
            main_layout = QVBoxLayout(central_widget)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # Custom title bar
            self._title_bar = TitleBar(self)
            main_layout.addWidget(self._title_bar)

            # Setup menu bar in custom title bar
            self._setup_menu_bar(self._title_bar.get_menu_bar())

            # Main content area
            content_area = QWidget(self)
            content_layout = QHBoxLayout(content_area)
            content_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.addWidget(content_area)

            main_splitter = QSplitter(Qt.Orientation.Horizontal)
            main_splitter.setChildrenCollapsible(False)
            content_layout.addWidget(main_splitter)

        # Left: File tree
        self.file_tree = FileTreeWidget(self.workspace)
        # Don't override minimum width - let FileTreeWidget handle it
        self.file_tree.directory_selected.connect(self._on_directory_selected)
        self.file_tree.file_selected.connect(self._on_file_selected)
        self.file_tree.path_changed.connect(self._on_file_tree_path_changed)
        main_splitter.addWidget(self.file_tree)

        # Center: Preview
        self.preview = PreviewWidget(self.workspace)
        self.preview.setMinimumWidth(300)
        self.preview.file_changed.connect(self._update_window_title)
        main_splitter.addWidget(self.preview)

        # Right: Agent panels side-by-side (Sub Agent | Main Agent)
        self.sub_agent_panel = AgentPanel("sub", get_agent_title("sub"), self.workspace)
        main_splitter.addWidget(self.sub_agent_panel)

        self.main_agent_panel = AgentPanel("main", get_agent_title("main"), self.workspace)
        main_splitter.addWidget(self.main_agent_panel)

        for index in range(main_splitter.count()):
            main_splitter.setCollapsible(index, False)

        # Set stretch factors for proportional sizing
        # file_tree: 20%, preview: 40%, sub_agent: 20%, main_agent: 20%
        main_splitter.setStretchFactor(0, 20)   # file_tree
        main_splitter.setStretchFactor(1, 40)   # preview
        main_splitter.setStretchFactor(2, 20)   # sub_agent_panel
        main_splitter.setStretchFactor(3, 20)   # main_agent_panel

        # Store main_splitter for resize handling
        self._main_splitter = main_splitter
        self._apply_splitter_sizes(force=True)

        # macOS reliability: make Cmd+Q work even when menu role shortcut
        # isn't dispatched by the native menu chain.
        self._quit_shortcut = QShortcut(QKeySequence.StandardKey.Quit, self)
        self._quit_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._quit_shortcut.activated.connect(self.close)
        self._setup_app_shortcuts()

        # Connect signals
        self._rollback_finished_signal.connect(self._on_rollback_finished)
        self.main_agent_panel.message_sent.connect(self._on_main_agent_message)
        self.main_agent_panel.file_context_attached.connect(self._on_main_agent_file_context)
        self.sub_agent_panel.message_sent.connect(self._on_sub_agent_message)
        self.sub_agent_panel.file_context_attached.connect(self._on_sub_agent_file_context)

        self.main_agent_panel.history_requested.connect(lambda: self._on_history_requested("main"))
        self.main_agent_panel.new_conversation_requested.connect(lambda: self._on_new_conversation_requested("main"))
        self.main_agent_panel.session_selected_from_dropdown.connect(lambda sid: self._on_session_selected(sid, "main"))
        self.main_agent_panel.delete_session_requested.connect(self._on_delete_session)
        self.main_agent_panel.rename_session_requested.connect(self._on_rename_session)
        self.sub_agent_panel.history_requested.connect(lambda: self._on_history_requested(self.sub_agent_panel.agent_type))
        self.sub_agent_panel.new_conversation_requested.connect(lambda: self._on_new_conversation_requested(self.sub_agent_panel.agent_type))
        self.sub_agent_panel.session_selected_from_dropdown.connect(lambda sid: self._on_session_selected(sid, self.sub_agent_panel.agent_type))
        self.sub_agent_panel.delete_session_requested.connect(self._on_delete_session)
        self.sub_agent_panel.rename_session_requested.connect(self._on_rename_session)
        self.main_agent_panel.interrupt_requested.connect(lambda: self._on_interrupt("main"))
        self.sub_agent_panel.interrupt_requested.connect(lambda: self._on_interrupt(self.sub_agent_panel.agent_type))
        self.sub_agent_panel.agent_type_changed.connect(self._on_sub_agent_type_changed)
        self.main_agent_panel.rollback_requested.connect(
            lambda checkpoint_id, row: self._on_rollback_requested("main", checkpoint_id, row)
        )
        self.sub_agent_panel.rollback_requested.connect(
            lambda checkpoint_id, row: self._on_rollback_requested(self.sub_agent_panel.agent_type, checkpoint_id, row)
        )

        self.preview.selection_changed.connect(self._on_preview_selection_changed)
        self.preview.restore_open_tabs()
        self.main_agent_panel.set_agent_type("main")
        self.sub_agent_panel.set_agent_type("data_analysis")
        self.main_agent_panel.set_debug_mode("main" in self._debug_agents)
        self.sub_agent_panel.set_debug_mode(self.sub_agent_panel.agent_type in self._debug_agents)

        self.main_agent_panel.conversation_cleared.connect(
            lambda: self._on_conversation_cleared("main"))
        self.sub_agent_panel.conversation_cleared.connect(
            lambda: self._on_conversation_cleared(self.sub_agent_panel.agent_type))

    def _on_directory_selected(self, directory: str) -> None:
        ui_logger.debug("MainWindow: directory selected {}", directory)
        # Directory navigation is decoupled from sub-agent switching.
        # Keep current contexts when the event is triggered by file click.
        if not getattr(self, "_file_just_selected", False):
            self.main_agent_panel.clear_file_context()
            self.sub_agent_panel.clear_file_context()
        self._file_just_selected = False

    def _on_preview_selection_changed(self, file_path: str, selected_text: str, start_line: int, end_line: int) -> None:
        if not selected_text:
            self.main_agent_panel.set_opened_file(file_path)
            self.sub_agent_panel.set_opened_file(file_path)
            return
        self.main_agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)
        self.sub_agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)

    def _on_file_selected(self, file_path: Path) -> None:
        ui_logger.debug("MainWindow: file selected {}", file_path.name)
        self._file_just_selected = True
        self.preview.load_file(file_path)
        rel_path = self._relative_path(file_path)
        self.main_agent_panel.set_opened_file(rel_path)
        self.sub_agent_panel.set_opened_file(rel_path)
        logger.debug("File selected: {}", file_path)

    def _on_file_tree_path_changed(self, old_path: Path, new_path: Path) -> None:
        self.preview.update_open_path(old_path, new_path)

    def _relative_path(self, file_path: Path) -> str:
        try:
            return file_path.relative_to(self.workspace).as_posix()
        except ValueError:
            return file_path.as_posix()

    def _setup_app_shortcuts(self) -> None:
        """Install platform-native application shortcuts for editing actions."""
        self._save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self._save_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._save_shortcut.activated.connect(self._on_save_file)

        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self._copy_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._copy_shortcut.activated.connect(lambda: self._dispatch_standard_edit("copy"))

        self._paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self)
        self._paste_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._paste_shortcut.activated.connect(lambda: self._dispatch_standard_edit("paste"))

        self._cut_shortcut = QShortcut(QKeySequence.StandardKey.Cut, self)
        self._cut_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._cut_shortcut.activated.connect(lambda: self._dispatch_standard_edit("cut"))

        self._undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self._undo_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._undo_shortcut.activated.connect(lambda: self._dispatch_standard_edit("undo"))

        self._redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        self._redo_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._redo_shortcut.activated.connect(lambda: self._dispatch_standard_edit("redo"))

        self._select_all_shortcut = QShortcut(QKeySequence.StandardKey.SelectAll, self)
        self._select_all_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._select_all_shortcut.activated.connect(
            lambda: self._dispatch_standard_edit("selectAll")
        )

    def _dispatch_standard_edit(self, method_name: str) -> None:
        """Dispatch standard edit command to focused widget when available."""
        widget = QApplication.focusWidget()
        if widget is None:
            return
        method = getattr(widget, method_name, None)
        if callable(method):
            method()

    def _load_conversations(self) -> None:
        # Restore main + currently selected sub-agent history on startup.
        self._load_conversations_for_agent("main", self.main_agent_panel)
        self._load_conversations_for_agent(self.sub_agent_panel.agent_type, self.sub_agent_panel)
        if hasattr(self.backend, "sync_agent_conversation"):
            self._submit_coroutine(
                self.backend.sync_agent_conversation("main", self._records_to_backend_messages("main"))
            )
            sub_agent = self.sub_agent_panel.agent_type
            self._submit_coroutine(
                self.backend.sync_agent_conversation(sub_agent, self._records_to_backend_messages(sub_agent))
            )

    def _load_conversations_for_agent(self, agent_type: str, panel: AgentPanel) -> None:
        panel._messages_area.clear()
        records = self._conv_store.load_messages(agent_type)
        if not records:
            return
        for rec in records:
            role = rec.get("role", "")
            content = rec.get("content", "")
            if role == "user":
                panel.add_message(
                    "user",
                    content,
                    summary=rec.get("summary"),
                    detail=rec.get("detail"),
                    expandable=rec.get("expandable", True),
                )
            elif role == "agent":
                panel.add_message(
                    "agent",
                    content,
                    summary=rec.get("summary"),
                    detail=rec.get("detail"),
                    expandable=rec.get("expandable", True),
                )
            elif role == "tool_call":
                panel.add_tool_call(
                    content,
                    rec.get("arguments", {}),
                    summary=rec.get("summary"),
                    detail=rec.get("detail"),
                    expandable=rec.get("expandable", True),
                )
            elif role == "tool_result":
                panel.add_tool_result(
                    content,
                    rec.get("result"),
                    rec.get("error"),
                    summary=rec.get("summary"),
                    detail=rec.get("detail"),
                    expandable=rec.get("expandable"),
                )
            elif role == "error":
                panel.add_error(rec.get("source", ""), content)
        logger.info("Loaded {} messages for agent {}", len(records), agent_type)

    def _records_to_backend_messages(self, agent_type: str) -> list[dict[str, str]]:
        """Convert stored records to backend chat history messages."""
        records = self._conv_store.load_messages(agent_type)
        converted: list[dict[str, str]] = []
        for rec in records:
            role = str(rec.get("role", ""))
            content = str(rec.get("content", ""))
            if role == "user":
                converted.append({"role": "user", "content": content})
            elif role == "agent":
                converted.append({"role": "assistant", "content": content})
            elif role == "tool_result":
                result = rec.get("result")
                err = rec.get("error")
                payload = str(result) if result is not None else str(err or "")
                converted.append({"role": "tool", "content": payload})
        return converted

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._async_loop = loop

    def _submit_coroutine(self, coro):
        if self._async_loop is None:
            logger.warning("No async loop set, cannot dispatch coroutine")
            return
        return asyncio.run_coroutine_threadsafe(coro, self._async_loop)

    def _on_main_agent_message(self, content: str) -> None:
        self._conv_store.append_message("main", "user", content)
        self._submit_coroutine(self.backend.send_user_message(content, "main"))

    def _on_sub_agent_message(self, content: str) -> None:
        agent_type = self.sub_agent_panel.agent_type
        self._conv_store.append_message(agent_type, "user", content)
        self._submit_coroutine(self.backend.send_user_message(content, agent_type))

    def _on_main_agent_file_context(self, file_context: dict) -> None:
        """Handle file context attachment for main agent."""
        self._submit_coroutine(self.backend.send_file_context(file_context, "main"))

    def _on_sub_agent_file_context(self, file_context: dict) -> None:
        """Handle file context attachment for sub agent."""
        agent_type = self.sub_agent_panel.agent_type
        self._submit_coroutine(self.backend.send_file_context(file_context, agent_type))

    def _on_sub_agent_type_changed(self, agent_type: str) -> None:
        self.sub_agent_panel.set_agent_type(agent_type)
        self.sub_agent_panel.set_debug_mode(agent_type in self._debug_agents)
        self._load_conversations_for_agent(agent_type, self.sub_agent_panel)
        if hasattr(self.backend, "sync_agent_conversation"):
            self._submit_coroutine(
                self.backend.sync_agent_conversation(agent_type, self._records_to_backend_messages(agent_type))
            )
        cached = self._agent_status_cache.get(agent_type)
        if cached:
            status, extra = cached
            self.sub_agent_panel.set_status(status, extra)
        else:
            self.sub_agent_panel.set_status("idle", {})

    def _on_interrupt(self, agent_type: str) -> None:
        """Handle interrupt request from GUI."""
        self._submit_coroutine(self.backend.interrupt_current_message(agent_type))

    def _on_rollback_requested(self, agent_type: str, checkpoint_id: str, row) -> None:
        reply = QMessageBox.question(
            self,
            "Rollback",
            "Rollback files and conversation to before this message?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        panel = self._get_panel_for_agent(agent_type)
        panel._messages_area.retract_from_row(row)
        future = self._submit_coroutine(self.backend.rollback_to_checkpoint(agent_type, checkpoint_id))
        if future is not None:
            future.add_done_callback(lambda done: self._rollback_finished_signal.emit(agent_type, done))

    def _on_rollback_finished(self, agent_type: str, future) -> None:
        try:
            future.result()
        except Exception as exc:
            logger.warning("Rollback failed for {}: {}", agent_type, exc)
            QMessageBox.warning(self, "Rollback Failed", str(exc))
            return

        self.file_tree.refresh()
        current_file = self.preview.current_file
        if current_file and current_file.exists():
            self.preview.load_file(current_file)

    def _on_bus_message(self, message: Message) -> None:
        self._message_signal.emit(message)

    def _dispatch_backend_message(self, message: Message) -> None:
        from ..interfaces.types import (
            AgentResponse,
            Checkpoint,
            Error,
            QueueUpdateMessage,
            StatusChange,
            TaskUpdateMessage,
            ToolCall,
            ToolResult,
            UserMessage,
        )

        if isinstance(message, AgentResponse):
            self._handle_agent_response(message)
        elif isinstance(message, UserMessage):
            self._handle_user_message(message)
        elif isinstance(message, ToolCall):
            self._handle_tool_call(message)
        elif isinstance(message, ToolResult):
            self._handle_tool_result(message)
        elif isinstance(message, StatusChange):
            self._handle_status_change(message)
        elif isinstance(message, Error):
            self._handle_error(message)
        elif isinstance(message, Checkpoint):
            self._handle_checkpoint(message)
        elif isinstance(message, TaskUpdateMessage):
            self._handle_task_update_msg(message)
        elif isinstance(message, AgentFeedback):
            self._handle_agent_feedback(message)
        elif isinstance(message, QueueUpdateMessage):
            self._handle_queue_update(message)

    def _handle_agent_response(self, message: AgentResponse) -> None:
        agent_str = str(message.agent_type)
        if agent_str != "main" and agent_str != self.sub_agent_panel.agent_type:
            if not message.streaming and message.content:
                self._conv_store.append_message(agent_str, "agent", message.content)
            return
        panel = self._get_panel_for_agent(agent_str)
        if getattr(message, "thinking", None):
            panel.append_thinking(message.thinking or "")
            return
        # Empty non-streaming message = completion signal for streaming
        if not message.streaming and not message.content:
            rows = panel._messages_area.get_message_rows()
            for row in reversed(rows):
                if row._role == "agent" and getattr(row, "_content", ""):
                    row.mark_complete()
                    break
            return
        # Non-streaming with content — check if streaming already delivered it
        if not message.streaming and message.content:
            rows = panel._messages_area.get_message_rows()
            if (rows
                    and rows[-1]._role == "agent"
                    and rows[-1]._content
                    and not rows[-1]._complete):
                rows[-1].mark_complete()
                self._conv_store.append_message(agent_str, "agent", rows[-1]._content)
                return
        panel.add_message("agent", message.content, streaming=message.streaming)
        if not message.streaming:
            self._conv_store.append_message(agent_str, "agent", message.content)
            # Mark newly added message as complete (copy button visible)
            rows = panel._messages_area.get_message_rows()
            if rows and rows[-1]._role == "agent":
                rows[-1].mark_complete()

    def _handle_user_message(self, message: UserMessage) -> None:
        agent_str = str(message.agent_type)
        if agent_str != "main" and agent_str != self.sub_agent_panel.agent_type:
            self._conv_store.append_message(
                agent_str,
                "user",
                message.content,
                extra={"source": message.source},
            )
            return
        source_key = str(message.source or "user")
        is_agent_message = source_key not in {"user", "system"}
        is_coordination = source_key == "main_agent"
        summary = None
        detail = None
        expandable = True
        if is_agent_message:
            sender = "Main" if source_key == "main_agent" else self._get_agent_display_name(source_key)
            summary, detail, expandable = self._build_inter_agent_summary(
                f"Message From {sender}",
                message.content,
            )

        target_panel = self._get_panel_for_agent(agent_str)
        target_panel.add_message(
            "user",
            message.content,
            source=message.source,
            coordination=is_coordination,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )

        self._conv_store.append_message(
            agent_str,
            "user",
            message.content,
            extra={
                "source": message.source,
                "summary": summary,
                "detail": detail,
                "expandable": expandable,
            },
        )

    def _get_agent_display_name(self, agent_type: str) -> str:
        return get_agent_badge(agent_type)

    def _handle_tool_call(self, message: ToolCall) -> None:
        agent_str = str(message.agent_type)
        if agent_str != "main" and agent_str != self.sub_agent_panel.agent_type:
            self._conv_store.append_tool_call(agent_str, message.tool_name, message.arguments)
            return
        panel = self._get_panel_for_agent(agent_str)
        summary = None
        detail = None
        expandable = True
        if agent_str == "main" and message.tool_name == "send_to_agent":
            target = self._get_agent_display_name(str(message.arguments.get("agent_type", "sub")))
            summary = f"Main To {target}"
            expandable = False

        panel.add_tool_call(
            message.tool_name,
            message.arguments,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )
        self._conv_store.append_tool_call(
            agent_str,
            message.tool_name,
            message.arguments,
            extra={
                "summary": summary,
                "detail": detail,
                "expandable": expandable,
            },
        )

    def _handle_tool_result(self, message: ToolResult) -> None:
        agent_str = str(message.agent_type)
        if agent_str != "main" and agent_str != self.sub_agent_panel.agent_type:
            result_str = str(message.result) if message.result else None
            self._conv_store.append_tool_result(
                agent_str,
                message.tool_name,
                result_str,
                message.error,
            )
            return
        panel = self._get_panel_for_agent(agent_str)
        result_str = str(message.result) if message.result else None
        summary = None
        detail = None
        expandable = None
        safe_error = None
        if message.error:
            safe_error = "Tool execution failed"

        if agent_str == "main" and message.tool_name == "send_to_agent":
            summary, detail, expandable = self._format_send_to_agent_result(message.result, message.error)
            result_str = detail or summary
        elif message.tool_name == "manage_tasks":
            summary, detail, expandable = self._format_manage_tasks_result(message.result, message.error)
            if summary or detail:
                result_str = detail or summary

        panel.add_tool_result(
            message.tool_name,
            message.result,
            safe_error,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )
        self._conv_store.append_tool_result(
            agent_str,
            message.tool_name,
            result_str,
            message.error,
            extra={
                "summary": summary,
                "detail": detail,
                "expandable": expandable,
            },
        )

    def _format_send_to_agent_result(self, result, error: str | None) -> tuple[str, str | None, bool]:
        if error:
            return ("Send To Agent", error, True)

        if not isinstance(result, dict):
            text = str(result).strip() if result is not None else ""
            return ("Sub-agent replied", text or None, bool(text))

        target = self._get_agent_display_name(str(result.get("agent_type", "sub")))
        status = str(result.get("status", "success"))
        response = str(result.get("response", "") or "").strip()

        if status == "delegated":
            detail = str(result.get("message", "") or "").strip() or None
            return (f"Delegated To {target}", detail, bool(detail))

        if status == "timeout":
            detail = str(result.get("error", "") or "").strip() or None
            return (f"{target} did not reply in time", detail, bool(detail))

        if status == "error":
            detail = str(result.get("error", "") or "").strip() or None
            return (f"Send To {target}", detail, bool(detail))

        if not response:
            return (f"{target} replied", None, False)

        first_line = response.splitlines()[0].strip()
        summary = f"{target} replied: {first_line}" if first_line else f"{target} replied"
        detail = response if ("\n" in response or len(response) > len(first_line)) else None
        return (summary, detail, bool(detail))

    def _format_manage_tasks_result(self, result, error: str | None) -> tuple[str | None, str | None, bool | None]:
        if error or not isinstance(result, dict):
            return (None, None, None)

        if str(result.get("status", "")) != "ok":
            return (None, None, None)

        def _rows(items: list[dict], title: str) -> list[str]:
            lines = [f"<b>{title}</b>"]
            shown = 0
            for item in items:
                if shown >= 10:
                    break
                status = str(item.get("status", "pending")).lower()
                brief = str(item.get("brief", "")).strip() or "task"
                done = status == "completed"
                box = "☑" if done else "☐"
                if done:
                    lines.append(f"<span style='color:#9098a3'>{box} <s>{brief}</s></span>")
                else:
                    lines.append(f"<span style='color:#9098a3'>{box} {brief}</span>")
                shown += 1
            if shown == 0:
                lines.append("<span style='color:#9098a3'>—</span>")
            return lines

        todolist = result.get("todolist")
        waitlist = result.get("waitlist")
        if isinstance(todolist, list) and isinstance(waitlist, list):
            detail = "\n".join(_rows(todolist, "Todo") + ["", *(_rows(waitlist, "Waiting"))])
            return ("<b>Todo</b>", detail, True)

        ui_summary = str(result.get("_ui_summary", "") or "").strip()
        ui_detail = str(result.get("_ui_detail", "") or "").strip()
        if not ui_summary and not ui_detail:
            return (None, None, None)
        return (ui_summary or "Task completed", ui_detail or None, bool(ui_detail))

    def _build_inter_agent_summary(self, prefix: str, content: str) -> tuple[str, str | None, bool]:
        response = str(content or "").strip()
        if not response:
            return (prefix, None, False)

        first_line = response.splitlines()[0].strip()
        summary = f"{prefix}: {first_line}" if first_line else prefix
        detail = response if ("\n" in response or len(response) > len(first_line)) else None
        return (summary, detail, bool(detail))

    def _handle_status_change(self, message: StatusChange) -> None:
        agent_str = str(message.agent_type)
        self._agent_status_cache[agent_str] = (str(message.status), dict(message.extra or {}))
        if agent_str == "main":
            self.main_agent_panel.set_status(message.status, message.extra)
            return
        if agent_str == self.sub_agent_panel.agent_type:
            self.sub_agent_panel.set_status(message.status, message.extra)

    def _handle_error(self, message: Error) -> None:
        self.main_agent_panel.add_error(message.source, message.message)

    def _handle_agent_feedback(self, message: AgentFeedback) -> None:
        """Handle AgentFeedback and show collapsed sub-agent issue reports in main."""
        from enum import Enum

        agent_str = message.agent_type.value if isinstance(message.agent_type, Enum) else str(message.agent_type)
        issue_type = message.feedback_type or "issue"
        summary, detail, expandable = self._build_inter_agent_summary(
            f"{self._get_agent_display_name(agent_str)} reported {issue_type}",
            message.content,
        )
        self.main_agent_panel.add_message(
            "agent",
            message.content,
            source=agent_str,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )
        self._conv_store.append_message(
            "main",
            "agent",
            message.content,
            extra={
                "source": agent_str,
                "summary": summary,
                "detail": detail,
                "expandable": expandable,
                "feedback_type": issue_type,
            },
        )

    def _handle_queue_update(self, message: QueueUpdateMessage) -> None:
        agent_str = str(message.agent_type)
        if agent_str != "main" and agent_str != self.sub_agent_panel.agent_type:
            return
        panel = self._get_panel_for_agent(agent_str)
        panel.set_queue_preview(message.queued_messages)

    def _handle_checkpoint(self, message: Checkpoint) -> None:
        agent_str = str(message.agent_type) if hasattr(message, "agent_type") else "main"
        if agent_str != "main" and agent_str != self.sub_agent_panel.agent_type:
            return
        panel = self._get_panel_for_agent(agent_str)
        panel.add_checkpoint(message.checkpoint_id, message.description)

    def _handle_task_update_msg(self, message) -> None:
        """Handle TaskUpdateMessage — display task notification in relevant panels."""
        from enum import Enum

        src = message.source_agent
        src_str = src.value if isinstance(src, Enum) else str(src)
        tgt = message.target_agent
        tgt_str = tgt.value if isinstance(tgt, Enum) else str(tgt)

        src_panel = self._get_panel_for_agent(src_str)
        tgt_panel = self._get_panel_for_agent(tgt_str)
        for panel in {src_panel, tgt_panel}:
            panel.handle_task_update(
                task_id=message.task_id,
                action=message.action,
                source=src_str,
                target=tgt_str,
                brief=getattr(message, "brief", "") or "",
            )

    def _get_panel_for_agent(self, agent_type: str) -> AgentPanel:
        if agent_type == "main":
            return self.main_agent_panel
        return self.sub_agent_panel

    # ---- Conversation History ----

    def _on_history_requested(self, agent_type: str) -> None:
        sessions = self._conv_store.get_sessions()
        current_id = self._conv_store.get_current_session_id(agent_type)
        panel = self._get_panel_for_agent(agent_type)
        panel.show_history_dropdown(sessions, current_id)

    def _on_new_conversation_requested(self, agent_type: str) -> None:
        self._conv_store.new_session(agent_type=agent_type)
        panel = self._get_panel_for_agent(agent_type)
        panel._messages_area.clear()
        if hasattr(self.backend, "sync_agent_conversation"):
            self._submit_coroutine(self.backend.sync_agent_conversation(agent_type, []))
        logger.info("New conversation session for {}: {}", agent_type,
                     self._conv_store.get_current_session_id(agent_type))

    def _on_conversation_cleared(self, agent_type: str) -> None:
        self._conv_store.new_session(agent_type=agent_type)
        if hasattr(self.backend, "sync_agent_conversation"):
            self._submit_coroutine(self.backend.sync_agent_conversation(agent_type, []))
        logger.info("/clear for {}: new session {}", agent_type,
                     self._conv_store.get_current_session_id(agent_type))

    def _on_session_selected(self, session_id: str, agent_type: str) -> None:
        if self._conv_store.switch_session(session_id, agent_type):
            panel = self._get_panel_for_agent(agent_type)
            panel._messages_area.clear()
            self._load_conversations_for_agent(agent_type, panel)
            if hasattr(self.backend, "sync_agent_conversation"):
                msgs = self._records_to_backend_messages(agent_type)
                self._submit_coroutine(self.backend.sync_agent_conversation(agent_type, msgs))
            logger.info("Switched {} to session: {}", agent_type, session_id)

    def _on_delete_session(self, session_id: str) -> None:
        self._conv_store.delete_session(session_id)
        self._clear_all_panels()
        self._load_conversations()
        logger.info("Deleted session: {}", session_id)

    def _on_rename_session(self, session_id: str, new_name: str) -> None:
        self._conv_store.rename_session(session_id, new_name)
        logger.info("Renamed session {} to {}", session_id, new_name)

    def _clear_all_panels(self) -> None:
        self.main_agent_panel._messages_area.clear()
        self.sub_agent_panel._messages_area.clear()

    def _subscribe_to_debug_messages(self) -> None:
        self.main_agent_panel.subscribe_to_debug_messages(self.backend.bus)
        self.sub_agent_panel.subscribe_to_debug_messages(self.backend.bus)

    def closeEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "preview"):
            self.preview.save_open_tabs()
        super().closeEvent(event)

    def resizeEvent(self, event):
        """Handle window resize to maintain proportional layout."""
        super().resizeEvent(event)
        if not self._splitter_sizes_initialized:
            self._apply_splitter_sizes(force=True)

    def showEvent(self, event) -> None:
        """Finalize splitter sizing after child widgets compute minimum widths."""
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self._apply_splitter_sizes(force=True))
        QTimer.singleShot(120, lambda: self._apply_splitter_sizes(force=True))

    def changeEvent(self, event) -> None:
        """Handle window state changes (maximize/restore/fullscreen)."""
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            if self._title_bar:
                is_maximized = self.windowState() & Qt.WindowState.WindowMaximized
                is_fullscreen = self.windowState() & Qt.WindowState.WindowFullScreen
                self._title_bar.update_maximize_button(
                    bool(is_maximized or is_fullscreen)
                )

    def _apply_splitter_sizes(self, force: bool = False) -> None:
        if not hasattr(self, "_main_splitter"):
            return
        if self._splitter_sizes_initialized and not force:
            return
        total_width = self._main_splitter.width()
        if total_width <= 0:
            return

        # Use the same proportions as stretch factors: 20%, 40%, 20%, 20%
        # But respect minimum widths of each panel
        total_factor = 20 + 40 + 20 + 20  # 100

        # Calculate minimum widths
        file_tree_min = self.file_tree.minimumWidth()
        preview_min = self.preview.minimumWidth()
        sub_agent_min = self.sub_agent_panel.minimumWidth()
        main_agent_min = self.main_agent_panel.minimumWidth()

        # Calculate sizes based on proportions
        file_tree_size = max(file_tree_min, int(total_width * 20 / total_factor))
        preview_size = max(preview_min, int(total_width * 40 / total_factor))
        sub_agent_size = max(sub_agent_min, int(total_width * 20 / total_factor))
        main_agent_size = max(main_agent_min, int(total_width * 20 / total_factor))

        # If sum exceeds total, scale down proportionally
        total_calculated = file_tree_size + preview_size + sub_agent_size + main_agent_size
        if total_calculated > total_width:
            scale = total_width / total_calculated
            file_tree_size = int(file_tree_size * scale)
            preview_size = int(preview_size * scale)
            sub_agent_size = int(sub_agent_size * scale)
            main_agent_size = int(main_agent_size * scale)

        sizes = [file_tree_size, preview_size, sub_agent_size, main_agent_size]
        self._main_splitter.setSizes(sizes)
        self._splitter_sizes_initialized = True
