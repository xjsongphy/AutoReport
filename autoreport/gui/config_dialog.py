"""Configuration dialog with multi-provider support and cc-switch presets."""

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config.manager import ConfigManager
from ..config.presets import ProviderPreset, get_presets_by_category, load_presets
from ..config.schema import ApiConfig
from ..core.preset_sync import is_cached, sync_presets
from ..core.providers.defaults import DEFAULT_API_BASES, DEFAULT_MODELS
from .dialogs import information_box, question_box, warning_box
from .theme import get_theme_colors
from .widgets.ui_utils import (
    IconActionButton,
    NoWheelComboBox,
    TextButton,
    combo_box_qss,
    dashed_button_qss,
    filled_button_qss,
    ghost_button_qss,
    line_edit_qss,
    render_svg_icon,
    secondary_filled_button_qss,
)

CATEGORY_LABELS = {
    "official": "官方",
    "cn_official": "国内官方",
    "aggregator": "聚合平台",
    "third_party": "第三方",
    "cloud_provider": "云服务商",
    "custom": "自定义",
    "builtin": "内置",
}

PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (GPT)",
    "google": "Google (Gemini)",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
    "groq": "Groq",
    "custom": "自定义 / 兼容",
}


class ConfigCard(QFrame):
    """Card widget for a single API configuration."""

    delete_requested = pyqtSignal()

    def __init__(self, config: ApiConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("providerCard")
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        self.name_input = QLineEdit()
        self.name_input.setText(self.config.name)
        grid.addWidget(QLabel("名称"), 0, 0)

        self.delete_btn = IconActionButton(
            text="×",
            tooltip="删除此配置",
            object_name="deleteBtn",
            button_size=(32, 28),
        )
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        grid.addWidget(self._field_with_action(self.name_input, self.delete_btn), 0, 1, 1, 2)

        self.provider_combo = NoWheelComboBox()
        for pid, label in PROVIDER_LABELS.items():
            self.provider_combo.addItem(label, pid)
        idx = self.provider_combo.findData(self.config.provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        grid.addWidget(QLabel("类型"), 1, 0)
        grid.addWidget(self.provider_combo, 1, 1, 1, 2)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setText(self.config.api_key or "")
        self.key_input.setPlaceholderText("sk-...")
        grid.addWidget(QLabel("API Key"), 2, 0)

        self.show_key_btn = IconActionButton(
            tooltip="显示 API Key",
            object_name="showKeyBtn",
            button_size=(32, 28),
            icon_size=(16, 16),
            on_click=self._toggle_key_visibility,
        )
        self._update_key_visibility_icon(False)
        grid.addWidget(self._field_with_action(self.key_input, self.show_key_btn), 2, 1, 1, 2)

        self.base_url_input = QLineEdit()
        self.base_url_input.setText(self.config.api_base or "")
        self.base_url_input.setPlaceholderText("https://api.example.com")
        grid.addWidget(QLabel("Base URL"), 3, 0)
        grid.addWidget(self.base_url_input, 3, 1, 1, 2)

        self.model_input = QLineEdit()
        self.model_input.setText(self.config.default_model or "")
        self.model_input.setPlaceholderText("例如: claude-sonnet-4-20250514")
        grid.addWidget(QLabel("默认模型"), 4, 0)
        grid.addWidget(self.model_input, 4, 1)

        c = get_theme_colors()
        self.test_btn = TextButton(
            text="测试连接",
            tooltip="测试连接",
            color=c["buttonBlue"],
            object_name="testBtn",
            on_click=self._test_connection,
        )
        grid.addWidget(self.test_btn, 4, 2)
        layout.addLayout(grid)

    def _field_with_action(self, field: QLineEdit, button: QPushButton) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(field, 1)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignRight)
        return row

    def _toggle_key_visibility(self) -> None:
        is_visible = self.key_input.echoMode() == QLineEdit.EchoMode.Normal
        if is_visible:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._update_key_visibility_icon(False)
        else:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self._update_key_visibility_icon(True)

    def _update_key_visibility_icon(self, is_visible: bool) -> None:
        c = get_theme_colors()
        icon_name = "eye-off" if is_visible else "eye"
        icon = render_svg_icon(icon_name, QColor(c["fg"]), size=16)
        self.show_key_btn.setIcon(icon)
        tooltip = "隐藏 API Key" if is_visible else "显示 API Key"
        self.show_key_btn.setToolTip(tooltip)

    def _on_provider_changed(self) -> None:
        provider = self.provider_combo.currentData()
        default_base = DEFAULT_API_BASES.get(provider, "")
        default_model = DEFAULT_MODELS.get(provider, "")

        if provider == "anthropic":
            placeholder = "https://api.anthropic.com"
        else:
            placeholder = default_base or "https://api.example.com"

        self.base_url_input.setPlaceholderText(placeholder)
        # Always update base URL and model when provider type changes
        if default_base:
            self.base_url_input.setText(default_base)
        if default_model:
            self.model_input.setText(default_model)

    def _on_delete_clicked(self) -> None:
        self.delete_requested.emit()

    def _test_connection(self) -> None:
        api_key = self.key_input.text().strip()
        if not api_key:
            warning_box(self, "测试失败", "未配置 API Key。")
            return
        information_box(
            self, "测试结果",
            f"API Key 已配置（{self.name_input.text()}，连接测试功能待实现）。",
        )

    def get_config(self) -> ApiConfig:
        return ApiConfig(
            id=self.config.id,
            name=self.name_input.text().strip() or self.config.name,
            provider=self.provider_combo.currentData(),
            api_key=self.key_input.text().strip() or None,
            api_base=self.base_url_input.text().strip() or None,
            enabled=True,
            default_model=self.model_input.text().strip() or None,
        )


class PresetSelectorDialog(QDialog):
    """Dialog for selecting a provider preset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_preset: ProviderPreset | None = None
        self._setup_ui()

    @property
    def selected_preset(self) -> ProviderPreset | None:
        return self._selected_preset

    def _setup_ui(self) -> None:
        self.setWindowTitle("选择预设模板")
        self.setMinimumSize(520, 480)
        self.resize(560, 560)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        hint = QLabel("选择一个预设模板自动填充配置。来源于 cc-switch 仓库。")
        hint.setWordWrap(True)
        hint.setObjectName("dialogSubtitle")
        layout.addWidget(hint)

        groups = get_presets_by_category()

        # Tabs or grouped list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)

        scroll_content = QWidget(self)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)

        for cat, presets in groups.items():
            if not presets:
                continue
            cat_label = QLabel(CATEGORY_LABELS.get(cat, cat))
            cat_label.setObjectName("categoryLabel")
            scroll_layout.addWidget(cat_label)

            for preset in presets:
                btn = QPushButton()
                btn.setObjectName("presetBtn")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda checked, p=preset: self._select(p))

                btn.setText(preset.name)
                scroll_layout.addWidget(btn)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # Bottom buttons: blank config + cancel
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        blank_btn = QPushButton("空白自定义配置")
        blank_btn.setObjectName("blankBtn")
        blank_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        blank_btn.clicked.connect(self._select_blank)
        bottom_row.addWidget(blank_btn)

        bottom_row.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)

        layout.addLayout(bottom_row)

    def _select(self, preset: ProviderPreset) -> None:
        self._selected_preset = preset
        self._is_blank = False
        self.accept()

    def _select_blank(self) -> None:
        self._selected_preset = None
        self._is_blank = True
        self.accept()


class ConfigDialog(QDialog):
    """Multi-configuration API settings dialog with preset support."""

    _sync_finished = pyqtSignal(int, bool, str)  # n, cached, error_msg

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self._config_manager = config_manager
        self._cards: list[ConfigCard] = []
        self._sync_finished.connect(self._on_sync_finished)
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        self.setWindowTitle("API 配置")
        self.setMinimumSize(620, 520)
        self.resize(640, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget(self)
        header.setObjectName("dialogHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 20, 24, 16)

        title_row = QHBoxLayout()
        title = QLabel("API 配置")
        title.setObjectName("dialogTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        c = get_theme_colors()
        self.sync_btn = TextButton(
            text="同步预设",
            tooltip="从 cc-switch 仓库同步最新预设模板",
            color=c["buttonBlue"],
            object_name="syncBtn",
            on_click=self._sync_presets,
        )
        title_row.addWidget(self.sync_btn)

        header_layout.addLayout(title_row)

        subtitle = QLabel("管理 API 配置。选择启用配置后所有 Agent 将使用该服务商。\n预设模板数据来自 cc-switch 仓库，点击「同步预设」获取最新。")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)

        warning = QLabel(
            "⚠ 部分订阅服务商（如智谱）不允许第三方工具调用 API，"
            "使用前请自行确认服务条款。"
        )
        warning.setObjectName("apiWarning")
        warning.setWordWrap(True)
        header_layout.addWidget(warning)

        # Enabled config selector
        enabled_row = QHBoxLayout()
        enabled_row.setSpacing(8)
        enabled_label = QLabel("启用配置:")
        enabled_label.setObjectName("activeLabel")
        enabled_row.addWidget(enabled_label)

        self.enabled_combo = NoWheelComboBox()
        self.enabled_combo.setMinimumWidth(200)
        enabled_row.addWidget(self.enabled_combo, 1)
        enabled_row.addStretch()

        header_layout.addLayout(enabled_row)
        root.addWidget(header)

        # Scrollable config cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.scroll_content = QWidget(self)
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(20, 8, 20, 8)
        self.scroll_layout.setSpacing(12)

        # Empty hint — must exist before _rebuild_cards calls _update_empty_hint_visibility
        self._empty_hint = QLabel("暂无 API 配置。点击下方「+ 添加配置」开始。")
        self._empty_hint.setObjectName("emptyHint")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setWordWrap(True)

        self._rebuild_cards()
        self._refresh_enabled_combo()
        self.scroll_layout.addStretch()
        scroll.setWidget(self.scroll_content)
        root.addWidget(scroll, 1)

        self._update_empty_hint_visibility()
        self.scroll_layout.addWidget(self._empty_hint)

        # Footer
        footer = QWidget(self)
        footer.setObjectName("dialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 12, 24, 16)
        footer_layout.setSpacing(12)

        self.add_btn = QPushButton("+ 添加配置")
        self.add_btn.setObjectName("addBtn")
        self.add_btn.clicked.connect(self._add_config)
        footer_layout.addWidget(self.add_btn)

        footer_layout.addStretch()

        self.reset_btn = QPushButton("恢复默认")
        self.reset_btn.setObjectName("resetBtn")
        self.reset_btn.clicked.connect(self._reset_config)
        footer_layout.addWidget(self.reset_btn)


        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.clicked.connect(self._save_config)
        self.save_btn.setDefault(True)
        footer_layout.addWidget(self.save_btn)

        root.addWidget(footer)

    def _refresh_enabled_combo(self) -> None:
        """Refresh the enabled config dropdown with auto-detection.

        Auto-detection logic:
        1. Try to match the saved active_id
        2. If no match, auto-select the first config with API key
        3. Otherwise, select the first config
        """
        self.enabled_combo.clear()
        configs = [c.get_config() for c in self._cards] if self._cards else []
        active_id = self._config_manager.config.providers.active

        matched = False
        first_with_key_idx = -1

        for i, cfg in enumerate(configs):
            label = f"{cfg.name} ({PROVIDER_LABELS.get(cfg.provider, cfg.provider)})"
            self.enabled_combo.addItem(label, cfg.id)
            if cfg.id == active_id:
                self.enabled_combo.setCurrentIndex(self.enabled_combo.count() - 1)
                matched = True
            # Track first config with API key
            if first_with_key_idx < 0 and cfg.api_key:
                first_with_key_idx = self.enabled_combo.count() - 1

        # Auto-detect: if no match, select first config with API key
        if not matched and configs:
            if first_with_key_idx >= 0:
                self.enabled_combo.setCurrentIndex(first_with_key_idx)
                self._config_manager.config.providers.active = configs[first_with_key_idx].id
            else:
                # No configs with API key, select first one
                self._config_manager.config.providers.active = configs[0].id
                self.enabled_combo.setCurrentIndex(0)
        elif not configs:
            self._config_manager.config.providers.active = ""

    def _rebuild_cards(self) -> None:
        for card in self._cards:
            self.scroll_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        configs = self._config_manager.config.providers.configurations
        for cfg in configs:
            card = ConfigCard(cfg)
            card.delete_btn.clicked.connect(lambda checked, c=card: self._remove_card(c))
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 2, card)
            self._cards.append(card)

        self._update_empty_hint_visibility()

    def _update_empty_hint_visibility(self) -> None:
        show_hint = len(self._cards) == 0
        self._empty_hint.setVisible(show_hint)
        # When showing hint, hide the stretch before it to center it
        if show_hint:
            # Find the stretch spacer before the hint
            for i in range(self.scroll_layout.count() - 1):
                item = self.scroll_layout.itemAt(i)
                if item and item.spacerItem():
                    item.spacerItem().changeSize(0, 0, QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        else:
            # Restore stretch
            for i in range(self.scroll_layout.count() - 1):
                item = self.scroll_layout.itemAt(i)
                if item and item.spacerItem():
                    item.spacerItem().changeSize(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _remove_card(self, card: ConfigCard) -> None:
        cfg = card.get_config()
        was_active = cfg.id == self._config_manager.config.providers.active
        self._cards.remove(card)
        self.scroll_layout.removeWidget(card)
        card.deleteLater()
        if was_active and self._cards:
            self._config_manager.config.providers.active = self._cards[0].get_config().id
        elif was_active:
            self._config_manager.config.providers.active = ""
        self._refresh_enabled_combo()
        self._update_empty_hint_visibility()

    def _add_card(self, cfg: ApiConfig) -> None:
        card = ConfigCard(cfg)
        card.delete_btn.clicked.connect(lambda checked, c=card: self._remove_card(c))
        self.scroll_layout.insertWidget(self.scroll_layout.count() - 2, card)
        self._cards.append(card)
        self._refresh_enabled_combo()
        self._update_empty_hint_visibility()

    def _add_config(self) -> None:
        dlg = PresetSelectorDialog(self)
        result = dlg.exec()

        if result != QDialog.DialogCode.Accepted:
            return

        if getattr(dlg, "_is_blank", False):
            self._add_card(ApiConfig(name="新配置", provider="custom", enabled=True))
        elif dlg.selected_preset:
            preset = dlg.selected_preset
            self._add_card(ApiConfig(
                name=preset.name,
                provider=preset.provider,
                api_base=preset.base_url if preset.base_url else None,
                default_model=preset.default_model if preset.default_model else None,
                enabled=True,
            ))

    def _sync_presets(self) -> None:
        from threading import Thread

        self.sync_btn.setEnabled(False)
        self.sync_btn.setText("同步中...")

        def _run():
            try:
                n = sync_presets(timeout=15)
                cached = is_cached()
                error_msg = ""
            except Exception as e:
                n = 0
                cached = False
                error_msg = str(e)
            self._sync_finished.emit(n, cached, error_msg)

        Thread(target=_run, daemon=True).start()

    def _on_sync_finished(self, n: int, cached: bool, error_msg: str) -> None:
        self.sync_btn.setEnabled(True)
        self.sync_btn.setText("同步预设")

        if error_msg:
            warning_box(
                None, "同步失败",
                f"预设同步出错：{error_msg}\n将使用内置预设模板。",
            )
        elif cached:
            count = len(load_presets())
            information_box(
                None, "同步完成",
                f"成功同步 {n} 个文件。\n当前共 {count} 个预设模板可用。",
            )
        else:
            warning_box(
                None, "同步失败",
                "无法下载预设文件，请检查网络连接和代理设置。\n"
                "将使用内置预设模板。",
            )

    def _save_config(self) -> None:
        cfg = self._config_manager.config

        new_configs = [card.get_config() for card in self._cards]
        cfg.providers.configurations = new_configs

        if self.enabled_combo.currentData():
            cfg.providers.active = self.enabled_combo.currentData()
        elif new_configs:
            cfg.providers.active = new_configs[0].id

        self._config_manager.save_config()
        logger.info("Configuration saved: {} configs", len(new_configs))
        information_box(self, "保存成功", "API 配置已保存。")
        self.accept()

    def _reset_config(self) -> None:
        reply = question_box(
            self,
            "确认重置",
            "确定要恢复默认配置吗？\n\n这将删除所有自定义配置并恢复默认设置。",
            default=QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._config_manager.reset_config()
        # Rebuild UI
        self._cards.clear()
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._rebuild_cards()
        self._refresh_enabled_combo()

        logger.info("Configuration reset to defaults")
        information_box(self, "重置完成", "配置已恢复为默认值。请重新配置 API Key。")

    def _apply_style(self) -> None:
        from PyQt6.QtGui import QPalette
        c = get_theme_colors()
        # Add/override colors specific to config dialog
        c["addBtnBorder"] = c["buttonBlue"]  # 蓝色添加按钮边框
        c["addBtnFg"] = c["buttonBlue"]
        c["deleteFg"] = c["fg"]  # 使用主题前景色
        c["deleteHoverBg"] = c["warningBg"]
        c["deleteHoverFg"] = c["warningFg"]
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.setStyleSheet(f"""
            ConfigDialog {{
                background-color: {c["bg"]};
            }}
            #dialogHeader {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
            }}
            #dialogTitle {{
                font-size: 20px;
                font-weight: {c["fw_semibold"]};
                color: {c["fg"]};
            }}
            #dialogSubtitle {{
                font-size: 13px;
                color: {c["muted"]};
                margin-top: 4px;
            }}
            #apiWarning {{
                font-size: 12px;
                color: {c["warningFg"]};
                padding: 6px 10px;
                background-color: {c["warningBg"]};
                border: 1px solid {c["warningBorder"]};
                border-radius: {c["radius_md"]};
                margin-top: 8px;
            }}
            #emptyHint {{
                font-size: 14px;
                color: {c["muted"]};
                padding: 40px 20px;
            }}
            #activeLabel {{
                font-size: 13px;
                font-weight: {c["fw_semibold"]};
                color: {c["activeFg"]};
            }}
            #dialogFooter {{
                background-color: {c["surface"]};
                border-top: 1px solid {c["border"]};
            }}
            #providerCard {{
                background-color: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: {c["radius_lg"]};
            }}
            #categoryLabel {{
                font-size: 12px;
                font-weight: {c["fw_semibold"]};
                color: {c["fg"]};
                text-transform: uppercase;
                margin-top: 4px;
            }}
            {filled_button_qss(
                "#saveBtn",
                bg=c["buttonBlue"],
                fg=c["primaryBtnFg"],
                hover_bg=c["buttonBlue"],
                disabled_bg=c["border"],
                disabled_fg=c["muted"],
                radius=c["radius_md"],
                padding="8px 24px",
                font_size=13,
            )}
            QPushButton#saveBtn:pressed {{
                background-color: {c["buttonBlue"]};
            }}
            {secondary_filled_button_qss(
                "#addBtn",
                radius=c["radius_md"],
                padding="8px 16px",
                font_size=13,
            )}
            {secondary_filled_button_qss("#cancelBtn")}
            {ghost_button_qss(
                "#resetBtn",
                fg=c["resetFg"],
                hover_bg="transparent",
                hover_fg=c["resetHoverFg"],
                padding="8px 16px",
                font_size=13,
            )}
            QPushButton#resetBtn:hover {{ text-decoration: underline; }}
            #deleteBtn {{
                background-color: transparent;
                color: {c["deleteFg"]};
                border: none;
                font-size: 16px;
                font-weight: {c["fw_bold"]};
            }}
            #deleteBtn:hover {{
                color: {c["deleteHoverFg"]};
                background-color: {c["deleteHoverBg"]};
                border: none;
                border-radius: {c["radius_sm"]};
            }}
            #showKeyBtn {{
                background-color: transparent;
                border: none;
                border-radius: {c["radius_sm"]};
            }}
            #showKeyBtn:hover {{
                background-color: {c["hover"]};
            }}
            {secondary_filled_button_qss(
                "#presetBtn",
                radius=c["radius_md"],
                padding="10px 14px",
                font_size=13,
            )}
            QPushButton#presetBtn {{
                text-align: left;
            }}
            {dashed_button_qss(
                "#blankBtn",
                fg=c["muted"],
                border=c["inputBorder"],
                hover_bg="transparent",
                hover_fg=c["buttonBlue"],
                hover_border=c["buttonBlue"],
                radius=c["radius_sm"],
                padding="6px 14px",
                font_size=12,
            )}
            {line_edit_qss(
                "",
                border_color=c["inputBorder"],
                focus_border_color=c["buttonBlue"],
                background_color=c["inputBg"],
                foreground_color=c["inputFg"],
                disabled_bg=c["inputDisabledBg"],
                disabled_fg=c["inputDisabledFg"],
                radius=c["radius_sm"],
                font_size=13,
                padding="6px 10px",
            )}
            QCheckBox {{ font-size: 13px; color: {c["checkFg"]}; }}
            {combo_box_qss(
                "",
                border_color=c["inputBorder"],
                background_color=c["inputBg"],
                foreground_color=c["inputFg"],
                hover_border_color=c["buttonBlue"],
                selection_bg=c["selectionBlue"],
                selection_fg=c["fg"],
                font_size=13,
                padding="6px 30px 6px 10px",
                radius=c["radius_sm"],
                popup_radius=c["radius_sm"],
                item_radius="4px",
            )}
            /* Icon buttons inside provider cards */
            IconActionButton {{
                background-color: transparent;
                border: none;
                border-radius: {c["radius_sm"]};
            }}
            IconActionButton:hover {{
                background-color: {c["hover"]};
            }}
            QScrollArea {{
                background-color: {c["bg"]};
                border: none;
            }}
            QScrollArea > QWidget {{
                background-color: {c["bg"]};
            }}
        """)

        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            try:
                hints.colorSchemeChanged.disconnect(self._apply_style)
            except Exception:
                pass
            hints.colorSchemeChanged.connect(self._apply_style)
