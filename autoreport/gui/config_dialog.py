"""Configuration dialog for API keys."""

from loguru import logger
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ...config import ConfigManager


class ConfigDialog(QDialog):
    """Configuration dialog for API keys."""

    def __init__(self, config_manager: ConfigManager, parent=None):
        """Initialize config dialog.

        Args:
            config_manager: Configuration manager.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config_manager = config_manager
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        self.setWindowTitle("API 配置")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel(
            "请配置至少一个 API Provider。API 密钥将保存在配置文件中。\n"
            "你也可以通过环境变量配置（ANTHROPIC_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY）。"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Form layout for API keys
        form = QFormLayout()

        # Anthropic
        self.anthropic_key = QLineEdit()
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key.setText(self.config_manager.config.providers.anthropic.api_key or "")
        self.anthropic_key.setPlaceholderText("sk-ant-...")
        form.addRow("Anthropic API Key:", self.anthropic_key)

        # OpenAI
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key.setText(self.config_manager.config.providers.openai.api_key or "")
        self.openai_key.setPlaceholderText("sk-...")
        form.addRow("OpenAI API Key:", self.openai_key)

        # DeepSeek
        self.deepseek_key = QLineEdit()
        self.deepseek_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepseek_key.setText(self.config_manager.config.providers.deepseek.api_key or "")
        self.deepseek_key.setPlaceholderText("sk-...")
        form.addRow("DeepSeek API Key:", self.deepseek_key)

        # Model selection
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "anthropic/claude-sonnet-4.5",
            "anthropic/claude-opus-4.5",
            "openai/gpt-4o",
            "openai/gpt-4-turbo",
            "deepseek/deepseek-chat",
        ])
        # Set current model
        current_model = self.config_manager.config.agents.defaults.model
        index = self.model_combo.findText(current_model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        form.addRow("默认模型:", self.model_combo)

        layout.addLayout(form)

        # Buttons
        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)

        reset_button = QPushButton("重置配置")
        reset_button.setStyleSheet("color: red;")
        reset_button.clicked.connect(self._reset_config)
        button_layout.addWidget(reset_button)

        test_button = QPushButton("测试连接")
        test_button.clicked.connect(self._test_connection)
        button_layout.addWidget(test_button)

        button_layout.addStretch()

        save_button = QPushButton("保存")
        save_button.clicked.connect(self._save_config)
        button_layout.addWidget(save_button)

        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

    def _test_connection(self) -> None:
        """Test API connection."""
        # Check if at least one key is provided
        has_key = (
            self.anthropic_key.text().strip() or
            self.openai_key.text().strip() or
            self.deepseek_key.text().strip()
        )

        if not has_key:
            QMessageBox.warning(self, "测试失败", "请至少配置一个 API 密钥。")
            return

        # TODO: Implement actual connection test
        QMessageBox.information(
            self,
            "测试结果",
            "API 密钥已配置（连接测试功能待实现）。"
        )

    def _save_config(self) -> None:
        """Save configuration."""
        # Update config
        if self.anthropic_key.text().strip():
            self.config_manager.config.providers.anthropic.api_key = self.anthropic_key.text().strip()
        if self.openai_key.text().strip():
            self.config_manager.config.providers.openai.api_key = self.openai_key.text().strip()
        if self.deepseek_key.text().strip():
            self.config_manager.config.providers.deepseek.api_key = self.deepseek_key.text().strip()

        # Update model
        self.config_manager.config.agents.defaults.model = self.model_combo.currentText()

        # Save to file
        self.config_manager.save_config()

        logger.info("Configuration saved")

        QMessageBox.information(self, "保存成功", "配置已保存。")
        self.accept()

    def _reset_config(self) -> None:
        """Reset configuration to defaults."""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置所有配置吗？这将清除所有 API 密钥并恢复默认设置。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Reset configuration
            self.config_manager.reset_config()

            # Clear input fields
            self.anthropic_key.clear()
            self.openai_key.clear()
            self.deepseek_key.clear()

            # Reset model selection
            self.model_combo.setCurrentIndex(0)

            logger.info("Configuration reset to defaults")

            QMessageBox.information(
                self,
                "重置完成",
                "配置已重置为默认值。请重新配置 API 密钥。"
            )
