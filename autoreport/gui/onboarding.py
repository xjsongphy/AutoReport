"""First-time user onboarding wizard.

Split into two phases:
  Phase 1 (PreProjectGuide): Shown BEFORE project selection — welcome + quick start.
  Phase 2 (OnboardingDialog): Shown AFTER main window — agent intro + data placement.
    Only shown if user chose "new user" in Phase 1.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.user_settings import UserSettings
from .theme import get_theme_colors, is_dark_mode
from .widgets.ui_utils import filled_button_qss, ghost_button_qss


# ── Page builder helpers ──────────────────────────────────────────────

def _make_step_page(
    step: int,
    total: int,
    title: str,
    description: str,
    tips: list[str] | None = None,
) -> QWidget:
    """Create a standard tutorial step page with scrollable content.

    Args:
        step: Current step number (1-based).
        total: Total number of steps.
        title: Page title.
        description: Main body text (supports basic HTML).
        tips: Optional list of tip lines shown in a highlighted box.

    Returns:
        Configured QWidget with scroll area for this page.
    """
    colors = get_theme_colors()

    # Create outer container widget
    page = QWidget()
    page.setObjectName("onboardingPage")
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(0, 0, 0, 0)
    page_layout.setSpacing(0)

    # Create scroll area
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setObjectName("pageScroll")

    # Create content widget
    content = QWidget()
    content.setObjectName("pageContent")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(48, 36, 48, 28)
    layout.setSpacing(16)

    # Step indicator
    step_label = QLabel(f"第 {step} 步 / 共 {total} 步")
    step_label.setStyleSheet(
        f"font-size: 12px; color: {colors['muted']}; "
        f"font-weight: {colors['fw_medium']};"
    )
    layout.addWidget(step_label)

    # Title
    title_label = QLabel(title)
    title_font = QFont()
    title_font.setPointSize(18)
    title_font.setBold(True)
    title_label.setFont(title_font)
    title_label.setStyleSheet(f"color: {colors['title']};")
    title_label.setWordWrap(True)
    layout.addWidget(title_label)

    # Separator
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"background-color: {colors['border']}; max-height: 1px;")
    layout.addWidget(sep)

    # Description
    desc = QLabel(description)
    desc.setWordWrap(True)
    desc.setStyleSheet(
        f"font-size: 14px; color: {colors['fg']}; line-height: 1.7;"
    )
    layout.addWidget(desc)

    # Tips box
    if tips:
        # Outer container - dark background
        tip_outer = QWidget()
        tip_outer.setStyleSheet(f"background-color: {colors['surface']};")
        tip_outer_layout = QVBoxLayout(tip_outer)
        tip_outer_layout.setContentsMargins(0, 0, 0, 0)
        tip_outer_layout.setSpacing(0)

        # Inner box - neutral gray background with subtle border
        tip_bg = colors["secondaryBtnBg"]
        tip_border = colors["secondaryBtnBorder"]

        tip_container = QWidget()
        tip_container.setStyleSheet(
            f"background-color: {tip_bg}; "
            f"border: 1px solid {tip_border}; "
            f"border-radius: {colors['radius_md']}; "
            f"margin: 14px 18px;"
        )
        tip_layout = QVBoxLayout(tip_container)
        tip_layout.setContentsMargins(14, 12, 14, 12)
        tip_layout.setSpacing(6)

        tip_header = QLabel("💡 关键提示")
        tip_header.setStyleSheet(
            f"font-size: 13px; font-weight: {colors['fw_semibold']}; "
            f"color: {colors['title']}; background: transparent; border: none;"
        )
        tip_layout.addWidget(tip_header)

        for tip in tips:
            tip_line = QLabel(f"• {tip}")
            tip_line.setWordWrap(True)
            tip_line.setStyleSheet(
                f"font-size: 13px; color: {colors['fg']}; "
                f"background: transparent; border: none;"
            )
            tip_layout.addWidget(tip_line)

        tip_outer_layout.addWidget(tip_container)
        layout.addWidget(tip_outer)

    layout.addStretch()

    # Set content as scroll widget
    scroll.setWidget(content)
    page_layout.addWidget(scroll)

    return page


# ── Phase 1: Pre-project guide ───────────────────────────────────────

class PreProjectGuide(QDialog):
    """Welcome guide shown BEFORE the project selection dialog.

    Gives users a quick overview and lets them choose whether to
    see the full tutorial after entering the project.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wants_tutorial = False

        self.setWindowTitle("AutoReport — 欢迎")
        self.setMinimumSize(560, 400)
        self.resize(580, 420)
        self.setModal(True)

        self._setup_ui()
        self._apply_style()

    @property
    def wants_tutorial(self) -> bool:
        """True if the user wants to see the full tutorial later."""
        return self._wants_tutorial

    def _setup_ui(self) -> None:
        colors = get_theme_colors()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Create scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Create content widget
        content = QWidget()
        content.setObjectName("guideContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(48, 40, 48, 32)
        content_layout.setSpacing(12)

        # Logo
        logo = QLabel("🧪")
        logo.setStyleSheet("font-size: 48px;")
        content_layout.addWidget(logo)

        # Title
        title = QLabel("欢迎使用 AutoReport")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {colors['title']};")
        content_layout.addWidget(title)

        content_layout.addSpacing(4)

        # Description
        desc = QLabel(
            "AutoReport 是一个<b>多 Agent 协作</b>的物理实验报告自动撰写系统。<br>"
            "您只需提供实验数据和实验要求，四个子 Agent 会自动完成<br>"
            "理论推导、数据处理、图表绘制和 LaTeX 报告生成。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 14px; color: {colors['fg']}; line-height: 1.6;")
        content_layout.addWidget(desc)

        content_layout.addSpacing(4)

        # Quick start guide
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {colors['border']}; max-height: 1px;")
        content_layout.addWidget(sep)

        guide_title = QLabel("📌 下一步您需要：")
        guide_title.setStyleSheet(
            f"font-size: 14px; font-weight: {colors['fw_semibold']}; color: {colors['title']};"
        )
        content_layout.addWidget(guide_title)

        steps = [
            "在弹出的项目选择窗口中，点击<b>「新建项目…」</b>",
            "选择一个位置，<b>新建一个空文件夹</b>，命名如 <code>C-V法测量杂质分布</code>",
            "系统会自动创建 <code>Data/</code>、<code>References/</code> 等子目录",
        ]
        for i, step_text in enumerate(steps, 1):
            step_label = QLabel(f"{i}. {step_text}")
            step_label.setWordWrap(True)
            step_label.setStyleSheet(
                f"font-size: 14px; color: {colors['fg']}; line-height: 1.5;"
            )
            content_layout.addWidget(step_label)

        content_layout.addSpacing(12)
        content_layout.addStretch()

        # Set content as scroll widget
        scroll.setWidget(content)
        root.addWidget(scroll)

        # Buttons (fixed at bottom, outside scroll)
        btn_container = QWidget()
        btn_container.setObjectName("btnBar")
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(48, 12, 48, 20)
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        self._skip_btn = QPushButton("我用过了，直接开始")
        self._skip_btn.setObjectName("ghostBtn")
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.clicked.connect(self._on_skip)
        btn_layout.addWidget(self._skip_btn)

        self._start_btn = QPushButton("我是新用户，开始教程 →")
        self._start_btn.setObjectName("primaryBtn")
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self._start_btn)

        root.addWidget(btn_container)

    def _on_start(self) -> None:
        self._wants_tutorial = True
        self.accept()

    def _on_skip(self) -> None:
        # "我用过了" — record that onboarding has been seen so the welcome
        # guide is not shown again on subsequent launches.
        UserSettings().has_seen_onboarding = True
        self._wants_tutorial = False
        self.accept()

    def _apply_style(self) -> None:
        colors = get_theme_colors()
        self.setStyleSheet(f"""
            PreProjectGuide {{
                background-color: {colors["surface"]};
            }}
            #guideContent {{
                background-color: {colors["surface"]};
            }}
            #btnBar {{
                background-color: {colors["surface"]};
                border-top: 1px solid {colors["border"]};
            }}
            {filled_button_qss(
                "#primaryBtn",
                bg=colors["buttonBlue"],
                fg=colors["primaryBtnFg"],
                hover_bg=colors["buttonBlue"],
                disabled_bg=colors["border"],
                disabled_fg=colors["muted"],
                radius=colors["radius_sm"],
                padding="8px 20px",
                font_size=13,
            )}
            {ghost_button_qss("#ghostBtn")}
        """)


