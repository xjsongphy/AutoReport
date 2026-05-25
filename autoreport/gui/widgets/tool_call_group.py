"""Tool call group matching the chat timeline tool-call style."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


@dataclass
class ToolCall:
    name: str
    arguments: dict
    success: bool | None
    duration_ms: int
    result: Any | None = None
    error: str | None = None
    summary: str | None = None
    elapsed_seconds: int = 0
    file_names: list[str] = field(default_factory=list)


class _ClickableHeaderWidget(QWidget):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):  # noqa: N802
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def click(self) -> None:
        self.clicked.emit()


class ToolCallGroup(QWidget):
    """Tool calls in a compact summary row."""

    @staticmethod
    def _display_name(name: str) -> str:
        return name.replace("_", " ").replace("/", " ").title()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._calls: list[ToolCall] = []
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick_running)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 4, 16, 4)
        layout.setSpacing(0)

        self._header_btn = _ClickableHeaderWidget()
        self._header_btn.setObjectName("toolCallHeader")
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.clicked.connect(lambda: None)
        header_layout = QHBoxLayout(self._header_btn)
        header_layout.setContentsMargins(0, 2, 0, 2)
        header_layout.setSpacing(8)

        self._dot = QLabel()
        self._dot.setObjectName("toolCallDot")
        self._dot.setFixedSize(7, 7)
        self._dot.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header_layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._header_text = QLabel()
        self._header_text.setObjectName("toolCallHeaderText")
        self._header_text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._header_text.setWordWrap(True)
        self._header_text.setTextFormat(Qt.TextFormat.RichText)
        self._header_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._header_text.setMinimumWidth(0)
        header_layout.addWidget(self._header_text, 1)
        layout.addWidget(self._header_btn)

    def add_tool_call(
        self,
        name: str,
        arguments: dict,
        success: bool | None,
        duration_ms: int = 0,
        result: Any = None,
        error: str | None = None,
        summary: str | None = None,
    ) -> None:
        self._calls.append(ToolCall(
            name=name,
            arguments=arguments,
            success=success,
            duration_ms=duration_ms,
            result=result,
            error=error,
            summary=summary,
            elapsed_seconds=0,
            file_names=self._extract_file_names(arguments),
        ))
        self._update_display()

    def complete_tool_call(
        self,
        name: str,
        result: Any = None,
        error: str | None = None,
        duration_ms: int = 100,
        summary: str | None = None,
    ) -> None:
        for call in reversed(self._calls):
            if call.name == name and call.success is None:
                call.success = error is None
                call.duration_ms = duration_ms
                call.result = result if error is None else None
                call.error = error
                if summary is not None:
                    call.summary = summary
                self._update_display()
                return

        self.add_tool_call(
            name=name,
            arguments={},
            success=error is None,
            duration_ms=duration_ms,
            result=result if error is None else None,
            error=error,
            summary=summary,
        )

    def can_merge_with_last(self, name: str) -> bool:
        if not self._calls:
            return False
        return self._calls[-1].name == name

    def _tick_running(self) -> None:
        dirty = False
        for call in self._calls:
            if call.success is None:
                call.elapsed_seconds += 1
                dirty = True
        if dirty:
            self._update_display()
        else:
            self._tick_timer.stop()

    def _status_dot_color(self, success: bool | None) -> str:
        if success is None:
            return "#3B82F6"
        return "#22C55E" if success else "#EF4444"

    def _timer_text(self, call: ToolCall) -> str:
        if call.success is None:
            return f"{call.elapsed_seconds}s"
        return ""

    def _extract_file_names(self, arguments: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for key in ("path", "file_path", "output_path"):
            val = arguments.get(key)
            if isinstance(val, str) and val.strip():
                names.append(Path(val).name)
        multi = arguments.get("file_paths")
        if isinstance(multi, list):
            for p in multi:
                if isinstance(p, str) and p.strip():
                    names.append(Path(p).name)
        return names

    def _header_text_for_call(self, call: ToolCall) -> str:
        if call.summary:
            return call.summary
        sep = "&nbsp;&nbsp;"
        if call.name == "read_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Read</b>{sep}{files}".strip()
        if call.name == "list_dir":
            files = " ".join(call.file_names) if call.file_names else "."
            return f"<b>List</b>{sep}{files}".strip()
        if call.name == "parse_pdf":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Parse</b>{sep}{files}".strip()
        if call.name == "write_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Write</b>{sep}{files}".strip()
        if call.name == "edit_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Edit</b>{sep}{files}".strip()
        if call.name == "delete_file":
            files = " ".join(call.file_names) if call.file_names else ""
            return f"<b>Delete</b>{sep}{files}".strip()
        if call.name == "bash":
            desc = str(call.arguments.get("command_description") or "").strip()
            if desc:
                desc = desc[0].upper() + desc[1:]
            return f"<b>Bash</b>{sep}{desc}".strip()
        return f"<b>{self._display_name(call.name)}</b>"

    def _update_display(self) -> None:
        if not self._calls:
            return

        if len(self._calls) == 1:
            call = self._calls[0]
            timer = self._timer_text(call)
            text = f"&nbsp;&nbsp;{self._header_text_for_call(call)}"
            if timer:
                text += f"&nbsp;&nbsp;{timer}"
            self._header_text.setText(text)
            dot_color = self._status_dot_color(call.success)
        else:
            running = any(c.success is None for c in self._calls)
            failed = any(c.success is False for c in self._calls)
            success = not running and not failed
            same_name = len({c.name for c in self._calls}) == 1
            if same_name and self._calls[0].name in {"read_file", "list_dir", "parse_pdf", "write_file", "edit_file", "delete_file"}:
                tool = self._calls[0].name
                files: list[str] = []
                for c in self._calls:
                    files.extend(c.file_names)
                file_text = " ".join(files).strip()
                label = {
                    "read_file": "Read",
                    "list_dir": "List",
                    "parse_pdf": "Parse",
                    "write_file": "Write",
                    "edit_file": "Edit",
                    "delete_file": "Delete",
                }[tool]
                joined = f"<b>{label}</b>&nbsp;&nbsp;{file_text}".strip()
            else:
                joined = " ".join(self._header_text_for_call(c) for c in self._calls)
            timer = ""
            if running:
                timer = f"&nbsp;&nbsp;{max((c.elapsed_seconds for c in self._calls if c.success is None), default=0)}s"
            self._header_text.setText(f"&nbsp;&nbsp;{joined}{timer}")
            dot_color = self._status_dot_color(None if running else success)

        self._dot.setStyleSheet(f"background:{dot_color}; border-radius: 3px;")

        if any(c.success is None for c in self._calls):
            if not self._tick_timer.isActive():
                self._tick_timer.start()
        else:
            self._tick_timer.stop()

    def is_expanded(self) -> bool:
        return False

    def get_summary_text(self) -> str:
        return self._header_text.text()
