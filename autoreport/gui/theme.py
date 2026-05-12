"""Unified theme management for AutoReport GUI.

Provides centralized color definitions for dark/light modes,
following VSCode Copilot Chat design language.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


def is_dark_mode() -> bool:
    """Detect if system is in dark mode."""
    hints = QApplication.styleHints()
    return hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark


def get_theme_colors() -> dict[str, str]:
    """Get unified theme colors for current mode.

    Returns:
        Dictionary of color name -> hex value.
        Based on VSCode Dark Modern / Light Modern palettes.
    """
    dark = is_dark_mode()

    # === Base Colors ===
    bg = "#1f1f1f" if dark else "#ffffff"
    surface = "#181818" if dark else "#f3f3f3"
    border = "#2b2b2b" if dark else "#e0e0e0"
    fg = "#cccccc" if dark else "#616161"
    muted = "#737373" if dark else "#9e9e9e"

    # Pre-define focus value before using in aliases
    focus = "#0078d4" if dark else "#0090ff"

    return {
        # === Layout ===
        "bg": bg,  # Main content area
        "surface": surface,  # Sidebar/chrome (file tree, header)
        "card": "#252526" if dark else "#f5f5f5",  # Elevated cards
        "border": border,
        "fg": fg,
        "muted": muted,

        # === Aliases for specific components ===
        "bg_header": surface,  # Header background
        "bg_header_alt": bg,  # Alternative header background (menus)
        "fg_dim": muted,  # Dimmed foreground
        "title": fg,  # Title text
        "focus_border": focus,  # Focus border

        # === Interactive ===
        "hover": "#2a2d2e" if dark else "#e8e8e8",  # --vscode-toolbar-hoverBackground
        "selection": "#264f78" if dark else "#add6ff",

        # === Input ===
        "input_bg": "#313131" if dark else "#ffffff",
        "input_border": "#3c3c3c" if dark else "#e0e0e0",

        # === Buttons ===
        "primary": "#0078d4" if dark else "#0090ff",
        "primary_hover": "#026ec1" if dark else "#006cbe",
        "danger": "#f44747" if dark else "#d32f2f",
        "danger_hover": "#d32f2f" if dark else "#b71c1c",

        # === Scrollbar ===
        "scrollbar": "#ffffff1a" if dark else "#c1c1c1",  # Transparent track
        "scrollbar_hover": "#ffffff33" if dark else "#a8a8a8",

        # === Chat/Agent Panel ===
        "bubble_bg": "#2a2a2a" if dark else "#f0f0f0",
        "bubble_hover": "#333333" if dark else "#e8e8e8",
        "avatar_bg": "#3c3c3c" if dark else "#e0e0e0",
        "avatar_fg": "#cccccc" if dark else "#616161",

        # === Status Indicators ===
        "status_think": "#0078d4" if dark else "#0090ff",
        "status_tool": "#cca700" if dark else "#bf8900",
        "status_error": "#f44747" if dark else "#d32f2f",
        "status_debug": "#b180d7" if dark else "#7b1fa2",
        "status_idle": "#737373" if dark else "#9e9e9e",

        # === Header Actions ===
        "header_action": "#737373" if dark else "#9e9e9e",
        "header_action_hover": "#cccccc" if dark else "#616161",

        # === File Tree ===
        "tree_hover": "#2a2d2e" if dark else "#e8e8e8",
        "tree_sel_bg": "#2a2d2e" if dark else "#dcdcdc",
        "tree_sel_fg": "#ffffff" if dark else "#202020",

        # === Editor/Preview ===
        "editor_bg": "#1f1f1f" if dark else "#ffffff",
        "editor_fg": "#d4d4d4" if dark else "#333333",
        "editor_margin": "#252526" if dark else "#f3f3f3",
        "accent": "#0078d4" if dark else "#0090ff",
        "compile_bg": "#0e639c" if dark else "#0078d4",
        "compile_fg": "#ffffff",

        # === Tabs ===
        "tab_active_bg": "#1f1f1f" if dark else "#f3f3f3",
        "tab_inactive_bg": "#2d2d2d" if dark else "#ececec",
        "tab_active_fg": "#ffffff" if dark else "#1a1a1a",
        "tab_inactive_fg": "#969696" if dark else "#888888",

        # === Context Menu ===
        "context_bg": "#1f1f1f" if dark else "#f3f3f3",
        "context_border": "#2b2b2b" if dark else "#e0e0e0",

        # === Spinner ===
        "spinner_fg": "#0078d4" if dark else "#0090ff",

        # === Tool Calls ===
        "tool_fg": "#cccccc" if dark else "#616161",
        "tool_border": "#2b2b2b" if dark else "#e0e0e0",
        "tool_detail": "#737373" if dark else "#9e9e9e",
    }


def format_stylesheet(template: str, colors: dict[str, str] | None = None) -> str:
    """Format a stylesheet template with theme colors.

    Args:
        template: CSS template string with {color_name} placeholders.
        colors: Optional color dict (uses get_theme_colors() if None).

    Returns:
        Formatted stylesheet string.
    """
    if colors is None:
        colors = get_theme_colors()
    return template.format(**colors)
