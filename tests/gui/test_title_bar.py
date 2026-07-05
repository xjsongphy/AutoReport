from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMainWindow

from autoreport.gui.title_bar import TitleBar


def test_title_bar_keeps_right_gap_draggable(qtbot) -> None:
    window = QMainWindow()
    window.resize(1200, 800)

    title_bar = TitleBar(window)
    qtbot.addWidget(title_bar)

    menu_bar = title_bar.get_menu_bar()
    menu_bar.addMenu("File")
    menu_bar.addMenu("Edit")
    menu_bar.addMenu("View")
    menu_bar.addMenu("Help")

    title_bar.resize(window.width(), title_bar.height())
    title_bar.show()
    qtbot.waitExposed(title_bar)
    qtbot.wait(50)

    controls_left = title_bar._controls_widget.geometry().left()
    menu_right = menu_bar.geometry().right()

    assert menu_right < controls_left - 1

    gap_x = (menu_right + controls_left) // 2
    gap_pos = QPoint(gap_x, title_bar.rect().center().y())
    assert title_bar._can_start_drag_at(gap_pos)
