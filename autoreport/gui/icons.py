"""Agent icons from Tabler Icons (MIT License)."""

from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtSvg import QSvgRenderer


# Tabler Icons SVG data (24x24, stroke-width 1.5)
_SVG_ICONS: dict[str, str] = {
    "dashboard": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="2"/><path d="M6.4 20a9 9 0 1 1 11.2 0z"/></svg>',
    "chart-bar": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="12" width="6" height="8" rx="1"/><rect x="9" y="8" width="6" height="12" rx="1"/><rect x="15" y="4" width="6" height="16" rx="1"/><line x1="4" y1="20" x2="18" y2="20"/></svg>',
    "line-chart": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16"/><path d="M4 16l4-4 4 4 4-6 4 4"/></svg>',
    "pencil": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4"/><path d="M13.5 6.5l4 4"/></svg>',
    "file-text": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2z"/><line x1="9" y1="9" x2="10" y2="9"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>',
}

_AGENT_ICON_MAP: dict[str, str] = {
    "main": "dashboard",
    "data_analysis": "chart-bar",
    "plotting": "line-chart",
    "theory": "pencil",
    "report": "file-text",
}


def _svg_to_icon(svg_data: str, color: str = "#d4d4d4", size: int = 16) -> QIcon:
    """Convert SVG string to QIcon with specified color and size."""
    # Inject color into SVG
    colored_svg = svg_data.replace('stroke="currentColor"', f'stroke="{color}"')

    # Create QPixmap and render SVG
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    renderer = QSvgRenderer(QByteArray(colored_svg.encode()))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


_ICON_CACHE: dict[str, QIcon] = {}


def get_agent_icon(agent_type: str, color: str = "#d4d4d4", size: int = 16) -> QIcon:
    """Get QIcon for an agent type."""
    icon_name = _AGENT_ICON_MAP.get(agent_type, "dashboard")
    cache_key = f"{icon_name}_{color}_{size}"

    if cache_key not in _ICON_CACHE:
        svg_data = _SVG_ICONS[icon_name]
        _ICON_CACHE[cache_key] = _svg_to_icon(svg_data, color, size)

    return _ICON_CACHE[cache_key]
