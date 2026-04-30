"""Configuration dialog with multi-provider support and cc-switch presets."""

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config.manager import ConfigManager
from ..config.presets import ProviderPreset, get_presets_by_category, load_presets
from ..config.schema import ApiConfig
from ..core.preset_sync import is_cached, sync_presets

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


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events to prevent accidental changes."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


class ConfigCard(QFrame):
    """Card widget for a single API configuration."""

    def __init__(self, config: ApiConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("providerCard")
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        # Row 1: Name + Delete button
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        name_label = QLabel("名称")
        name_label.setFixedWidth(60)
        row1.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setText(self.config.name)
        row1.addWidget(self.name_input, 1)

        self.delete_btn = QPushButton("×")
        self.delete_btn.setObjectName("deleteBtn")
        self.delete_btn.setFixedWidth(28)
        self.delete_btn.setToolTip("删除此配置")
        row1.addWidget(self.delete_btn)

        layout.addLayout(row1)

        # Row 2: Provider type + enabled
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        type_label = QLabel("类型")
        type_label.setFixedWidth(60)
        row2.addWidget(type_label)

        self.provider_combo = NoWheelComboBox()
        for pid, label in PROVIDER_LABELS.items():
            self.provider_combo.addItem(label, pid)
        idx = self.provider_combo.findData(self.config.provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        row2.addWidget(self.provider_combo, 1)

        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(self.config.enabled)
        self.enabled_check.toggled.connect(self._on_enabled_toggled)
        row2.addWidget(self.enabled_check)

        layout.addLayout(row2)

        # Row 3: API Key
        row3 = QHBoxLayout()
        row3.setSpacing(6)

        key_label = QLabel("API Key")
        key_label.setFixedWidth(60)
        row3.addWidget(key_label)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setText(self.config.api_key or "")
        self.key_input.setPlaceholderText("sk-...")
        row3.addWidget(self.key_input, 1)

        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setFixedWidth(32)
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setToolTip("显示/隐藏 API Key")
        self.show_key_btn.toggled.connect(self._toggle_key_visibility)
        row3.addWidget(self.show_key_btn)

        layout.addLayout(row3)

        # Row 4: Base URL
        row4 = QHBoxLayout()
        row4.setSpacing(6)

        url_label = QLabel("Base URL")
        url_label.setFixedWidth(60)
        row4.addWidget(url_label)

        self.base_url_input = QLineEdit()
        self.base_url_input.setText(self.config.api_base or "")
        self.base_url_input.setPlaceholderText("https://api.example.com")
        row4.addWidget(self.base_url_input, 1)

        layout.addLayout(row4)

        # Row 5: Default Model + Test button
        row5 = QHBoxLayout()
        row5.setSpacing(6)

        model_label = QLabel("默认模型")
        model_label.setFixedWidth(60)
        row5.addWidget(model_label)

        self.model_input = QLineEdit()
        self.model_input.setText(self.config.default_model or "")
        self.model_input.setPlaceholderText("例如: claude-sonnet-4-20250514")
        row5.addWidget(self.model_input, 1)

        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("testBtn")
        self.test_btn.clicked.connect(self._test_connection)
        row5.addWidget(self.test_btn)

        layout.addLayout(row5)

    def _toggle_key_visibility(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.key_input.setEchoMode(mode)

    def _on_enabled_toggled(self, enabled: bool) -> None:
        for w in (self.name_input, self.key_input, self.base_url_input,
                   self.model_input, self.provider_combo, self.test_btn,
                   self.show_key_btn):
            w.setEnabled(enabled)

    def _test_connection(self) -> None:
        api_key = self.key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "测试失败", "未配置 API Key。")
            return
        QMessageBox.information(
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
            enabled=self.enabled_check.isChecked(),
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

        scroll_content = QWidget()
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
        header = QWidget()
        header.setObjectName("dialogHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 20, 24, 16)

        title_row = QHBoxLayout()
        title = QLabel("API 配置")
        title.setObjectName("dialogTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        self.sync_btn = QPushButton("同步预设")
        self.sync_btn.setObjectName("syncBtn")
        self.sync_btn.setToolTip("从 cc-switch 仓库同步最新预设模板")
        self.sync_btn.clicked.connect(self._sync_presets)
        title_row.addWidget(self.sync_btn)

        header_layout.addLayout(title_row)

        subtitle = QLabel("管理 API 配置。选择活跃配置后所有 Agent 将使用该服务商。\n预设模板数据来自 cc-switch 仓库，点击「同步预设」获取最新。")
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

        # Active config switcher
        active_row = QHBoxLayout()
        active_row.setSpacing(8)
        active_label = QLabel("活跃配置:")
        active_label.setObjectName("activeLabel")
        active_row.addWidget(active_label)

        self.active_combo = NoWheelComboBox()
        self.active_combo.setMinimumWidth(200)
        self._refresh_active_combo()
        active_row.addWidget(self.active_combo, 1)
        active_row.addStretch()

        header_layout.addLayout(active_row)
        root.addWidget(header)

        # Scrollable config cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(20, 8, 20, 8)
        self.scroll_layout.setSpacing(12)

        self._rebuild_cards()
        self.scroll_layout.addStretch()
        scroll.setWidget(self.scroll_content)
        root.addWidget(scroll, 1)

        # Add config button
        add_row = QHBoxLayout()
        add_row.setContentsMargins(20, 4, 20, 4)
        add_btn = QPushButton("+ 添加配置")
        add_btn.setObjectName("addBtn")
        add_btn.clicked.connect(self._add_config)
        add_row.addWidget(add_btn)
        add_row.addStretch()
        root.addLayout(add_row)

        # Footer
        footer = QWidget()
        footer.setObjectName("dialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 12, 24, 16)
        footer_layout.setSpacing(12)

        self.reset_btn = QPushButton("恢复默认")
        self.reset_btn.setObjectName("resetBtn")
        self.reset_btn.clicked.connect(self._reset_config)
        footer_layout.addWidget(self.reset_btn)

        footer_layout.addStretch()

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

    def _refresh_active_combo(self) -> None:
        self.active_combo.clear()
        configs = [c.get_config() for c in self._cards] if self._cards else []
        active_id = self._config_manager.config.providers.active

        matched = False
        for cfg in configs:
            label = f"{cfg.name} ({PROVIDER_LABELS.get(cfg.provider, cfg.provider)})"
            self.active_combo.addItem(label, cfg.id)
            if cfg.id == active_id:
                self.active_combo.setCurrentIndex(self.active_combo.count() - 1)
                matched = True

        if not matched and configs:
            self._config_manager.config.providers.active = configs[0].id
            self.active_combo.setCurrentIndex(0)
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
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, card)
            self._cards.append(card)

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
        self._refresh_active_combo()

    def _add_card(self, cfg: ApiConfig) -> None:
        card = ConfigCard(cfg)
        card.delete_btn.clicked.connect(lambda checked, c=card: self._remove_card(c))
        self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, card)
        self._cards.append(card)
        self._refresh_active_combo()

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
            QMessageBox.warning(
                self, "同步失败",
                f"预设同步出错：{error_msg}\n将使用内置预设模板。",
            )
        elif cached:
            count = len(load_presets())
            QMessageBox.information(
                self, "同步完成",
                f"成功同步 {n} 个文件。\n当前共 {count} 个预设模板可用。",
            )
        else:
            QMessageBox.warning(
                self, "同步失败",
                "无法下载预设文件，请检查网络连接和代理设置。\n"
                "将使用内置预设模板。",
            )

    def _save_config(self) -> None:
        cfg = self._config_manager.config

        new_configs = [card.get_config() for card in self._cards]
        cfg.providers.configurations = new_configs

        if self.active_combo.currentData():
            cfg.providers.active = self.active_combo.currentData()
        elif new_configs:
            cfg.providers.active = new_configs[0].id

        self._config_manager.save_config()
        logger.info("Configuration saved: {} configs", len(new_configs))
        QMessageBox.information(self, "保存成功", "API 配置已保存。")
        self.accept()

    def _reset_config(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要恢复默认配置吗？\n\n这将删除所有自定义配置并恢复默认设置。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
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
        self._refresh_active_combo()

        logger.info("Configuration reset to defaults")
        QMessageBox.information(self, "重置完成", "配置已恢复为默认值。请重新配置 API Key。")

    def _is_dark_mode(self) -> bool:
        hints = QApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark
        app = QApplication.instance()
        if app:
            return app.palette().color(Qt.ColorRole.Window).lightness() < 128
        return False

    def _apply_style(self) -> None:
        dark = self._is_dark_mode()

        c = {
            "headerBg": "#2c2c2e" if dark else "#f8fafc",
            "headerBorder": "#3a3a3c" if dark else "#e2e8f0",
            "titleFg": "#e5e5e7" if dark else "#0f172a",
            "subtitleFg": "#98989d" if dark else "#64748b",
            "activeFg": "#e5e5e7" if dark else "#1e293b",
            "footerBg": "#2c2c2e" if dark else "#f8fafc",
            "footerBorder": "#3a3a3c" if dark else "#e2e8f0",
            "cardBg": "#323234" if dark else "#ffffff",
            "cardBorder": "#3a3a3c" if dark else "#e2e8f0",
            "primaryBtnBg": "#0a84ff" if dark else "#2563eb",
            "primaryBtnFg": "#ffffff",
            "primaryBtnHover": "#409cff" if dark else "#1d4ed8",
            "primaryBtnPressed": "#0066cc" if dark else "#1e40af",
            "secondaryBtnBg": "#3a3a3c" if dark else "#ffffff",
            "secondaryBtnFg": "#e5e5e7" if dark else "#374151",
            "secondaryBtnBorder": "#48484a" if dark else "#d1d5db",
            "secondaryBtnHoverBg": "#48484a" if dark else "#f9fafb",
            "secondaryBtnHoverBorder": "#545456" if dark else "#9ca3af",
            "resetFg": "#8e8e93" if dark else "#6b7280",
            "resetHoverFg": "#ff453a" if dark else "#dc2626",
            "testFg": "#0a84ff" if dark else "#2563eb",
            "testBorder": "#0a84ff" if dark else "#2563eb",
            "testHoverBg": "#1a3a5c" if dark else "#eff6ff",
            "testDisabledFg": "#48484a" if dark else "#cbd5e1",
            "testDisabledBorder": "#3a3a3c" if dark else "#e2e8f0",
            "deleteFg": "#8e8e93" if dark else "#94a3b8",
            "deleteHoverFg": "#ff453a" if dark else "#ef4444",
            "deleteHoverBg": "#3a1a1a" if dark else "#fef2f2",
            "inputBorder": "#48484a" if dark else "#d1d5db",
            "inputFocusBorder": "#0a84ff" if dark else "#2563eb",
            "inputBg": "#1c1c1e" if dark else "#ffffff",
            "inputFg": "#e5e5e7" if dark else "#1e293b",
            "inputDisabledBg": "#2c2c2e" if dark else "#f1f5f9",
            "inputDisabledFg": "#636366" if dark else "#94a3b8",
            "checkFg": "#e5e5e7" if dark else "#374151",
            "warningFg": "#ff453a" if dark else "#dc2626",
            "warningBg": "#3a1a1a" if dark else "#fef2f2",
            "warningBorder": "#6b2121" if dark else "#fecaca",
            "bodyBg": "#1c1c1e" if dark else "#ffffff",
            "categoryFg": "#98989d" if dark else "#64748b",
            "presetBtnBg": "#323234" if dark else "#f8fafc",
            "presetBtnFg": "#e5e5e7" if dark else "#334155",
            "presetBtnBorder": "#3a3a3c" if dark else "#e2e8f0",
            "presetBtnHoverBg": "#3a3a3c" if dark else "#f1f5f9",
            "addBtnFg": "#0a84ff" if dark else "#2563eb",
            "addBtnBorder": "#0a84ff" if dark else "#2563eb",
            "addBtnHoverBg": "#1a3a5c" if dark else "#eff6ff",
            "syncBtnFg": "#30d158" if dark else "#059669",
            "syncBtnBorder": "#30d158" if dark else "#059669",
            "syncBtnHoverBg": "#1a3a1a" if dark else "#ecfdf5",
        }

        self.setStyleSheet(f"""
            ConfigDialog {{
                background-color: {c["bodyBg"]};
            }}
            #dialogHeader {{
                background-color: {c["headerBg"]};
                border-bottom: 1px solid {c["headerBorder"]};
            }}
            #dialogTitle {{
                font-size: 20px;
                font-weight: 600;
                color: {c["titleFg"]};
            }}
            #dialogSubtitle {{
                font-size: 13px;
                color: {c["subtitleFg"]};
                margin-top: 4px;
            }}
            #apiWarning {{
                font-size: 12px;
                color: {c["warningFg"]};
                padding: 6px 10px;
                background-color: {c["warningBg"]};
                border: 1px solid {c["warningBorder"]};
                border-radius: 6px;
                margin-top: 8px;
            }}
            #activeLabel {{
                font-size: 13px;
                font-weight: 600;
                color: {c["activeFg"]};
            }}
            #dialogFooter {{
                background-color: {c["footerBg"]};
                border-top: 1px solid {c["footerBorder"]};
            }}
            #providerCard {{
                background-color: {c["cardBg"]};
                border: 1px solid {c["cardBorder"]};
                border-radius: 8px;
            }}
            #categoryLabel {{
                font-size: 12px;
                font-weight: 600;
                color: {c["categoryFg"]};
                text-transform: uppercase;
                margin-top: 4px;
            }}
            #saveBtn {{
                background-color: {c["primaryBtnBg"]};
                color: {c["primaryBtnFg"]};
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: 600;
                font-size: 13px;
            }}
            #saveBtn:hover {{ background-color: {c["primaryBtnHover"]}; }}
            #saveBtn:pressed {{ background-color: {c["primaryBtnPressed"]}; }}
            #cancelBtn {{
                background-color: {c["secondaryBtnBg"]};
                color: {c["secondaryBtnFg"]};
                border: 1px solid {c["secondaryBtnBorder"]};
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
            }}
            #cancelBtn:hover {{
                background-color: {c["secondaryBtnHoverBg"]};
                border-color: {c["secondaryBtnHoverBorder"]};
            }}
            #resetBtn {{
                background-color: transparent;
                color: {c["resetFg"]};
                border: none;
                padding: 8px 16px;
                font-size: 13px;
            }}
            #resetBtn:hover {{ color: {c["resetHoverFg"]}; text-decoration: underline; }}
            #testBtn {{
                background-color: transparent;
                color: {c["testFg"]};
                border: 1px solid {c["testBorder"]};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }}
            #testBtn:hover {{ background-color: {c["testHoverBg"]}; }}
            #testBtn:disabled {{
                color: {c["testDisabledFg"]};
                border-color: {c["testDisabledBorder"]};
            }}
            #deleteBtn {{
                background-color: transparent;
                color: {c["deleteFg"]};
                border: 1px solid transparent;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }}
            #deleteBtn:hover {{
                color: {c["deleteHoverFg"]};
                background-color: {c["deleteHoverBg"]};
                border-color: {c["deleteHoverFg"]};
            }}
            #addBtn {{
                background-color: transparent;
                color: {c["addBtnFg"]};
                border: 1px dashed {c["addBtnBorder"]};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }}
            #addBtn:hover {{ background-color: {c["addBtnHoverBg"]}; }}
            #syncBtn {{
                background-color: transparent;
                color: {c["syncBtnFg"]};
                border: 1px solid {c["syncBtnBorder"]};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }}
            #syncBtn:hover {{ background-color: {c["syncBtnHoverBg"]}; }}
            #presetBtn {{
                background-color: {c["presetBtnBg"]};
                color: {c["presetBtnFg"]};
                border: 1px solid {c["presetBtnBorder"]};
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 13px;
                text-align: left;
            }}
            #presetBtn:hover {{ background-color: {c["presetBtnHoverBg"]}; }}
            #blankBtn {{
                background-color: transparent;
                color: {c["subtitleFg"]};
                border: 1px dashed {c["inputBorder"]};
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }}
            #blankBtn:hover {{
                color: {c["primaryBtnBg"]};
                border-color: {c["primaryBtnBg"]};
            }}
            QLineEdit {{
                border: 1px solid {c["inputBorder"]};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                background-color: {c["inputBg"]};
                color: {c["inputFg"]};
            }}
            QLineEdit:focus {{ border-color: {c["inputFocusBorder"]}; }}
            QLineEdit:disabled {{
                background-color: {c["inputDisabledBg"]};
                color: {c["inputDisabledFg"]};
            }}
            QCheckBox {{ font-size: 13px; color: {c["checkFg"]}; }}
            QComboBox {{
                border: 1px solid {c["inputBorder"]};
                border-radius: 4px;
                padding: 6px 10px;
                padding-right: 28px;
                font-size: 13px;
                background-color: {c["inputBg"]};
                color: {c["inputFg"]};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                width: 8px;
                height: 8px;
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {c["subtitleFg"]};
            }}
            QComboBox::down-arrow:hover {{
                border-top-color: {c["inputFg"]};
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid {c["inputBorder"]};
                border-radius: 4px;
                background-color: {c["inputBg"]};
                color: {c["inputFg"]};
                selection-background-color: {c["primaryBtnBg"]};
                selection-color: {c["primaryBtnFg"]};
                padding: 4px;
            }}
            QScrollArea {{ background-color: transparent; }}
        """)

        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            try:
                hints.colorSchemeChanged.disconnect(self._apply_style)
            except Exception:
                pass
            hints.colorSchemeChanged.connect(self._apply_style)
