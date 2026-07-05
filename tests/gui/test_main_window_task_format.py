"""Tests for manage_tasks result formatting in MainWindow."""

from autoreport.gui.main_window import MainWindow


def test_manage_tasks_format_omits_empty_sections():
    summary, detail, expandable = MainWindow._format_manage_tasks_result(
        None,
        {
            "status": "ok",
            "todolist": [
                {
                    "brief": "DATA_ANALYSIS: Process measurements",
                    "status": "pending",
                }
            ],
            "waitlist": [],
        },
        None,
    )

    assert summary == "<b>Task</b>\nTodo\n☐ DATA_ANALYSIS: Process measurements"
    assert detail is None
    assert expandable is False


def test_manage_tasks_format_omits_all_empty_task_sections():
    summary, detail, expandable = MainWindow._format_manage_tasks_result(
        None,
        {
            "status": "ok",
            "todolist": [],
            "waitlist": [],
        },
        None,
    )

    assert summary == "<b>Task</b>"
    assert detail is None
    assert expandable is False
