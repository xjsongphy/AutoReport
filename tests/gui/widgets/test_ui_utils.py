from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from autoreport.gui.widgets.ui_utils import NoWheelComboBox


def test_combo_popup_host_is_transparent_without_fill(qtbot) -> None:
    combo = NoWheelComboBox()
    qtbot.addWidget(combo)
    popup = QWidget()

    combo._style_popup_host(popup)

    assert popup.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is True
    assert popup.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground) is True
    assert popup.autoFillBackground() is False
    assert popup.styleSheet() == "background: transparent; border: none;"


def test_combo_popup_host_applies_rounded_mask(qtbot) -> None:
    combo = NoWheelComboBox()
    qtbot.addWidget(combo)
    popup = QWidget()
    popup.resize(200, 100)

    combo._apply_popup_mask(popup)

    assert popup.mask().isEmpty() is False


def test_combo_tracks_popup_open_state_for_chevron_direction(qtbot) -> None:
    combo = NoWheelComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["DeepSeek", "OpenAI"])
    combo.show()
    qtbot.waitExposed(combo)

    assert combo._popup_open is False

    combo.showPopup()
    qtbot.wait(20)

    assert combo._popup_open is True

    combo.hidePopup()
    qtbot.wait(20)

    assert combo._popup_open is False