# ── Phase 2: Post-project tutorial ───────────────────────────────────

class OnboardingDialog(QDialog):
    """Post-project tutorial shown AFTER the main window opens.

    Covers Agent panels, chatting, data placement, and final tips.
    Only shown if the user chose "new user" in Phase 1.

    Emits ``completed`` when the user finishes the tutorial.
    """

    completed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user_settings = UserSettings()
        self._was_new_user = False

        self.setWindowTitle("AutoReport — 新手引导")
        self.setMinimumSize(620, 480)
        self.resize(640, 520)
        self.setModal(True)

        self._setup_ui()
        self._apply_style()

    @property
    def was_new_user(self) -> bool:
        """True if the user went through the full tutorial (not skipped)."""
        return self._was_new_user

    # ── UI setup ──────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Stacked pages (no welcome page — starts at step 1) ──
        self._stack = QStackedWidget(self)

        total_steps = 4
        step_pages = [
            _make_step_page(
                1, total_steps,
                "认识 Agent 面板",
                "进入主界面后，右侧会显示<b>多个 Agent 面板</b>：<br><br>"
                "<b>🧭 Main Agent（主 Agent，最右侧）</b><br>"
                "总协调者，接收你的指令，分派任务给子 Agent。你只需要和它对话。<br><br>"
                "<b>📐 Theory Agent</b> — 理论推导<br>"
                "<b>📊 Data Analysis Agent</b> — 数据处理与计算<br>"
                "<b>📈 Plotting Agent</b> — 绘制图表<br>"
                "<b>📝 Report Agent</b> — 撰写 LaTeX 报告<br><br>"
                "每个子 Agent 都有自己的面板，你可以点击查看它们的工作进度。",
                tips=[
                    "你只需要和 Main Agent 对话，它会自动调度子 Agent",
                    "子 Agent 之间也会自动传递数据——Theory → Analysis → Plotting → Report",
                ],
            ),
            _make_step_page(
                2, total_steps,
                "和 Main Agent 对话",
                "在 Main Agent 面板底部的输入框中，<b>用自然语言描述你的实验报告需求</b>。<br><br>"
                "例如：<br>"
                "<blockquote>"
                "请撰写'电容电压法测量半导体中的杂质分布'实验报告。"
                "数据文件在 Data/ 目录下，参考资料在 References/ 目录中。"
                "</blockquote>"
                "<br>"
                "Main Agent 会自动分析任务，依次调度 Theory → Data Analysis → Plotting → Report "
                "四个子 Agent 完成报告。<br><br>"
                "你可以随时发送新消息来干预或调整报告内容。",
                tips=[
                    "说得越具体越好——给出实验名称、数据位置、特殊要求",
                    "子 Agent 工作时，你可以在它们各自的面板看到实时进度",
                ],
            ),
            _make_step_page(
                3, total_steps,
                "放入数据和参考资料",
                "<b>这是最关键的一步！</b>在发送报告指令之前，先把文件放到正确的位置：<br><br>"
                "📂 <b>Data/</b> ← 放入<b>原始实验数据文件</b><br>"
                "&nbsp;&nbsp;&nbsp;&nbsp;CSV、TXT、Excel 等数据文件<br>"
                "&nbsp;&nbsp;&nbsp;&nbsp;（Data Analysis Agent 会将处理结果写入 Data/Processed/）<br><br>"
                "📂 <b>References/</b> ← 放入<b>参考资料</b><br>"
                "&nbsp;&nbsp;&nbsp;&nbsp;实验讲义 PDF、实验要求等<br>"
                "&nbsp;&nbsp;&nbsp;&nbsp;也可放入<b>自定义 LaTeX 模板</b>（.tex / .cls 文件）<br>"
                "&nbsp;&nbsp;&nbsp;&nbsp;系统会<b>自动优先</b>使用你的模板，无需手动替换<br>"
                "⚠️ <b>数据必须放在项目文件夹内！</b>Agent 无法访问项目文件夹之外的文件。",
                tips=[
                    "你可以从文件管理器<b>直接拖拽</b>文件到左侧文件树的对应目录",
                    "放入数据后再发送报告指令——Agent 会立即开始工作",
                    "如果数据不在项目文件夹内，Agent 会找不到文件",
                ],
            ),
            _make_step_page(
                4, total_steps,
                "准备就绪！",
                "你已经了解了 AutoReport 的基本工作流程。总结一下：<br><br>"
                "✅ <b>1.</b> 创建项目文件夹<br>"
                "✅ <b>2.</b> 把数据放入 <code>Data/</code>，参考资料放入 <code>References/</code><br>"
                "✅ <b>3.</b> 在 Main Agent 面板中输入报告需求<br>"
                "✅ <b>4.</b> 等待 Agent 自动协作，查看进度<br>"
                "✅ <b>5.</b> 最终报告 PDF 在 <code>Tex/</code> 目录<br><br>"
                "点击下方按钮开始你的第一个项目吧！",
                tips=[
                    "任何时候都可以输入 /help 查看帮助",
                    "左侧文件树支持拖拽导入文件，也可以在预览面板查看文件内容",
                ],
            ),
        ]
        for page in step_pages:
            self._stack.addWidget(page)

        root.addWidget(self._stack, 1)

        # ── Navigation bar ──
        nav = QWidget(self)
        nav.setObjectName("navBar")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(40, 14, 40, 18)
        nav_layout.setSpacing(12)

        nav_layout.addStretch()

        # Buttons
        self._back_btn = QPushButton("上一步")
        self._back_btn.setObjectName("ghostBtn")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._on_back)
        nav_layout.addWidget(self._back_btn)

        self._next_btn = QPushButton("下一步")
        self._next_btn.setObjectName("primaryBtn")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._on_next)
        nav_layout.addWidget(self._next_btn)

        root.addWidget(nav)

        # ── State ──
        self._current_page = 0
        self._stack.setCurrentIndex(0)
        self._update_navigation()

    # ── Navigation ────────────────────────────────────────────────

    def _update_navigation(self) -> None:
        """Update button visibility and labels based on current page."""
        is_last_step = self._current_page == self._stack.count() - 1

        self._back_btn.setVisible(self._current_page > 0)

        if is_last_step:
            self._next_btn.setText("开始使用")
        else:
            self._next_btn.setText("下一步")

    def _on_next(self) -> None:
        """Handle next/start button click."""
        if self._current_page < self._stack.count() - 1:
            self._current_page += 1
            self._stack.setCurrentIndex(self._current_page)
            self._update_navigation()
        else:
            self._finish()

    def _on_back(self) -> None:
        """Handle back button click."""
        if self._current_page > 0:
            self._current_page -= 1
            self._stack.setCurrentIndex(self._current_page)
            self._update_navigation()

    def _finish(self) -> None:
        """Complete onboarding.

        Note: we intentionally do NOT set ``has_seen_onboarding`` here.  That
        flag controls whether the Phase 1 welcome guide reappears on future
        launches, and its contract is: the guide shows until the user clicks
        "我用过了" (``_on_skip``).  Completing the Phase 2 tutorial must not
        silently re-suppress the welcome guide — otherwise clicking "新手提示"
        would not stick.
        """
        if self._current_page >= 0:
            self._was_new_user = True

        self.completed.emit()
        self.accept()

    # ── Style ─────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        colors = get_theme_colors()
        self.setStyleSheet(f"""
            OnboardingDialog {{
                background-color: {colors["surface"]};
            }}
            #onboardingPage, #pageScroll, #pageContent {{
                background-color: {colors["surface"]};
            }}
            #navBar {{
                background-color: {colors["surface"]};
                border-top: 1px solid {colors["border"]};
            }}
            {filled_button_qss(
                "#primaryBtn",
                bg=colors["buttonBlue"],
                fg=colors["primaryBtnFg"],
                hover_bg=colors["buttonBlue"],
                disabled_bg=colors["border"],
                disabled_fg=colors["muted"],
                radius=colors["radius_sm"],
                padding="8px 20px",
                font_size=13,
            )}
            {ghost_button_qss("#ghostBtn")}
        """)


# ── Public API ───────────────────────────────────────────────────────

def show_pre_project_guide(parent=None, *, force: bool = False) -> bool:
    """Show the pre-project welcome guide.

    Returns True if the user wants the full tutorial,
    False if they chose to skip.

    Args:
        parent: Parent widget.
        force: If True, show the guide even if the user has dismissed it before
            (used by the "新手提示" button on the project selection page).

    Returns:
        bool: True → show full tutorial later; False → skip.
    """
    settings = UserSettings()
    if settings.has_seen_onboarding and not force:
        return False

    dialog = PreProjectGuide(parent)
    dialog.exec()
    return dialog.wants_tutorial


def show_onboarding(parent=None) -> OnboardingDialog | None:
    """Show the post-project tutorial (agent intro + data placement).

    Only call this if show_pre_project_guide() returned True.  Skipped silently
    when the user has already completed onboarding.

    Args:
        parent: Parent widget.

    Returns:
        The OnboardingDialog instance if shown, else ``None`` when already seen.
    """
    settings = UserSettings()
    if settings.has_seen_onboarding:
        return None

    dialog = OnboardingDialog(parent)
    dialog.exec()
    return dialog
