"""Tests for API configuration dialog widgets."""

from autoreport.config.schema import ApiConfig
from autoreport.gui.config_dialog import ConfigCard


def test_config_card_action_column_uses_test_button_width(qtbot) -> None:
    card = ConfigCard(
        ApiConfig(
            name="DeepSeek",
            provider="anthropic",
            api_key="sk-test",
            api_base="https://api.deepseek.com/anthropic",
            default_model="deepseek-v4-flash",
        )
    )
    qtbot.addWidget(card)
    card.resize(1180, 420)
    card.show()
    qtbot.waitExposed(card)
    qtbot.wait(20)

    action_buttons = [card.delete_btn, card.show_key_btn, card.test_btn]
    widths = [button.width() for button in action_buttons]
    right_edges = [
        button.mapTo(card, button.rect().topRight()).x()
        for button in action_buttons
    ]

    assert widths[0] == widths[2]
    assert widths[1] == widths[2]
    assert right_edges[0] == right_edges[2]
    assert right_edges[1] == right_edges[2]
