"""Configuration dialog for API providers with modern card-based UI."""

import os

from loguru import logger
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
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
from ..config.schema import ProviderConfig

PROVIDER_META = {
    "anthropic": {
        "name": "Anthropic",
        "desc": "Claude 系列模型 (Sonnet, Opus, Haiku)",
        "base_placeholder": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-20250514",
        "env_var": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "name": "OpenAI",
        "desc": "GPT 系列模型 (GPT-4o, GPT-4.1)",
        "base_placeholder": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "env_var": "OPENAI_API_KEY",
    },
    "google": {
        "name": "Google",
        "desc": "Gemini 系列模型",
        "base_placeholder": "",
        "default_model": "gemini-2.0-flash-exp",
        "env_var": "GOOGLE_API_KEY",
    },
    "deepseek": {
        "name": "DeepSeek",
        "desc": "DeepSeek Chat 模型",
        "base_placeholder": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "env_var": "DEEPSEEK_API_KEY",
    },
    "openrouter": {
        "name": "OpenRouter",
        "desc": "多模型聚合平台",
        "base_placeholder": "https://openrouter.ai/api/v1",
        "default_model": "",
        "env_var": "OPENROUTER_API_KEY",
    },
    "groq": {
        "name": "Groq",
        "desc": "高速推理 (LPU 加速)",
        "base_placeholder": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "env_var": "GROQ_API_KEY",
    },
    "custom": {
        "name": "自定义",
        "desc": "兼容 OpenAI API 的自建服务 (vLLM, Ollama 等)",
        "base_placeholder": "http://localhost:11434/v1",
        "default_model": "",
        "env_var": None,
    },
}


