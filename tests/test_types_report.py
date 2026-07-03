from autoreport.interfaces.types import (
    AgentType, MessageType, ReportMessage, SystemNotice, TaskStatus,
)


def test_task_status_has_blocked():
    assert TaskStatus.BLOCKED.value == "blocked"


def test_report_message_fields():
    msg = ReportMessage(
        agent_type=AgentType.PLOTTING,
        task_id="tk001",
        report_type="missing_data",
        content="need data.csv",
    )
    assert msg.report_type == "missing_data"
    assert msg.task_id == "tk001"
    assert msg.type == MessageType.REPORT


def test_system_notice_fields():
    msg = SystemNotice(agent_type=AgentType.MAIN, content="waiting on blocked task")
    assert msg.type == MessageType.SYSTEM_NOTICE
    assert msg.content == "waiting on blocked task"
