"""File search popup widget for @ file references."""

from dataclasses import dataclass
from pathlib import Path
from typing import override

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QTextDocument
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)


@dataclass
class FileMatch:
    """File search result match."""

    path: Path
    score: int
    indices: list[int] | None = None


class FileSearchPopup(QWidget):
    """Popup widget for displaying file search results.

    Based on Codex's FileSearchPopup pattern adapted for PyQt6.
    """

    file_selected = pyqtSignal(Path)  # Emits selected file path
    cancelled = pyqtSignal()  # User cancelled (Esc)

    MAX_VISIBLE_ROWS = 10

    def __init__(self, parent=None):
        """Initialize file search popup.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._query = ""
        self._matches: list[FileMatch] = []
        self._selected_idx = 0

        self._setup_ui()
        self._setup_window_flags()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Status label (shows "loading..." or "no matches")
        self._status_label = QLabel()
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        # Results list
        self._list_widget = QListWidget()
        self._list_widget.setItemDelegate(HTMLDelegate())
        self._list_widget.setSpacing(2)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_widget.currentRowChanged.connect(self._on_current_row_changed)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list_widget)

        # Set fixed width for consistent display
        self.setFixedWidth(400)

    def _setup_window_flags(self) -> None:
        """Setup window flags for popup behavior."""
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def set_query(self, query: str, waiting: bool = True) -> None:
        """Set current search query.

        Args:
            query: Search query string.
            waiting: True if waiting for search results.
        """
        self._query = query
        self._selected_idx = 0

        if waiting:
            self._show_status("loading...")
        elif not self._matches:
            self._show_status("no matches")
        else:
            self._status_label.setVisible(False)
            self._populate_list()

    def set_matches(self, matches: list[FileMatch]) -> None:
        """Set search results.

        Args:
            matches: List of file matches.
        """
        self._matches = matches
        self._selected_idx = 0

        if not matches:
            self._show_status("no matches")
        else:
            self._status_label.setVisible(False)
            self._populate_list()

    def _show_status(self, text: str) -> None:
        """Show status message instead of list.

        Args:
            text: Status text to display.
        """
        self._list_widget.setVisible(False)
        self._status_label.setText(text)
        self._status_label.setVisible(True)

    def _populate_list(self) -> None:
        """Populate list widget with current matches."""
        self._list_widget.clear()
        self._list_widget.setVisible(True)

        for match in self._matches[: self.MAX_VISIBLE_ROWS]:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, match)

            # Format item text with highlighting
            text = self._format_match_text(match)
            item.setText(text)

            self._list_widget.addItem(item)

        # Set initial selection
        if self._list_widget.count() > 0:
            self._list_widget.setCurrentRow(0)

    def _format_match_text(self, match: FileMatch) -> str:
        """Format match text with highlighted search terms.

        Args:
            match: File match to format.

        Returns:
            HTML-formatted text with highlighting.
        """
        path_str = str(match.path)
        rel_path = path_str

        # If indices provided, highlight matched characters
        if match.indices:
            # Build HTML with highlighted characters
            highlighted = []
            for i, char in enumerate(path_str):
                if i in match.indices:
                    highlighted.append(f"<b>{char}</b>")
                else:
                    highlighted.append(char)
            rel_path = "".join(highlighted)

        # Show relative path if possible
        # For now, show filename with parent directory
        if len(path_str) > 50:
            # Truncate long paths
            parts = Path(path_str).parts
            if len(parts) > 3:
                rel_path = ".../" + "/".join(parts[-3:])
                if match.indices:
                    # Simplified highlighting for truncated paths
                    rel_path = rel_path

        return rel_path

    def move_up(self) -> None:
        """Move selection up."""
        if not self._list_widget.isVisible():
            return
        current = self._list_widget.currentRow()
        if current > 0:
            self._list_widget.setCurrentRow(current - 1)

    def move_down(self) -> None:
        """Move selection down."""
        if not self._list_widget.isVisible():
            return
        current = self._list_widget.currentRow()
        if current < self._list_widget.count() - 1:
            self._list_widget.setCurrentRow(current + 1)

    def select_current(self) -> None:
        """Select current item and emit signal."""
        if not self._list_widget.isVisible():
            return

        current_item = self._list_widget.currentItem()
        if current_item:
            match: FileMatch = current_item.data(Qt.ItemDataRole.UserRole)
            self.file_selected.emit(match.path)

    def cancel(self) -> None:
        """Cancel the popup."""
        self.cancelled.emit()

    def _on_current_row_changed(self, row: int) -> None:
        """Handle current row changed.

        Args:
            row: New current row index.
        """
        self._selected_idx = row

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle item double-click.

        Args:
            item: Clicked item.
        """
        self.select_current()

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press events.

        Args:
            event: Key event.
        """
        match event.key():
            case Qt.Key.Key_Up:
                self.move_up()
            case Qt.Key.Key_Down:
                self.move_down()
            case Qt.Key.Key_Enter | Qt.Key.Key_Return:
                self.select_current()
                return
            case Qt.Key.Key_Escape:
                self.cancel()
                return
            case _:
                # Pass other keys to parent
                super().keyPressEvent(event)

    def calculate_height(self) -> int:
        """Calculate required height based on content.

        Returns:
            Required height in pixels.
        """
        if self._status_label.isVisible():
            return 40

        row_count = min(len(self._matches), self.MAX_VISIBLE_ROWS)
        row_height = self._list_widget.sizeHintForRow(0) or 24
        return row_count * row_height + 20  # +20 for margins


class HTMLDelegate(QStyledItemDelegate):
    """Delegate for rendering HTML in list items."""

    @override
    def paint(self, painter, option, index):
        """Paint item with HTML rendering.

        Args:
            painter: QPainter instance.
            option: Style option.
            index: Model index.
        """
        item = index.model().data(index, Qt.ItemDataRole.UserRole)
        if item and isinstance(item, FileMatch):
            # Use custom painting for highlighted text
            option.text = ""
            super().paint(painter, option, index)

            # Draw text manually
            text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
            if text:
                document = QTextDocument()
                document.setHtml(text)
                document.setTextWidth(option.rect.width())

                painter.save()
                painter.translate(option.rect.topLeft())
                document.drawContents(painter)
                painter.restore()
        else:
            super().paint(painter, option, index)

    @override
    def sizeHint(self, option, index):
        """Calculate size hint for item.

        Args:
            option: Style option.
            index: Model index.

        Returns:
            Size hint.
        """
        item = index.model().data(index, Qt.ItemDataRole.UserRole)
        if item and isinstance(item, FileMatch):
            text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
            if text:
                document = QTextDocument()
                document.setHtml(text)
                document.setTextWidth(400)  # Match popup width
                return QSize(400, int(document.size().height()) + 4)
        return super().sizeHint(option, index)
