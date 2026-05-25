"""Unified theme management for AutoReport GUI.

Provides centralized color definitions for dark/light modes,
following VSCode Copilot Chat design language.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


def is_dark_mode() -> bool:
    """Detect if system is in dark mode."""
    app = QApplication.instance()
    if app is None:
        return False

    hints = app.styleHints()
    if hasattr(hints, "colorScheme"):
        try:
            if hints.colorScheme() == Qt.ColorScheme.Dark:
                return True
            if hints.colorScheme() == Qt.ColorScheme.Light:
                return False
        except Exception:
            pass

    # Fallback for platforms where colorScheme is unavailable/unreliable.
    # Compare window/background luminance from current palette.
    window = app.palette().window().color()
    return window.lightness() < 128


def get_theme_colors() -> dict[str, str]:
    """Get unified theme colors for current mode.

    Returns:
        Dictionary of color name -> hex value.
        Based on VSCode Dark Modern / Light Modern palettes.
    """
    dark = is_dark_mode()

    # === Base Colors ===
    bg = "#1e1e1e" if dark else "#ffffff"
    surface = "#181818" if dark else "#f0f0f0"
    panel_bg = "#141414" if dark else "#f0f0f0"
    titlebar_bg = "#141414" if dark else "#e6e6e6"
    messages_bg = "#121212" if dark else "#f0f0f0"
    border = "#2b2b2b" if dark else "#e0e0e0"
    fg = "#cccccc" if dark else "#616161"
    muted = "#737373" if dark else "#9e9e9e"

    # Pre-define values before using in aliases
    focus = "#0078d4" if dark else "#0090ff"
    hover = "#2a2d2e" if dark else "#e8e8e8"

    return {
        # === Layout ===
        "bg": bg,  # Main content area
        "surface": surface,  # Sidebar/chrome (file tree, header)
        "panel_bg": panel_bg,  # Agent panel background (darker than editor)
        "titlebar_bg": titlebar_bg,  # Custom window title bar background
        "messages_bg": messages_bg,  # Agent conversation area background
        "card": "#252526" if dark else "#f5f5f5",  # Elevated cards
        "border": border,
        "fg": fg,
        "muted": muted,
        "radius_sm": "4px",
        "radius_md": "6px",
        "radius_lg": "10px",

        # === Font Weights ===
        "fw_normal": "400",
        "fw_medium": "500",
        "fw_semibold": "600",
        "fw_bold": "700",

        # === Aliases for specific components ===
        "bg_header": surface,  # Header background
        "bg_header_alt": bg,  # Alternative header background (menus)
        "fg_dim": muted,  # Dimmed foreground
        "title": fg,  # Title text
        "focus_border": focus,  # Focus border

        # === Interactive ===
        "hover": hover,  # --vscode-toolbar-hoverBackground
        "selection": "#264f78" if dark else "#add6ff",
        "focus": focus,  # Focus color for UI elements

        # === Input ===
        "input_bg": "#313131" if dark else "#ffffff",
        "input_border": "#3c3c3c" if dark else "#e0e0e0",
        "input_border_width": "1px",

        # === Buttons ===
        "primary": "#0078d4" if dark else "#0090ff",
        "primary_hover": "#026ec1" if dark else "#006cbe",
        "danger": "#f44747" if dark else "#d32f2f",
        "danger_hover": "#d32f2f" if dark else "#b71c1c",

        # === Chat Action Buttons ===
        "send_bg": "#0078d4" if dark else "#0090ff",
        "send_hover": "#026ec1" if dark else "#006cbe",
        "stop_bg": "#f44747" if dark else "#d32f2f",
        "stop_hover": "#d32f2f" if dark else "#b71c1c",

        # === Scrollbar ===
        "scrollbar": "#6b6b6b" if dark else "#c1c1c1",
        "scrollbar_hover": "#8a8a8a" if dark else "#a8a8a8",

        # === Chat/Agent Panel ===
        "bubble_bg": "#2a2a2a" if dark else "#ffffff",
        "bubble_hover": "#333333" if dark else "#ffffff",
        "edit_bubble_bg": "#3c3c3c" if dark else "#ffffff",
        "edit_bubble_border": "transparent" if dark else "#616161",
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
        "tree_sel_bg": "#094771" if dark else "#cce8ff",
        "tree_sel_fg": "#ffffff" if dark else "#202020",

        # === Editor/Preview ===
        "editor_bg": bg,
        "editor_fg": "#d4d4d4" if dark else "#333333",
        "editor_margin": bg if dark else "#ffffff",
        "editor_caret_fg": "#ffffff" if dark else "#000000",
        "accent": "#0078d4" if dark else "#0090ff",
        "compile_bg": "#0e639c" if dark else "#0078d4",
        "compile_fg": "#ffffff",

        # === Tabs ===
        "tab_active_bg": bg if dark else "#ffffff",
        "tab_inactive_bg": surface if dark else "#f0f0f0",
        "tab_active_fg": "#ffffff" if dark else "#1a1a1a",
        "tab_inactive_fg": "#969696" if dark else "#888888",

        # === Context Menu ===
        "context_bg": bg if dark else "#f3f3f3",
        "context_border": "#2b2b2b" if dark else "#e0e0e0",
        "popup_fg": "#cccccc" if dark else "#333333",
        "popup_hover": "#2a2d2e" if dark else "#f5f5f5",

        # === Spinner ===
        "spinner_fg": "#0078d4" if dark else "#0090ff",

        # === Tool Calls ===
        "tool_fg": "#cccccc" if dark else "#616161",
        "tool_border": "#2b2b2b" if dark else "#e0e0e0",
        "tool_detail": "#737373" if dark else "#9e9e9e",

        # === Dialog/Config Specific ===
        "bodyBg": bg,
        "headerBg": surface,
        "headerBorder": border,
        "footerBg": surface,
        "footerBorder": border,
        "cardBg": "#252526" if dark else "#f5f5f5",
        "cardBorder": border,
        "titleFg": fg,
        "subtitleFg": muted,
        "categoryFg": fg,
        "sectionFg": fg,
        "activeFg": "#ffffff" if dark else "#202020",
        "checkFg": "#4ec9b0" if dark else "#008000",

        # === Input Variations ===
        "inputBg": "#313131" if dark else "#ffffff",
        "inputBorder": "#3c3c3c" if dark else "#e0e0e0",
        "inputFg": "#cccccc" if dark else "#333333",
        "inputFocusBorder": focus,
        "inputDisabledBg": "#1f1f1f" if dark else "#f3f3f3",
        "inputDisabledFg": "#737373" if dark else "#9e9e9e",

        # === Primary Button Variations ===
        "primaryBg": "#0078d4" if dark else "#0090ff",
        "primaryFg": "#ffffff",
        "primaryHover": "#026ec1" if dark else "#006cbe",
        "primaryBtnBg": "#0078d4" if dark else "#0090ff",
        "primaryBtnFg": "#ffffff",
        "primaryBtnHover": "#026ec1" if dark else "#006cbe",
        "primaryBtnPressed": "#005a9e" if dark else "#005a9e",

        # === Secondary Button ===
        "secondaryBorder": "#3c3c3c" if dark else "#c5c5c5",
        "secondaryFg": fg,
        "secondaryHoverBg": hover,
        "secondaryBtnBg": "#3c3c3c" if dark else "#e0e0e0",
        "secondaryBtnBorder": "#3c3c3c" if dark else "#c5c5c5",
        "secondaryBtnFg": fg,
        "secondaryBtnHoverBg": hover,
        "secondaryBtnHoverBorder": "#4c4c4c" if dark else "#b5b5b5",

        # === Action Buttons ===
        "addBtnBorder": "#3c3c3c" if dark else "#c5c5c5",
        "addBtnFg": fg,
        "addBtnHoverBg": hover,
        "deleteFg": "#f44747" if dark else "#d32f2f",
        "deleteHoverBg": "#f44747" if dark else "#d32f2f",
        "deleteHoverFg": "#ffffff",
        "resetFg": fg,
        "resetHoverFg": "#ffffff" if dark else "#202020",

        # === Test/Connection Buttons ===
        "testBorder": "#3c3c3c" if dark else "#c5c5c5",
        "testFg": fg,
        "testHoverBg": hover,
        "testDisabledBorder": "#1f1f1f" if dark else "#f3f3f3",
        "testDisabledFg": "#737373" if dark else "#9e9e9e",

        # === Preset/Sync Buttons ===
        "presetBtnBg": "#3c3c3c" if dark else "#e0e0e0",
        "presetBtnBorder": "#3c3c3c" if dark else "#c5c5c5",
        "presetBtnFg": fg,
        "presetBtnHoverBg": hover,
        "syncBtnBorder": "#3c3c3c" if dark else "#c5c5c5",
        "syncBtnFg": fg,
        "syncBtnHoverBg": hover,

        # === Cancel Button ===
        "cancelFg": fg,
        "cancelHoverFg": "#ffffff" if dark else "#202020",

        # === Path/Link ===
        "pathFg": "#cccccc" if dark else "#616161",
        "link": "#0078d4" if dark else "#0090ff",
        "linkHover": "#026ec1" if dark else "#006cbe",

        # === Warning/Error ===
        "warningBg": "#4a1d1d" if dark else "#ffe5e5",
        "warningBorder": "#d94545" if dark else "#e55555",
        "warningFg": "#ff6b6b" if dark else "#c53030",
        "successFg": "#4ec9b0" if dark else "#008000",
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
