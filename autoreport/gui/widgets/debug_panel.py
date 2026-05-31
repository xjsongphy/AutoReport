"""Debug panel widget for displaying API request/response debug information."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..theme import get_theme_colors
from .ui_utils import ghost_button_qss, secondary_filled_button_qss


@dataclass
class DebugEntry:
    """Single debug entry for an API call."""

    timestamp: datetime
    model: str
    tokens_in: int
    tokens_out: int
    duration_ms: int
    status: str  # "success" or "error"
    error: Optional[str] = None


class DebugPanel(QWidget):
    """Collapsible debug panel showing API call summaries."""

    # Signal emitted when entries are added or cleared
    entries_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize debug panel."""
        super().__init__(parent)
        self._entries: list[DebugEntry] = []
        self._max_entries = 50
        self._is_collapsed = False

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with toggle
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 8, 8, 8)

        self._toggle_btn = QPushButton("▼")
        self._toggle_btn.setObjectName("debugToggleBtn")
        self._toggle_btn.setFixedWidth(30)
        self._toggle_btn.clicked.connect(self._toggle_collapsed)

        self._title_label = QLabel("🔍 API Debug (0 calls)")
        self._title_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))

        header_layout.addWidget(self._toggle_btn)
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        layout.addWidget(header)

        # Content area
        self._content_widget = QWidget(self)
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)

        # Scroll area for entries
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_area.setMaximumHeight(300)

        self._entries_widget = QWidget(self)
        self._entries_layout = QVBoxLayout(self._entries_widget)
        self._entries_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._entries_layout.setContentsMargins(0, 0, 0, 0)
        self._entries_layout.setSpacing(4)

        self._scroll_area.setWidget(self._entries_widget)
        content_layout.addWidget(self._scroll_area)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self._clear_btn = QPushButton("Clear All")
        self._clear_btn.setObjectName("debugClearBtn")
        self._clear_btn.clicked.connect(self.clear_all)

        self._export_btn = QPushButton("Export JSON")
        self._export_btn.setObjectName("debugExportBtn")
        self._export_btn.clicked.connect(self._export_json)

        button_layout.addWidget(self._clear_btn)
        button_layout.addWidget(self._export_btn)
        button_layout.addStretch()

        content_layout.addLayout(button_layout)
        layout.addWidget(self._content_widget)

        # Apply styling
        self._apply_styling()

    def _apply_styling(self):
        """Apply dark/light theme styling."""
        c = get_theme_colors()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {c["surface"]};
                border-bottom: 1px solid {c["border"]};
            }}
            QLabel {{
                color: {c["popup_fg"]};
            }}
            {ghost_button_qss(
                "#debugToggleBtn",
                padding="4px 6px",
                font_size=12,
                radius=c["radius_sm"],
            )}
            {secondary_filled_button_qss(
                "#debugClearBtn",
                radius=c["radius_sm"],
                padding="4px 12px",
                font_size=12,
            )}
            {secondary_filled_button_qss(
                "#debugExportBtn",
                radius=c["radius_sm"],
                padding="4px 12px",
                font_size=12,
            )}
            QPushButton#debugClearBtn:pressed,
            QPushButton#debugExportBtn:pressed {{
                background-color: {c["hover"]};
            }}
        """)

    def _toggle_collapsed(self):
        """Toggle collapsed state."""
        self._is_collapsed = not self._is_collapsed
        self._content_widget.setVisible(not self._is_collapsed)
        self._toggle_btn.setText("▶" if self._is_collapsed else "▼")

    def add_entry(
        self,
        timestamp: datetime,
        model: str,
        tokens_in: int,
        tokens_out: int,
        duration_ms: int,
        status: str,
        error: Optional[str] = None,
    ):
        """Add a debug entry, evicting oldest if max exceeded."""
        entry = DebugEntry(
            timestamp=timestamp,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            status=status,
            error=error,
        )

        # FIFO eviction
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries.pop(0)

        self._update_display()
        self.entries_changed.emit()

    def clear_all(self):
        """Clear all entries."""
        self._entries.clear()
        self._update_display()
        self.entries_changed.emit()

    def entry_count(self) -> int:
        """Return number of entries."""
        return len(self._entries)

    def get_summary_text(self) -> str:
        """Get summary text of all entries."""
        if not self._entries:
            return ""

        lines = []
        for entry in self._entries:
            ts = entry.timestamp.strftime("%H:%M:%S")
            status_symbol = "✓" if entry.status == "success" else "✗"
            lines.append(
                f"{ts} {status_symbol} {entry.model} | "
                f"In: {entry.tokens_in} | Out: {entry.tokens_out} | "
                f"Time: {entry.duration_ms}ms"
            )
            if entry.error:
                lines.append(f"  Error: {entry.error}")

        return "\n".join(lines)

    def _update_display(self):
        """Update the display with current entries."""
        # Update title
        self._title_label.setText(f"🔍 API Debug ({len(self._entries)} calls)")

        # Clear existing entries
        for i in reversed(range(self._entries_layout.count())):
            self._entries_layout.itemAt(i).widget().setParent(None)

        # Add entry widgets
        for entry in reversed(self._entries):  # Show newest first
            entry_widget = self._create_entry_widget(entry)
            self._entries_layout.addWidget(entry_widget)

    def _create_entry_widget(self, entry: DebugEntry) -> QFrame:
        """Create a widget for a single debug entry."""
        c = get_theme_colors()
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {c["bg"]};
                border: 1px solid {c["border"]};
                border-radius: {c["radius_sm"]};
                padding: 4px;
            }}
            QLabel {{
                color: {c["popup_fg"]};
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Main info line
        ts = entry.timestamp.strftime("%H:%M:%S")
        status_symbol = "✓" if entry.status == "success" else "✗"
        status_color = c["successFg"] if entry.status == "success" else c["status_error"]

        main_line = QLabel(
            f"{ts} <span style='color: {status_color};'>{status_symbol}</span> "
            f"<b>{entry.model}</b> | "
            f"In: {entry.tokens_in} | Out: {entry.tokens_out} | "
            f"Time: {entry.duration_ms}ms"
        )
        main_line.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(main_line)

        # Error line if present
        if entry.error:
            error_label = QLabel(f"Error: {entry.error}")
            error_label.setStyleSheet(f"color: {c['status_error']};")
            layout.addWidget(error_label)

        return frame

    def _export_json(self):
        """Export entries to JSON file."""
        if not self._entries:
            return

        # Get save path
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Debug Log", "debug_log.json", "JSON Files (*.json)"
        )

        if file_path:
            self.export_to_json(file_path)

    def export_to_json(self, file_path: str):
        """Export entries to JSON file at specified path."""
        export_data = []
        for entry in self._entries:
            entry_dict = asdict(entry)
            # Convert datetime to ISO format string
            entry_dict["timestamp"] = entry.timestamp.isoformat()
            export_data.append(entry_dict)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
