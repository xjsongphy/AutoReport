"""Agent icons from Tabler Icons (MIT License)."""

from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtSvg import QSvgRenderer


# Tabler Icons SVG data (24x24, stroke-width 1.5)
_SVG_ICONS: dict[str, str] = {
    "robot": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2"/><circle cx="12" cy="2.5" r=".8" fill="currentColor"/><rect x="5" y="6" width="14" height="11" rx="5"/><path d="M5 10h-1.2a1.3 1.3 0 0 0 0 2.6H5"/><path d="M19 10h1.2a1.3 1.3 0 0 1 0 2.6H19"/><rect x="7.5" y="8.5" width="9" height="5.5" rx="2.5" fill="currentColor" stroke="none"/><ellipse cx="10" cy="11.2" rx=".7" ry="1" fill="white" stroke="none"/><ellipse cx="14" cy="11.2" rx=".7" ry="1" fill="white" stroke="none"/><path d="M10 17v1"/><path d="M14 17v1"/></svg>',
    "chart-bar": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="12" width="6" height="8" rx="1"/><rect x="9" y="8" width="6" height="12" rx="1"/><rect x="15" y="4" width="6" height="16" rx="1"/><line x1="4" y1="20" x2="18" y2="20"/></svg>',
    "line-chart": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16"/><path d="M4 16l4-4 4 4 4-6 4 4"/></svg>',
    "pencil": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4"/><path d="M13.5 6.5l4 4"/></svg>',
    "file-text": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2z"/><line x1="9" y1="9" x2="10" y2="9"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>',
}

_AGENT_ICON_MAP: dict[str, str] = {
    "main": "robot",
    "data_analysis": "chart-bar",
    "plotting": "line-chart",
    "theory": "pencil",
    "report": "file-text",
}

# Agent icon colors
_AGENT_COLORS: dict[str, str] = {
    "main": "#0078d4",        # Blue
    "data_analysis": "#107c10",  # Green
    "plotting": "#8e44ad",    # Purple
    "theory": "#e67e22",      # Orange
    "report": "#5dade2",      # Light Blue
}


def _svg_to_icon(svg_data: str, color: str = "#d4d4d4", size: int = 16) -> QIcon:
    """Convert SVG string to QIcon with specified color and size."""
    # Inject color into SVG (both stroke and fill)
    colored_svg = svg_data.replace('stroke="currentColor"', f'stroke="{color}"')
    colored_svg = colored_svg.replace('fill="currentColor"', f'fill="{color}"')

    # Create QPixmap and render SVG
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    renderer = QSvgRenderer(QByteArray(colored_svg.encode()))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


_ICON_CACHE: dict[str, QIcon] = {}


def get_agent_icon(agent_type: str, color: str | None = None, size: int = 16) -> QIcon:
    """Get QIcon for an agent type.

    Args:
        agent_type: The agent type (main, data_analysis, plotting, theory, report)
        color: Optional color override. If None, uses agent's theme color.
        size: Icon size in pixels.
    """
    icon_name = _AGENT_ICON_MAP.get(agent_type, "robot")
    # Use agent's theme color if no override provided
    if color is None:
        color = _AGENT_COLORS.get(agent_type, "#0078d4")
    cache_key = f"{icon_name}_{color}_{size}"

    if cache_key not in _ICON_CACHE:
        svg_data = _SVG_ICONS[icon_name]
        _ICON_CACHE[cache_key] = _svg_to_icon(svg_data, color, size)

    return _ICON_CACHE[cache_key]
