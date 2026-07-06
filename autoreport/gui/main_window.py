"""Main application window."""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core.conversations import ConversationStore
from ..interfaces.protocol import BackendAPI
from ..interfaces.types import (
    AgentResponse,
    AgentType,
    Checkpoint,
    Error,
    Message,
    QueueUpdateMessage,
    ReportMessage,
    StatusChange,
    SystemNotice,
    ToolCallMessage,
    ToolResult,
    UserMessage,
)
from ..utils.agent_labels import get_agent_badge, get_agent_title
from ..utils.editor_context import build_editor_context_message, build_editor_context_prompt
from ..utils.logging_config import ui_logger
from .dialogs import information_box, question_box, warning_box
from .scale import dpi_scale
from .theme import get_theme_colors, scrollbar_stylesheet
from .title_bar import TitleBar
from .widgets.agent_panel import AgentPanel
from .widgets.file_tree import FileTreeWidget
from .widgets.preview import PreviewWidget
from .widgets.ui_utils import (
    combo_box_qss,
    compact_tooltip_qss,
    filled_button_qss,
    outlined_button_qss,
)


@dataclass
class _TurnState:
    message_id: str | None = None
    answer_started: bool = False
    phase: str = "idle"
    thinking_text: str = ""


# File-tree panel sizing (logical px, DPI-scaled at use sites).
_FILE_TREE_DEFAULT_WIDTH = 440  # initial width — the tree needs little room
_FILE_TREE_MAX_WIDTH = 1020  # cap so it can't hog the window when resized
_FILE_TREE_MAX_FRACTION = 0.40  # never exceed 40% of the window width


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
        self._agent_queue_cache: dict[str, list[str]] = {}
        self._title_bar: TitleBar | None = None
        self._splitter_sizes_initialized = False
        self._initial_render_prepared = False
        # Cache file context to attach to next user message
        self._pending_file_context: dict[str, dict | None] = {}
        self._pending_rollbacks: dict[str, dict[str, str | None]] = {}
        self._turn_state: dict[str, _TurnState] = {}

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

        self._message_signal.connect(self._dispatch_backend_message)
        self.backend.subscribe_to_messages(self._on_bus_message)
        self._subscribe_to_debug_messages()

        logger.info("Main window initialized for workspace: {}", self.workspace)

    def prepare_initial_render(self) -> None:
        """Synchronously prepare splitter sizes and history before first paint."""
        if self._initial_render_prepared:
            return
        self._initial_render_prepared = True
        self.ensurePolished()
        central = self.centralWidget()
        if central is not None and central.layout() is not None:
            central.layout().activate()
        self._apply_splitter_sizes(force=True)
        areas = [self.agent_panel._messages_area]
        for area in areas:
            area.setUpdatesEnabled(False)
        try:
            self._load_conversations()
            self.layout().activate()
            for area in areas:
                area.viewport().updateGeometry()
        finally:
            for area in areas:
                area.setUpdatesEnabled(True)

    def _apply_window_shadow(self) -> None:
        """Apply window shadow effect for platform-appropriate appearance."""
        if sys.platform == "win32":
            # Windows: Use native DWM shadow
            import ctypes

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
            #titleBarDivider {{
                background-color: {c["border"]};
                border: none;
                margin: 0;
                padding: 0;
            }}
            {
            scrollbar_stylesheet(
                orientation="vertical",
                background_color="transparent",
                thickness=px(8),
                min_handle_extent=px(30),
                radius=px(4),
                colors=c,
            )
        }
            {
            scrollbar_stylesheet(
                orientation="horizontal",
                background_color="transparent",
                thickness=px(8),
                min_handle_extent=px(30),
                radius=px(4),
                colors=c,
            )
        }
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
            {
            combo_box_qss(
                "#subAgentSelector",
                border_color=c["border"],
                background_color=c["surface"],
                foreground_color=c["fg"],
                hover_border_color=c["buttonBlue"],
                selection_bg=c["selectionBlue"],
                selection_fg=c["fg"],
                font_size=12,
                padding="2px 24px 2px 8px",
                radius=c["radius_md"],
                popup_radius=c["radius_md"],
                item_radius=c["radius_sm"],
            )
        }
            #headerAction {{
                background-color: transparent;
                border: none;
                border-radius: {c["radius_sm"]};
                font-size: {px(14)};
                padding: 0;
                color: {c["fg"]};
            }}
            #headerAction:hover {{
                background-color: {c["tree_hover"]};
            }}
            /* ---- Input Container (with working border space) ---- */
            #composerHost {{
                background-color: {c["messages_bg"]};
            }}
            #inputContainer {{
                background-color: {c["messages_bg"]};
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
                background-color: {c["messages_bg"]};
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
                background-color: {c["buttonBlue"]};
                color: {c["primaryBtnFg"]};
                border: 1px solid {c["buttonBlue"]};
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
                background-color: {c["buttonBlue"]};
                border-color: {c["buttonBlue"]};
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
                border: 1px solid {c["gray_white"]};
                border-radius: {px(12)};
            }}
            #userContextChip {{
                background-color: {c["secondaryBtnBg"]};
                border: 1px solid {c["gray_white"]};
                border-radius: {px(8)};
            }}
            #userContextChipIcon {{
                color: {c["muted"]};
                font-size: {px(10)};
                font-weight: {c["fw_semibold"]};
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
                background-color: transparent;
            }}
            #userContextChipText {{
                color: {c["fg"]};
                font-size: {px(12)};
                font-weight: {c["fw_semibold"]};
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
                background-color: transparent;
            }}
            #userEditBubble {{
                background-color: {c["edit_bubble_bg"]};
                border: 1px solid {c["edit_bubble_border"]};
                border-radius: {px(12)};
            }}
            #userMessageText {{
                color: {c["editor_fg"]};
                font-size: {px(13)};
                font-family: "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
            }}
            #messageExpandBtn {{
                background-color: {c["message_expand_bg"]};
                color: {c["message_expand_fg"]};
                border: 1px solid {c["message_expand_border"]};
                border-radius: {px(9)};
                padding: {px(3)} {px(8)};
                font-size: {px(11)};
                font-weight: {c["fw_medium"]};
            }}
            #messageExpandBtn:hover {{
                background-color: {c["message_expand_hover_bg"]};
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
            {
            filled_button_qss(
                "#userSaveBtn",
                bg=c["buttonBlue"],
                fg=c["primaryBtnFg"],
                hover_bg=c["buttonBlue"],
                disabled_bg=c["muted"],
                disabled_fg=c["primaryBtnFg"],
                radius=px(4),
                padding=f"{px(4)} {px(10)}",
                font_size=round(12 * s),
            )
        }
            QPushButton#userSaveBtn:disabled {{
                opacity: 0.5;
            }}
            {
            outlined_button_qss(
                "#userCancelBtn",
                fg=c["fg"],
                border=c["border"],
                hover_bg=c["hover"],
                hover_border=c["muted"],
                radius=px(4),
                padding=f"{px(4)} {px(10)}",
                font_size=round(12 * s),
            )
        }
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
                font-family: "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
            }}
            #agentMessageRow {{
                background-color: transparent;
            }}
            #agentMessageText {{
                color: {c["editor_fg"]};
                font-size: {px(13)};
                line-height: 1.5;
                background-color: transparent;
                font-family: "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
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
                font-family: "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
                font-size: {px(13)};
                line-height: 1.7;
                font-weight: {c["fw_medium"]};
            }}
            #toolCallDetail {{
                color: {c["fg"]};
                font-family: "Segoe UI", "SF Pro", sans-serif;
                font-size: {px(13)};
                padding: 0;
            }}
            #execDetailCard {{
                background-color: {c["detail_card_bg"]};
                border: 1px solid {c["detail_card_border"]};
                border-radius: {px(6)};
            }}
            #execDetailRow {{
                background-color: transparent;
            }}
            #execDetailTag {{
                color: {c["detail_muted"]};
                font-size: {px(10)};
                font-weight: {c["fw_semibold"]};
                min-width: {px(20)};
            }}
            #execDetailValueHost {{
                background-color: transparent;
                border: none;
                border-radius: 0;
            }}
            #execDetailText {{
                color: {c["detail_fg"]};
                font-family: "Cascadia Code", "SF Mono", "Consolas", monospace;
                font-size: {px(11)};
                line-height: 1.45;
            }}
            #execDetailDivider {{
                background-color: {c["detail_card_border"]};
                border: none;
            }}
            #manageDetailCard {{
                background-color: {c["detail_card_bg"]};
                border: 1px solid {c["detail_card_border"]};
                border-radius: {px(8)};
            }}
            #manageDetailTitle {{
                color: {c["detail_muted"]};
                font-size: {px(10)};
                font-weight: {c["fw_semibold"]};
            }}
            #manageDetailItem {{
                color: {c["detail_fg"]};
                font-size: {px(11)};
                line-height: 1.6;
                font-family: "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
            }}
            #manageDetailDone {{
                color: {c["detail_muted"]};
                font-size: {px(11)};
                line-height: 1.6;
                font-family: "Segoe UI", "Microsoft YaHei", "Roboto", "Helvetica Neue", sans-serif;
                text-decoration: line-through;
            }}
            #manageDetailEmpty {{
                color: {c["detail_muted"]};
                font-size: {px(11)};
            }}
            #manageDetailDivider {{
                background-color: {c["detail_card_border"]};
                border: none;
            }}
            #execCopyBtn {{
                background-color: transparent;
                border: none;
                border-radius: {px(4)};
                color: {c["detail_muted"]};
                padding: 0;
            }}
            #execCopyBtn:hover {{
                background-color: {c["hover"]};
                color: {c["detail_hover_fg"]};
            }}

            /* ---- Status Indicator ---- */
            #statusSpinner {{
                color: {c["buttonBlue"]};
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
        open_file_act.setEnabled(False)
        open_file_act.setToolTip("请通过左侧文件树添加文件（拖放或目录内右键新建）")
        open_file_act.triggered.connect(self._on_open_file)

        open_folder_act = file_menu.addAction("打开文件夹...")
        open_folder_act.triggered.connect(self._on_open_folder)

        file_menu.addSeparator()

        save_act = file_menu.addAction("保存")
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self._on_save_file)

        file_menu.addSeparator()

        new_window_act = file_menu.addAction("新建窗口")
        new_window_act.setEnabled(False)
        new_window_act.setToolTip("暂不支持多窗口；请新建/打开另一个项目")
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
        if not hasattr(self, "preview"):
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
        """Handle open file action.

        Currently unsupported — files are added via the file tree (drag-drop or
        right-click within a directory). The menu entry is disabled; this
        handler only guards against any future trigger path.
        """
        information_box(
            self,
            "暂不支持",
            "请通过左侧文件树添加文件：将文件拖入对应目录，或在目录上右键新建。",
        )

    def _on_open_folder(self) -> None:
        """Handle open folder action — switch workspace to the selected folder.

        The workspace is bound at startup (LoopManager, async loop, conversation
        stores all key off it), so switching means relaunching the app into the
        new project via ``--project``. The new process is started detached and
        this window is closed.
        """
        from PyQt6.QtCore import QProcess
        from PyQt6.QtWidgets import QFileDialog

        from ..core.recent_projects import RecentProjects
        from .project_dialog import create_project_structure, is_valid_project

        folder_path = QFileDialog.getExistingDirectory(self, "打开文件夹（切换工作区）")
        if not folder_path:
            return

        folder = Path(folder_path).expanduser().resolve()

        # Validate it looks like an AutoReport project; offer to scaffold if not.
        if not is_valid_project(folder):
            reply = question_box(
                self,
                "不是有效的项目",
                f"'{folder.name}' 不是 AutoReport 项目。是否在该目录创建项目结构并打开？",
                default=QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            create_project_structure(folder)

        RecentProjects().add(folder)

        # Relaunch detached into the new workspace so the new window survives
        # after this process quits.
        QProcess.startDetached(
            sys.executable,
            ["-m", "autoreport", "--project", str(folder)],
        )
        logger.info("Switching workspace to {} (relaunching)", folder)
        QApplication.closeAllWindows()

    def _on_save_file(self) -> None:
        """Save the active file in the preview panel."""
        if not self.preview.save_current_file():
            logger.debug("Save skipped: no editable active file")

    def _on_new_window(self) -> None:
        """Handle new window action.

        Currently unsupported — multi-window mode is not implemented. The menu
        entry is disabled; this handler only guards against future triggers.
        """
        information_box(self, "暂不支持", "暂不支持多窗口，请新建或打开另一个项目。")

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
            self._titlebar_divider = QFrame(self)
            self._titlebar_divider.setObjectName("titleBarDivider")
            self._titlebar_divider.setFixedHeight(1)
            main_layout.addWidget(self._titlebar_divider)

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
        self.preview.file_changed.connect(self._on_preview_file_changed)
        main_splitter.addWidget(self.preview)

        # Right: Single agent panel with agent selector
        self.agent_panel = AgentPanel("sub", get_agent_title("sub"), self.workspace)
        main_splitter.addWidget(self.agent_panel)

        for index in range(main_splitter.count()):
            main_splitter.setCollapsible(index, False)

        # Cap the file-tree width so it stays a narrow rail and never hogs the
        # window — extra space should flow to the preview/agent panels.
        self.file_tree.setMaximumWidth(_FILE_TREE_MAX_WIDTH)

        # Set stretch factors: file_tree is non-stretching (it has a max width),
        # extra space is split between preview and agent_panel.
        main_splitter.setStretchFactor(0, 0)  # file_tree (fixed-ish rail)
        main_splitter.setStretchFactor(1, 56)  # preview
        main_splitter.setStretchFactor(2, 44)  # agent_panel

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
        self.agent_panel.message_sent.connect(self._on_agent_message)
        self.agent_panel.file_context_attached.connect(self._on_agent_file_context)
        self.agent_panel.history_requested.connect(
            lambda: self._on_history_requested(self.current_agent_type)
        )
        self.agent_panel.new_conversation_requested.connect(
            lambda: self._on_new_conversation_requested(self.current_agent_type)
        )
        self.agent_panel.session_selected_from_dropdown.connect(
            lambda sid: self._on_session_selected(sid, self.current_agent_type)
        )
        self.agent_panel.delete_session_requested.connect(self._on_delete_session)
        self.agent_panel.rename_session_requested.connect(self._on_rename_session)
        self.agent_panel.interrupt_requested.connect(
            lambda: self._on_interrupt(self.current_agent_type)
        )
        self.agent_panel.agent_type_changed.connect(self._on_agent_type_changed)
        self.agent_panel.rollback_requested.connect(
            lambda checkpoint_id, row: self._on_rollback_requested(
                self.current_agent_type, checkpoint_id, row
            )
        )
        self.agent_panel.thinking_finished.connect(
            lambda summary, detail, expandable: self._on_thinking_finished(
                self.current_agent_type, summary, detail, expandable
            )
        )

        self.preview.selection_changed.connect(self._on_preview_selection_changed)
        self.preview.restore_open_tabs()
        self.file_tree.restore_state()
        self.agent_panel.set_agent_type("main")
        self.agent_panel.set_debug_mode("main" in self._debug_agents)
        self.agent_panel.conversation_cleared.connect(
            lambda: self._on_conversation_cleared(self.current_agent_type)
        )

    def _on_directory_selected(self, directory: str) -> None:
        ui_logger.debug("MainWindow: directory selected {}", directory)
        # Directory navigation is decoupled from sub-agent switching.
        # Keep current contexts when the event is triggered by file click.
        if not getattr(self, "_file_just_selected", False):
            self.agent_panel.clear_file_context()
        self._file_just_selected = False

    def _on_preview_selection_changed(
        self, file_path: str, selected_text: str, start_line: int, end_line: int
    ) -> None:
        if not selected_text:
            # Empty selection should not override selection context here.
            # File-path attachment is synchronized via _on_preview_file_changed.
            return
        self.agent_panel.set_preview_context(file_path, selected_text, start_line, end_line)

    def _on_preview_file_changed(self, file_path: Path) -> None:
        if not file_path:
            self.agent_panel.clear_file_context()
            return
        self.file_tree.select_file(file_path)
        rel_path = self._relative_path(file_path)
        self.agent_panel.set_opened_file(rel_path)

    def _on_file_selected(self, file_path: Path) -> None:
        ui_logger.debug("MainWindow: file selected {}", file_path.name)
        self._file_just_selected = True
        self.preview.load_file(file_path)
        rel_path = self._relative_path(file_path)
        self.agent_panel.set_opened_file(rel_path)
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
            return

        # QLabel (used by message markdown/text rows) doesn't expose copy(),
        # but still supports selectedText() when text is selectable.
        if method_name == "copy":
            selected_getter = getattr(widget, "selectedText", None)
            if callable(selected_getter):
                selected = str(selected_getter() or "")
                if selected:
                    clipboard = QApplication.clipboard()
                    if clipboard:
                        clipboard.setText(selected)

    def _load_conversations(self) -> None:
        self._load_conversations_for_agent(self.current_agent_type, self.agent_panel)
        if hasattr(self.backend, "sync_agent_conversation"):
            self._submit_coroutine(
                self.backend.sync_agent_conversation(
                    self.current_agent_type,
                    self._records_to_backend_messages(self.current_agent_type),
                    session_id=self._conv_store.get_current_session_id(self.current_agent_type),
                )
            )

    def _load_conversations_for_agent(self, agent_type: str, panel: AgentPanel) -> None:
        panel._messages_area.clear()
        records = self._conv_store.load_messages(agent_type)
        if not records:
            panel._update_width()
            return
        for rec in records:
            role = rec.get("role", "")
            content = rec.get("content", "")
            if role == "user":
                context = rec.get("editor_context")
                if isinstance(context, dict):
                    content = build_editor_context_message(context, str(content))
                panel.add_message(
                    "user",
                    content,
                    display_mode=str(rec.get("display_mode") or "bubble"),
                    bubble_title=rec.get("bubble_title"),
                    bubble_align=str(rec.get("bubble_align") or "right"),
                    bubble_on_timeline=bool(rec.get("bubble_on_timeline", False)),
                    bubble_collapsible=bool(rec.get("bubble_collapsible", True)),
                    allow_edit=str(rec.get("source", "user")) == "user",
                    message_id=rec.get("message_id"),
                )
            elif role == "agent":
                if rec.get("display_mode") == "bubble":
                    panel.add_message(
                        "agent",
                        content,
                        display_mode="bubble",
                        bubble_title=rec.get("bubble_title"),
                        bubble_align=str(rec.get("bubble_align") or "left"),
                        bubble_on_timeline=bool(rec.get("bubble_on_timeline", True)),
                        bubble_collapsible=bool(rec.get("bubble_collapsible", True)),
                        muted_italic=bool(rec.get("muted_italic", False)),
                        message_id=rec.get("message_id"),
                    )
                else:
                    panel.add_message("agent", content, message_id=rec.get("message_id"))
            elif role == "thinking":
                panel.add_message(
                    "agent",
                    content,
                    display_mode="thought",
                    bubble_title=rec.get("bubble_title") or "Thought",
                    bubble_collapsible=bool(rec.get("bubble_collapsible", True)),
                )
            elif role == "tool_call":
                panel.add_tool_call(
                    content,
                    rec.get("arguments", {}),
                    summary=rec.get("summary"),
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
        panel._update_width()
        logger.info("Loaded {} messages for agent {}", len(records), agent_type)

    def _on_thinking_finished(
        self, agent_type: str, summary: str, detail: str, expandable: bool
    ) -> None:
        if not (detail or "").strip():
            return
        self._conv_store.append_message(
            agent_type,
            "thinking",
            detail or "",
            extra={
                "display_mode": "thought",
                "bubble_title": summary,
                "bubble_collapsible": expandable,
            },
        )

    def _records_to_backend_messages(self, agent_type: str) -> list[dict[str, str]]:
        """Convert stored records to backend chat history messages."""
        records = self._conv_store.load_messages(agent_type)
        converted: list[dict[str, str]] = []
        for rec in records:
            role = str(rec.get("role", ""))
            content = str(rec.get("content", ""))
            if role == "user":
                context = rec.get("editor_context")
                if isinstance(context, dict):
                    content = build_editor_context_prompt(context, content)
                converted.append({"role": "user", "content": content})
            elif role == "agent":
                converted.append({"role": "assistant", "content": content})
            elif role == "tool_result":
                result = rec.get("result")
                err = rec.get("error")
                payload = str(result) if result is not None else str(err or "")
                # Anthropic doesn't support role="tool", use role="user" with is_tool_result flag
                converted.append({"role": "user", "content": payload, "is_tool_result": True})
        return converted

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._async_loop = loop

    def _submit_coroutine(self, coro):
        if self._async_loop is None:
            logger.warning("No async loop set, cannot dispatch coroutine")
            close = getattr(coro, "close", None)
            if callable(close):
                close()
            return
        return asyncio.run_coroutine_threadsafe(coro, self._async_loop)

    @property
    def current_agent_type(self) -> str:
        return self.agent_panel.agent_type

    def _is_visible_agent(self, agent_type: str) -> bool:
        return agent_type == self.current_agent_type

    def _show_current_agent_conversation(self) -> None:
        self.agent_panel.finish_thinking()
        self.agent_panel._pending_tool_groups.clear()
        self.agent_panel._current_tool_group = None
        self.agent_panel._messages_area.clear()
        self._load_conversations_for_agent(self.current_agent_type, self.agent_panel)
        self.agent_panel.set_queue_preview(self._agent_queue_cache.get(self.current_agent_type, []))
        cached = self._agent_status_cache.get(self.current_agent_type)
        if cached:
            status, extra = cached
            self.agent_panel.set_status(status, extra)
        else:
            self.agent_panel.set_status("idle", {})
        self.agent_panel.set_debug_mode(self.current_agent_type in self._debug_agents)

    def _on_agent_message(self, content: str) -> None:
        import uuid

        agent_type = self.current_agent_type
        full_content = content
        file_context = self._pending_file_context.get(agent_type)
        if file_context:
            full_content = build_editor_context_prompt(file_context, content)
            self._pending_file_context[agent_type] = None

        # A client-generated message_id lets the pre-message checkpoint and the
        # user bubble find each other precisely (see attach_checkpoint_*).
        message_id = uuid.uuid4().hex
        self._submit_coroutine(
            self.backend.send_user_message(full_content, agent_type, message_id=message_id)
        )

    def _on_agent_file_context(self, file_context: dict) -> None:
        self._pending_file_context[self.current_agent_type] = file_context

    def _on_agent_type_changed(self, agent_type: str) -> None:
        self.agent_panel.set_agent_type(agent_type)
        self._show_current_agent_conversation()
        if hasattr(self.backend, "sync_agent_conversation"):
            self._submit_coroutine(
                self.backend.sync_agent_conversation(
                    agent_type,
                    self._records_to_backend_messages(agent_type),
                    session_id=self._conv_store.get_current_session_id(agent_type),
                )
            )

    def _on_interrupt(self, agent_type: str) -> None:
        """Handle interrupt request from GUI."""
        self._submit_coroutine(self.backend.interrupt_current_message(agent_type))

    def _on_rollback_requested(self, agent_type: str, checkpoint_id: str, row) -> None:
        reply = question_box(
            self,
            "Rollback",
            "Rollback files and conversation to before this message?",
            default=QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        panel = self._get_panel_for_agent(agent_type)
        self._pending_rollbacks[agent_type] = {
            "message_id": getattr(row, "_message_id", None),
            "content": getattr(row, "_content", None),
            "role": getattr(row, "_role", None),
        }
        panel._messages_area.retract_from_row(row)
        future = self._submit_coroutine(
            self.backend.rollback_to_checkpoint(agent_type, checkpoint_id)
        )
        if future is not None:
            future.add_done_callback(
                lambda done: self._rollback_finished_signal.emit(agent_type, done)
            )

    def _on_rollback_finished(self, agent_type: str, future) -> None:
        rollback_target = self._pending_rollbacks.pop(agent_type, None)
        try:
            future.result()
        except Exception as exc:
            logger.warning("Rollback failed for {}: {}", agent_type, exc)
            warning_box(self, "Rollback Failed", str(exc))
            if self._is_visible_agent(agent_type):
                self._show_current_agent_conversation()
            return

        if rollback_target:
            self._conv_store.truncate_from_message(agent_type, **rollback_target)
        if self._is_visible_agent(agent_type):
            self._show_current_agent_conversation()
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
            ReportMessage,
            StatusChange,
            SystemNotice,
            TaskUpdateMessage,
            ToolCallMessage,
            ToolResult,
            UserMessage,
        )

        if isinstance(message, AgentResponse):
            self._handle_agent_response(message)
        elif isinstance(message, UserMessage):
            self._handle_user_message(message)
        elif isinstance(message, ToolCallMessage):
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
        elif isinstance(message, ReportMessage):
            self._handle_report_message(message)
        elif isinstance(message, SystemNotice):
            self._handle_system_notice(message)
        elif isinstance(message, QueueUpdateMessage):
            self._handle_queue_update(message)

    def _handle_agent_response(self, message: AgentResponse) -> None:
        agent_str = str(message.agent_type)
        if not self._is_visible_agent(agent_str):
            if not message.streaming and message.content:
                self._conv_store.append_message(
                    agent_str,
                    "agent",
                    message.content,
                    extra={"message_id": message.message_id},
                )
            return
        panel = self._get_panel_for_agent(agent_str)
        state = self._state_for_agent(agent_str)

        def _latest_incomplete_agent_row():
            rows = panel._messages_area.get_message_rows()
            for row in reversed(rows):
                if getattr(row, "_role", "") != "agent":
                    continue
                if getattr(row, "_display_mode", "") != "agent_markdown":
                    continue
                if not getattr(row, "_content", ""):
                    continue
                if getattr(row, "_complete", True):
                    continue
                return row
            return None

        msg_id = str(getattr(message, "message_id", "") or "")
        if msg_id and state.message_id != msg_id:
            state.message_id = msg_id
            state.answer_started = False
            state.phase = "idle"
            state.thinking_text = ""

        if getattr(message, "thinking", None):
            thinking = message.thinking or ""
            merged_thinking = panel._merge_thinking_chunk(state.thinking_text, thinking)
            if state.thinking_text and merged_thinking == state.thinking_text:
                return
            if state.answer_started and state.thinking_text and merged_thinking.startswith(state.thinking_text):
                return
            panel.append_thinking(thinking)
            state.thinking_text = merged_thinking
            state.phase = "thinking"
            return

        if not message.streaming and not message.content:
            panel.finish_thinking()
            row = _latest_incomplete_agent_row()
            if row is not None:
                row.mark_complete()
            state.answer_started = False
            state.phase = "idle"
            return

        if not message.streaming and message.content:
            panel.finish_thinking()
            row = _latest_incomplete_agent_row()
            if row is not None:
                row.mark_complete()
                self._conv_store.append_message(
                    agent_str,
                    "agent",
                    row._content,
                    extra={"message_id": msg_id or None},
                )
                state.answer_started = False
                state.phase = "idle"
                return

        panel.finish_thinking()
        state.answer_started = True
        state.phase = "answer"
        panel.add_message(
            "agent", message.content, streaming=message.streaming, message_id=msg_id or None
        )
        if not message.streaming:
            self._conv_store.append_message(
                agent_str,
                "agent",
                message.content,
                extra={"message_id": msg_id or None},
            )
            rows = panel._messages_area.get_message_rows()
            if rows and rows[-1]._role == "agent":
                rows[-1].mark_complete()
            state.answer_started = False
            state.phase = "idle"

    def _handle_user_message(self, message: UserMessage) -> None:
        agent_str = str(message.agent_type)
        if not self._is_visible_agent(agent_str):
            self._conv_store.append_message(
                agent_str,
                "user",
                message.content,
                extra={
                    "source": message.source,
                    "message_id": message.message_id,
                    "summary": getattr(message, "summary", "") or "",
                },
            )
            return
        source_key = str(message.source or "user")
        is_agent_message = source_key not in {"user", "system"}
        bubble_title = None
        bubble_align = "right"
        bubble_on_timeline = False
        allow_edit = source_key == "user"
        if is_agent_message:
            sender = (
                "Main" if source_key == "main_agent" else self._get_agent_display_name(source_key)
            )
            summary = str(getattr(message, "summary", "") or "").strip()
            bubble_title = summary or self._build_inter_agent_title(
                f"Message From {sender}",
                message.content,
            )

        target_panel = self._get_panel_for_agent(agent_str)
        target_panel.add_message(
            "user",
            message.content,
            source=message.source,
            coordination=False,
            display_mode="bubble",
            bubble_title=bubble_title,
            bubble_align=bubble_align,
            bubble_on_timeline=bubble_on_timeline,
            bubble_collapsible=True,
            allow_edit=allow_edit,
            message_id=message.message_id,
        )

        self._conv_store.append_message(
            agent_str,
            "user",
            message.content,
            extra={
                "source": message.source,
                "summary": getattr(message, "summary", "") or "",
                "display_mode": "bubble",
                "bubble_title": bubble_title,
                "bubble_align": bubble_align,
                "bubble_on_timeline": bubble_on_timeline,
                "bubble_collapsible": True,
                "message_id": message.message_id,
            },
        )

    def _get_agent_display_name(self, agent_type: str) -> str:
        return get_agent_badge(agent_type)

    def _route_summary(self, source: str, target: str) -> str:
        return f"{get_agent_badge(source)} to {get_agent_badge(target)}"

    def _respond_summary(self, agent_str: str, content: str | None) -> str:
        route = MainWindow._route_summary(self, agent_str, "main")
        text = str(content or "").strip()
        if not text:
            return route
        first_line = text.splitlines()[0].strip()
        if len(first_line) > 96:
            first_line = first_line[:93].rstrip() + "..."
        return f"{route}: {first_line}" if first_line else route

    def _handle_tool_call(self, message: ToolCallMessage) -> None:
        agent_str = str(message.agent_type)
        state = self._state_for_agent(agent_str)
        if agent_str == "main" and message.tool_name == "send_to_agent":
            if self._is_visible_agent(agent_str):
                self._get_panel_for_agent(agent_str).finish_thinking()
            state.phase = "tool"
            return
        if not self._is_visible_agent(agent_str):
            self._conv_store.append_tool_call(agent_str, message.tool_name, message.arguments)
            return
        panel = self._get_panel_for_agent(agent_str)
        panel.finish_thinking()
        state.phase = "tool"
        summary = None
        detail = None
        expandable = True
        if agent_str == "main" and message.tool_name == "send_to_agent":
            target = str(message.arguments.get("agent_type") or "sub")
            summary = MainWindow._route_summary(self, "main", target)
            expandable = False
        elif message.tool_name == "respond":
            detail = str(message.arguments.get("content") or "").strip() or None
            summary = (
                str(message.arguments.get("summary") or "").strip()
                or MainWindow._respond_summary(self, agent_str, detail)
            )
            expandable = bool(detail)
        elif message.tool_name == "manage_tasks":
            summary = "<b>Task</b>"
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
            },
        )

    def _handle_tool_result(self, message: ToolResult) -> None:
        agent_str = str(message.agent_type)
        state = self._state_for_agent(agent_str)
        if not self._is_visible_agent(agent_str):
            result_str = str(message.result) if message.result else None
            summary = None
            detail = None
            expandable = None
            if agent_str == "main" and message.tool_name == "send_to_agent":
                summary, detail = self._format_send_to_agent_bubble(message.result, message.error)
                expandable = bool(detail)
                result_str = detail or summary
                self._conv_store.append_tool_call(
                    agent_str,
                    message.tool_name,
                    self._send_to_agent_result_arguments(message.result),
                    extra={"summary": summary},
                )
            elif message.tool_name == "respond":
                summary, detail = self._format_respond_bubble(
                    message.result, message.error, agent_str=agent_str
                )
                expandable = bool(detail)
                result_str = detail or summary
            elif message.tool_name == "manage_tasks":
                message.result = self._augment_manage_tasks_result(agent_str, message.result)
                summary, detail, expandable = self._format_manage_tasks_result(
                    message.result, message.error
                )
                if summary:
                    result_str = summary
            self._conv_store.append_tool_result(
                agent_str,
                message.tool_name,
                result_str,
                message.error,
                extra={
                    "summary": summary,
                    "detail": detail,
                    "expandable": expandable,
                }
                if summary or detail or expandable is not None
                else None,
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
            summary, detail = self._format_send_to_agent_bubble(message.result, message.error)
            expandable = bool(detail)
            result_str = detail or summary
        elif message.tool_name == "respond":
            summary, detail = self._format_respond_bubble(
                message.result, message.error, agent_str=agent_str
            )
            expandable = bool(detail)
            result_str = detail or summary
        elif message.tool_name == "manage_tasks":
            message.result = self._augment_manage_tasks_result(agent_str, message.result)
            summary, _, _ = self._format_manage_tasks_result(message.result, message.error)
            if summary:
                result_str = summary

        if agent_str == "main" and message.tool_name == "send_to_agent":
            panel.add_tool_call(
                message.tool_name,
                self._send_to_agent_result_arguments(message.result),
                summary=summary,
                detail=detail,
                expandable=bool(expandable),
            )
            self._conv_store.append_tool_call(
                agent_str,
                message.tool_name,
                self._send_to_agent_result_arguments(message.result),
                extra={"summary": summary},
            )

        panel.add_tool_result(
            message.tool_name,
            message.result,
            safe_error,
            summary=summary,
            detail=detail,
            expandable=expandable,
        )
        state.phase = "tool"
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

    def _send_to_agent_result_arguments(self, result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            target = str(result.get("agent_type") or "sub").strip() or "sub"
            task_id = str(result.get("task_id") or "").strip()
            args: dict[str, Any] = {"agent_type": target}
            if task_id:
                args["task_id"] = task_id
            return args
        return {}

    def _augment_manage_tasks_result(self, agent_str: str, result: Any) -> Any:
        """Ensure manage_tasks result always carries todolist/waitlist for UI rendering."""
        if not isinstance(result, dict):
            return result
        if isinstance(result.get("todolist"), list) and isinstance(result.get("waitlist"), list):
            return result
        loop_manager = getattr(self.backend, "loop_manager", None)
        task_board = (
            getattr(loop_manager, "_task_board", None) if loop_manager is not None else None
        )
        if task_board is None:
            return result
        try:
            agent_type = AgentType(agent_str)
        except ValueError:
            return result
        session_id = self._conv_store.get_current_session_id(agent_str)
        todolist = task_board.get_todolist(agent_type, session_id=session_id)
        waitlist = task_board.get_waitlist(agent_type, session_id=session_id)
        augmented = dict(result)
        augmented["todolist"] = [
            {
                "task_id": t.task_id,
                "brief": t.brief,
                "status": t.status.value,
                "source_agent": t.source_agent.value,
            }
            for t in todolist
        ]
        augmented["waitlist"] = [
            {
                "task_id": t.task_id,
                "brief": t.brief,
                "status": t.status.value,
                "target_agent": t.target_agent.value,
            }
            for t in waitlist
        ]
        return augmented

    def _format_send_to_agent_bubble(self, result, error: str | None) -> tuple[str, str | None]:
        target = "sub"
        if isinstance(result, dict):
            target = str(result.get("agent_type") or target)
        route = MainWindow._route_summary(self, "main", target)
        if error:
            return (route, error)

        if not isinstance(result, dict):
            text = str(result).strip() if result is not None else ""
            return (route, text or None)

        status = str(result.get("status", "success"))
        response = str(result.get("response", "") or "").strip()
        request_summary = str(result.get("summary") or result.get("request_summary") or "").strip()
        response_summary = str(result.get("response_summary") or "").strip()

        if status == "delegated":
            detail = str(result.get("message", "") or "").strip() or None
            return (request_summary or route, detail)

        if status == "timeout":
            detail = str(result.get("error", "") or "").strip() or None
            return (request_summary or route, detail)

        if status == "error":
            detail = str(result.get("error", "") or "").strip() or None
            return (request_summary or route, detail)

        if not response:
            return (response_summary or request_summary or route, None)

        return (response_summary or request_summary or route, response)

    def _format_respond_bubble(
        self, result, error: str | None, *, agent_str: str = "sub"
    ) -> tuple[str, str | None]:
        if error:
            return (MainWindow._respond_summary(self, agent_str, error), error)
        if not isinstance(result, dict):
            text = str(result).strip() if result is not None else ""
            return (MainWindow._respond_summary(self, agent_str, text), text or None)
        detail = str(result.get("content") or "").strip()
        if not detail:
            detail = str(result.get("message") or "").strip()
        summary = str(result.get("summary") or "").strip()
        return (summary or MainWindow._respond_summary(self, agent_str, detail), detail or None)

    def _format_manage_tasks_result(
        self, result, error: str | None
    ) -> tuple[str | None, str | None, bool | None]:
        if error or not isinstance(result, dict):
            return (None, None, None)

        if str(result.get("status", "")) != "ok":
            return (None, None, None)

        def _rows(items: list[dict], title: str) -> list[str]:
            if not items:
                return []
            lines = [title]
            shown = 0
            for item in items:
                if shown >= 10:
                    break
                status = str(item.get("status", "pending")).lower()
                brief = str(item.get("brief", "")).strip() or "task"
                marker = {
                    "pending": "☐",
                    "in_progress": "●",
                    "completed": "☑",
                    "failed": "⚠",
                    "cancelled": "✗",
                }.get(status, "☐")
                if title == "Wait" and status == "pending":
                    marker = "○"
                lines.append(f"{marker} {brief}")
                shown += 1
            return lines

        todolist = result.get("todolist")
        waitlist = result.get("waitlist")
        if isinstance(todolist, list) and isinstance(waitlist, list):
            sections = [_rows(todolist, "Todo"), _rows(waitlist, "Wait")]
            lines = ["<b>Task</b>"]
            for section in sections:
                if not section:
                    continue
                if len(lines) > 1:
                    lines.append("")
                lines.extend(section)
            summary = "\n".join(lines)
            return (summary, None, False)

        ui_summary = str(result.get("_ui_summary", "") or "").strip()
        ui_detail = str(result.get("_ui_detail", "") or "").strip()
        if not ui_summary and not ui_detail:
            return (None, None, None)
        return (ui_summary or "Task completed", ui_detail or None, bool(ui_detail))

    def _build_inter_agent_title(self, prefix: str, content: str) -> str:
        response = str(content or "").strip()
        if not response:
            return prefix

        first_line = response.splitlines()[0].strip()
        return f"{prefix}: {first_line}" if first_line else prefix

    def _handle_status_change(self, message: StatusChange) -> None:
        agent_str = str(message.agent_type)
        self._agent_status_cache[agent_str] = (str(message.status), dict(message.extra or {}))
        if self._is_visible_agent(agent_str):
            self.agent_panel.set_status(message.status, message.extra)

    def _handle_error(self, message: Error) -> None:
        if self._is_visible_agent("main"):
            self.agent_panel.add_error(message.source, message.message)
        self._conv_store.append_message(
            "main", "error", message.message, extra={"source": message.source}
        )

    def _handle_report_message(self, message: ReportMessage) -> None:
        """Handle ReportMessage and show sub-agent reports in main panel."""
        from enum import Enum

        agent_str = (
            message.agent_type.value
            if isinstance(message.agent_type, Enum)
            else str(message.agent_type)
        )
        summary = str(getattr(message, "summary", "") or "").strip()
        bubble_title = summary or MainWindow._respond_summary(self, agent_str, message.content)
        if self._is_visible_agent("main"):
            self.agent_panel.add_message(
                "agent",
                message.content,
                source=agent_str,
                display_mode="bubble",
                bubble_title=bubble_title,
                bubble_align="left",
                bubble_on_timeline=False,
                bubble_collapsible=True,
            )
        self._conv_store.append_message(
            "main",
            "agent",
            message.content,
            extra={
                "source": agent_str,
                "summary": summary,
                "display_mode": "bubble",
                "bubble_title": bubble_title,
                "bubble_align": "left",
                "bubble_on_timeline": False,
                "bubble_collapsible": True,
                "report_type": message.report_type,
                "task_id": message.task_id,
            },
        )

    def _handle_system_notice(self, message: SystemNotice) -> None:
        """Handle SystemNotice and render in target agent panel."""
        from enum import Enum

        agent_str = (
            message.agent_type.value
            if isinstance(message.agent_type, Enum)
            else str(message.agent_type)
        )
        bubble_title = None
        is_interrupt = getattr(message, "kind", "notice") == "interrupt"
        if self._is_visible_agent(agent_str):
            panel = self._get_panel_for_agent(agent_str)
            panel.add_message(
                "agent",
                message.content,
                source="system",
                display_mode="bubble",
                bubble_title=bubble_title,
                bubble_align="left",
                bubble_on_timeline=False,
                bubble_collapsible=True,
                muted_italic=is_interrupt,
            )
        self._conv_store.append_message(
            agent_str,
            "agent",
            message.content,
            extra={
                "source": "system",
                "display_mode": "bubble",
                "bubble_title": bubble_title,
                "bubble_align": "left",
                "bubble_on_timeline": False,
                "bubble_collapsible": True,
                "system_notice": True,
                "muted_italic": is_interrupt,
            },
        )

    def _handle_queue_update(self, message: QueueUpdateMessage) -> None:
        agent_str = str(message.agent_type)
        self._agent_queue_cache[agent_str] = list(message.queued_messages)
        if self._is_visible_agent(agent_str):
            self.agent_panel.set_queue_preview(message.queued_messages)

    def _handle_checkpoint(self, message: Checkpoint) -> None:
        agent_str = str(message.agent_type) if hasattr(message, "agent_type") else "main"
        if not self._is_visible_agent(agent_str):
            return
        self.agent_panel.add_checkpoint(
            message.checkpoint_id, message.description, message.message_id
        )

    def _handle_task_update_msg(self, message) -> None:
        """Handle TaskUpdateMessage — display task notification in relevant panels."""
        from enum import Enum

        src = message.source_agent
        src_str = src.value if isinstance(src, Enum) else str(src)
        tgt = message.target_agent
        tgt_str = tgt.value if isinstance(tgt, Enum) else str(tgt)

        if self.current_agent_type == "main" or self.current_agent_type in {src_str, tgt_str}:
            self._render_task_block_for_current_agent()

    def _render_task_block_for_current_agent(self) -> None:
        loop_manager = getattr(self.backend, "loop_manager", None)
        task_board = (
            getattr(loop_manager, "_task_board", None) if loop_manager is not None else None
        )
        if task_board is None:
            return
        try:
            agent_type = AgentType(self.current_agent_type)
        except ValueError:
            return
        session_id = self._conv_store.get_current_session_id(self.current_agent_type)
        todolist = task_board.get_todolist(agent_type, session_id=session_id)
        waitlist = task_board.get_waitlist(agent_type, session_id=session_id)
        todo_rows = [{"brief": t.brief, "status": t.status.value} for t in todolist]
        wait_rows = [{"brief": t.brief, "status": t.status.value} for t in waitlist]
        self.agent_panel.add_task_block(todo_rows, wait_rows)

    def _get_panel_for_agent(self, agent_type: str) -> AgentPanel:
        return self.agent_panel

    def _state_for_agent(self, agent_type: str) -> _TurnState:
        state = self._turn_state.get(agent_type)
        if state is None:
            state = _TurnState()
            self._turn_state[agent_type] = state
        return state

    # ---- Conversation History ----

    def _on_history_requested(self, agent_type: str) -> None:
        sessions = self._conv_store.get_sessions(agent_type)
        current_id = self._conv_store.get_current_session_id(agent_type)
        panel = self._get_panel_for_agent(agent_type)
        panel.show_history_dropdown(sessions, current_id)

    def _on_new_conversation_requested(self, agent_type: str) -> None:
        self._conv_store.new_session(agent_type=agent_type)
        panel = self._get_panel_for_agent(agent_type)
        panel._messages_area.clear()
        if hasattr(self.backend, "sync_agent_conversation"):
            self._submit_coroutine(
                self.backend.sync_agent_conversation(
                    agent_type,
                    [],
                    session_id=self._conv_store.get_current_session_id(agent_type),
                )
            )
        logger.info(
            "New conversation session for {}: {}",
            agent_type,
            self._conv_store.get_current_session_id(agent_type),
        )

    def _on_conversation_cleared(self, agent_type: str) -> None:
        self._conv_store.new_session(agent_type=agent_type)
        if hasattr(self.backend, "sync_agent_conversation"):
            self._submit_coroutine(
                self.backend.sync_agent_conversation(
                    agent_type,
                    [],
                    session_id=self._conv_store.get_current_session_id(agent_type),
                )
            )
        logger.info(
            "/clear for {}: new session {}",
            agent_type,
            self._conv_store.get_current_session_id(agent_type),
        )

    def _on_session_selected(self, session_id: str, agent_type: str) -> None:
        if self._conv_store.switch_session(session_id, agent_type):
            panel = self._get_panel_for_agent(agent_type)
            panel._messages_area.clear()
            self._load_conversations_for_agent(agent_type, panel)
            if hasattr(self.backend, "sync_agent_conversation"):
                msgs = self._records_to_backend_messages(agent_type)
                self._submit_coroutine(
                    self.backend.sync_agent_conversation(
                        agent_type,
                        msgs,
                        session_id=self._conv_store.get_current_session_id(agent_type),
                    )
                )
            logger.info("Switched {} to session: {}", agent_type, session_id)

    def _on_delete_session(self, session_id: str) -> None:
        self._conv_store.delete_session(session_id)
        self._clear_all_panels()
        self._load_conversations()
        self._refresh_history_dropdown_if_open()
        logger.info("Deleted session: {}", session_id)

    def _refresh_history_dropdown_if_open(self) -> None:
        """Repopulate the history dropdown with fresh data if it is open.

        Deleting a session mutates the store but the open dropdown is a static
        snapshot, so it would otherwise still show the removed entry.
        """
        if self.agent_panel.is_history_dropdown_visible():
            sessions = self._conv_store.get_sessions(self.current_agent_type)
            current_id = self._conv_store.get_current_session_id(self.current_agent_type)
            self.agent_panel.show_history_dropdown(sessions, current_id)

    def _on_rename_session(self, session_id: str, new_name: str) -> None:
        self._conv_store.rename_session(session_id, new_name)
        self._refresh_history_dropdown_if_open()
        logger.info("Renamed session {} to {}", session_id, new_name)

    def _clear_all_panels(self) -> None:
        self.agent_panel._messages_area.clear()

    def _subscribe_to_debug_messages(self) -> None:
        self.agent_panel.subscribe_to_debug_messages(self.backend.bus)

    def closeEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "preview"):
            self.preview.save_open_tabs()
        if hasattr(self, "file_tree"):
            self.file_tree.save_state()
        super().closeEvent(event)

    def resizeEvent(self, event):
        """Handle window resize to maintain proportional layout."""
        super().resizeEvent(event)
        if not self._splitter_sizes_initialized:
            self._apply_splitter_sizes(force=True)

    def showEvent(self, event) -> None:
        """Finalize splitter sizing after child widgets compute minimum widths."""
        self.prepare_initial_render()
        super().showEvent(event)

    def changeEvent(self, event) -> None:
        """Handle window state changes (maximize/restore/fullscreen)."""
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            if self._title_bar:
                is_maximized = self.windowState() & Qt.WindowState.WindowMaximized
                is_fullscreen = self.windowState() & Qt.WindowState.WindowFullScreen
                self._title_bar.update_maximize_button(bool(is_maximized or is_fullscreen))

    def _apply_splitter_sizes(self, force: bool = False) -> None:
        if not hasattr(self, "_main_splitter"):
            return
        if self._splitter_sizes_initialized and not force:
            return
        total_width = self._main_splitter.width()
        if total_width <= 0:
            return

        # file_tree gets a fixed default clamped on BOTH sides:
        #  - lower bound: its own minimumWidth() and the default (never too small)
        #  - upper bound: the default, the max cap, AND a fraction of the window
        #    width (so it can never dominate on small/narrow screens).
        file_tree_default = _FILE_TREE_DEFAULT_WIDTH
        file_tree_min = self.file_tree.minimumWidth()
        file_tree_max = self.file_tree.maximumWidth() or file_tree_default
        proportional_cap = int(total_width * _FILE_TREE_MAX_FRACTION)
        file_tree_size = max(
            file_tree_min,
            min(file_tree_default, file_tree_max, proportional_cap),
        )

        preview_min = self.preview.minimumWidth()
        agent_panel_min = self.agent_panel.minimumWidth()

        remaining = max(0, total_width - file_tree_size)
        # Split remaining 56:44 (matches stretch factors), honoring minimums.
        preview_size = max(preview_min, int(remaining * 56 / 100))
        agent_panel_size = max(agent_panel_min, remaining - preview_size)

        # If sum exceeds total, scale down proportionally
        total_calculated = file_tree_size + preview_size + agent_panel_size
        if total_calculated > total_width:
            scale = total_width / total_calculated
            file_tree_size = int(file_tree_size * scale)
            preview_size = int(preview_size * scale)
            agent_panel_size = int(agent_panel_size * scale)

        sizes = [file_tree_size, preview_size, agent_panel_size]
        self._main_splitter.setSizes(sizes)
        self._splitter_sizes_initialized = True