class ProviderCard(QFrame):
    """Card widget for a single provider configuration."""

    def __init__(self, provider_id: str, config: ProviderConfig, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id
        self._meta = PROVIDER_META[provider_id]
        self._setup_ui(config)

    def _setup_ui(self, config: ProviderConfig) -> None:
        self.setObjectName("providerCard")
        self.setFrameStyle(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        # Header: name + enabled toggle
        header = QHBoxLayout()
        header.setSpacing(8)

        name_label = QLabel(self._meta["name"])
        name_label.setObjectName("providerName")
        header.addWidget(name_label)

        desc_label = QLabel(self._meta["desc"])
        desc_label.setObjectName("providerDesc")
        header.addWidget(desc_label, 1)

        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(config.enabled)
        self.enabled_check.toggled.connect(self._on_enabled_toggled)
        header.addWidget(self.enabled_check)

        layout.addLayout(header)

        # Body: API Key, Base URL, Default Model
        body = QVBoxLayout()
        body.setSpacing(8)

        # API Key row
        key_layout = QHBoxLayout()
        key_layout.setSpacing(6)

        key_label = QLabel("API Key")
        key_label.setFixedWidth(80)
        key_layout.addWidget(key_label)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setText(config.api_key or "")
        self.key_input.setPlaceholderText("sk-...")
        key_layout.addWidget(self.key_input, 1)

        # Show/hide toggle
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setFixedWidth(32)
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setToolTip("显示/隐藏 API Key")
        self.show_key_btn.toggled.connect(self._toggle_key_visibility)
        key_layout.addWidget(self.show_key_btn)

        # Env var indicator
        env_var = self._meta.get("env_var")
        if env_var and os.environ.get(env_var):
            env_label = QLabel("环境变量")
            env_label.setObjectName("envIndicator")
            env_label.setToolTip(f"已通过 {env_var} 环境变量设置")
            key_layout.addWidget(env_label)

        body.addLayout(key_layout)

        # Base URL row
        url_layout = QHBoxLayout()
        url_layout.setSpacing(6)

        url_label = QLabel("Base URL")
        url_label.setFixedWidth(80)
        url_layout.addWidget(url_label)

        self.base_url_input = QLineEdit()
        self.base_url_input.setText(config.api_base or "")
        placeholder = self._meta["base_placeholder"]
        self.base_url_input.setPlaceholderText(placeholder)
        url_layout.addWidget(self.base_url_input, 1)

        body.addLayout(url_layout)

        # Default Model row
        model_layout = QHBoxLayout()
        model_layout.setSpacing(6)

        model_label = QLabel("默认模型")
        model_label.setFixedWidth(80)
        model_layout.addWidget(model_label)

        self.model_input = QLineEdit()
        self.model_input.setText(config.default_model or "")
        default_model = self._meta["default_model"]
        self.model_input.setPlaceholderText(f"例如: {default_model}" if default_model else "例如: my-model")
        model_layout.addWidget(self.model_input, 1)

        body.addLayout(model_layout)

        layout.addLayout(body)

        # Footer: test connection button
        footer = QHBoxLayout()
        footer.addStretch()

        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("testBtn")
        self.test_btn.clicked.connect(self._test_connection)
        footer.addWidget(self.test_btn)

        layout.addLayout(footer)

        # Apply enabled state
        self._on_enabled_toggled(config.enabled)

    def _toggle_key_visibility(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.key_input.setEchoMode(mode)

    def _on_enabled_toggled(self, enabled: bool) -> None:
        self.key_input.setEnabled(enabled)
        self.base_url_input.setEnabled(enabled)
        self.model_input.setEnabled(enabled)
        self.test_btn.setEnabled(enabled)
        self.show_key_btn.setEnabled(enabled)

    def _test_connection(self) -> None:
        api_key = self.key_input.text().strip() or os.environ.get(
            self._meta.get("env_var", "")
        )
        if not api_key:
            QMessageBox.warning(
                self,
                "测试失败",
                f"{self._meta['name']} 未配置 API Key。",
            )
            return

        QMessageBox.information(
            self,
            "测试结果",
            f"{self._meta['name']} API Key 已配置（连接测试功能待实现）。",
        )

    def get_config(self) -> ProviderConfig:
        return ProviderConfig(
            enabled=self.enabled_check.isChecked(),
            api_key=self.key_input.text().strip() or None,
            api_base=self.base_url_input.text().strip() or None,
            default_model=self.model_input.text().strip() or None,
        )


class ConfigDialog(QDialog):
    """Configuration dialog for API providers."""

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self._config_manager = config_manager
        self._cards: dict[str, ProviderCard] = {}
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        self.setWindowTitle("API 配置")
        self.setMinimumSize(560, 500)
        self.resize(600, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("dialogHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 20, 24, 16)

        title = QLabel("API 配置")
        title.setObjectName("dialogTitle")
        header_layout.addWidget(title)

        subtitle = QLabel(
            "配置 LLM 服务商。API Key 也可通过环境变量设置\n"
            "(ANTHROPIC_API_KEY, OPENAI_API_KEY 等)，环境变量优先级更高。"
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)

        root.addWidget(header)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(20, 8, 20, 8)
        scroll_layout.setSpacing(12)

        config = self._config_manager.config
        providers = [
            "anthropic",
            "openai",
            "google",
            "deepseek",
            "openrouter",
            "groq",
            "custom",
        ]

        for pid in providers:
            provider_config = getattr(config.providers, pid)
            card = ProviderCard(pid, provider_config)
            scroll_layout.addWidget(card)
            self._cards[pid] = card

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        # Footer buttons
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

    def _is_dark_mode(self) -> bool:
        """Detect system dark mode via Qt 6.5+ colorScheme API."""
        hints = QApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark
        # Fallback for Qt < 6.5: check palette lightness
        app = QApplication.instance()
        if app:
            return app.palette().color(Qt.ColorRole.Window).lightness() < 128
        return False

    def _apply_style(self) -> None:
        dark = self._is_dark_mode()

        # Color tokens — light (Slate) / dark (neutral gray, macOS style)
        c = {
            "headerBg": "#2c2c2e" if dark else "#f8fafc",
            "headerBorder": "#3a3a3c" if dark else "#e2e8f0",
            "titleFg": "#e5e5e7" if dark else "#0f172a",
            "subtitleFg": "#98989d" if dark else "#64748b",
            "footerBg": "#2c2c2e" if dark else "#f8fafc",
            "footerBorder": "#3a3a3c" if dark else "#e2e8f0",
            "cardBg": "#323234" if dark else "#ffffff",
            "cardBorder": "#3a3a3c" if dark else "#e2e8f0",
            "nameFg": "#e5e5e7" if dark else "#1e293b",
            "descFg": "#8e8e93" if dark else "#94a3b8",
            "envFg": "#30d158" if dark else "#059669",
            "envBg": "#1a3a1a" if dark else "#d1fae5",
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
            "inputBorder": "#48484a" if dark else "#d1d5db",
            "inputFocusBorder": "#0a84ff" if dark else "#2563eb",
            "inputBg": "#1c1c1e" if dark else "#ffffff",
            "inputFg": "#e5e5e7" if dark else "#1e293b",
            "inputDisabledBg": "#2c2c2e" if dark else "#f1f5f9",
            "inputDisabledFg": "#636366" if dark else "#94a3b8",
            "checkFg": "#e5e5e7" if dark else "#374151",
            "bodyBg": "#1c1c1e" if dark else "#ffffff",
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
            #dialogFooter {{
                background-color: {c["footerBg"]};
                border-top: 1px solid {c["footerBorder"]};
            }}
            #providerCard {{
                background-color: {c["cardBg"]};
                border: 1px solid {c["cardBorder"]};
                border-radius: 8px;
            }}
            #providerName {{
                font-size: 15px;
                font-weight: 600;
                color: {c["nameFg"]};
            }}
            #providerDesc {{
                font-size: 12px;
                color: {c["descFg"]};
            }}
            #envIndicator {{
                font-size: 11px;
                color: {c["envFg"]};
                background-color: {c["envBg"]};
                border-radius: 4px;
                padding: 2px 6px;
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
            #saveBtn:hover {{
                background-color: {c["primaryBtnHover"]};
            }}
            #saveBtn:pressed {{
                background-color: {c["primaryBtnPressed"]};
            }}
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
            #resetBtn:hover {{
                color: {c["resetHoverFg"]};
                text-decoration: underline;
            }}
            #testBtn {{
                background-color: transparent;
                color: {c["testFg"]};
                border: 1px solid {c["testBorder"]};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }}
            #testBtn:hover {{
                background-color: {c["testHoverBg"]};
            }}
            #testBtn:disabled {{
                color: {c["testDisabledFg"]};
                border-color: {c["testDisabledBorder"]};
            }}
            QLineEdit {{
                border: 1px solid {c["inputBorder"]};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                background-color: {c["inputBg"]};
                color: {c["inputFg"]};
            }}
            QLineEdit:focus {{
                border-color: {c["inputFocusBorder"]};
            }}
            QLineEdit:disabled {{
                background-color: {c["inputDisabledBg"]};
                color: {c["inputDisabledFg"]};
            }}
            QCheckBox {{
                font-size: 13px;
                color: {c["checkFg"]};
            }}
            QScrollArea {{
                background-color: transparent;
            }}
        """)

        # Subscribe to theme changes for live switching
        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            try:
                hints.colorSchemeChanged.disconnect(self._apply_style)
            except Exception:
                pass
            hints.colorSchemeChanged.connect(self._apply_style)

    def _save_config(self) -> None:
        cfg = self._config_manager.config

        for pid, card in self._cards.items():
            provider_config = card.get_config()
            setattr(cfg.providers, pid, provider_config)

        self._config_manager.save_config()
        logger.info("Configuration saved")
        QMessageBox.information(self, "保存成功", "API 配置已保存。")
        self.accept()

    def _reset_config(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要恢复默认配置吗？\n\n这将清除所有 API Key，禁用所有服务商，并恢复默认设置。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self._config_manager.reset_config()
        default_cfg = self._config_manager.config

        for pid, card in self._cards.items():
            default_provider = getattr(default_cfg.providers, pid)
            card.enabled_check.setChecked(default_provider.enabled)
            card.key_input.clear()
            card.base_url_input.clear()
            card.model_input.clear()

        logger.info("Configuration reset to defaults")
        QMessageBox.information(
            self, "重置完成", "配置已恢复为默认值。请重新配置 API Key。"
        )
