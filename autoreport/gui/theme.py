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
    titlebar_bg = "#141414" if dark else surface
    messages_bg = panel_bg
    border = "#2b2b2b" if dark else "#e0e0e0"
    fg = "#cccccc" if dark else "#616161"
    muted = "#737373" if dark else "#9e9e9e"

    # Blue system: only two keys should be consumed by UI code.
    button_blue = "#0078d4" if dark else "#0090ff"
    selection_blue = "#264f78" if dark else "#add6ff"
    hover = "#2a2d2e" if dark else "#e8e8e8"
    danger = "#f44747" if dark else "#d32f2f"
    success = "#4ec9b0" if dark else "#008000"
    input_bg = "#313131" if dark else "#ffffff"
    input_border = "#3c3c3c" if dark else "#e0e0e0"
    input_fg = "#cccccc" if dark else "#333333"
    disabled_fg = muted
    secondary_bg = "#3c3c3c" if dark else "#e0e0e0"
    secondary_border = "#3c3c3c" if dark else "#c5c5c5"
    detail_card_bg = "#23272f" if dark else "#ffffff"
    detail_card_border = "#353b46" if dark else border
    detail_muted = "#9aa3b2" if dark else muted
    detail_fg = "#d5dbe5" if dark else fg

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
        "buttonBlue": button_blue,
        "selectionBlue": selection_blue,
        "radius_sm": "4px",
        "radius_md": "6px",
        "radius_lg": "10px",

        # === Font Weights ===
        "fw_normal": "400",
        "fw_medium": "500",
        "fw_semibold": "600",
        "fw_bold": "700",

        # === Aliases for specific components ===
        "title": fg,  # Title text

        # === Interactive ===
        "hover": hover,  # --vscode-toolbar-hoverBackground

        # === Input ===
        "input_bg": input_bg,
        "input_border": input_border,

        # === Buttons ===
        "danger": danger,
        "danger_hover": "#d32f2f" if dark else "#b71c1c",

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
        "status_tool": "#cca700" if dark else "#bf8900",
        "status_running": button_blue,
        "status_success": success,
        "status_error": danger,
        "status_debug": "#b180d7" if dark else "#7b1fa2",
        "status_idle": muted,
        "timeline_dot": "#9ca3af" if dark else "#000000",

        # === File Tree ===
        "tree_hover": "#2a2d2e" if dark else "#e8e8e8",
        "tree_sel_bg": "#094771" if dark else "#cce8ff",
        "tree_sel_fg": "#ffffff" if dark else "#202020",

        # === Editor/Preview ===
        "editor_bg": bg,
        "editor_fg": "#d4d4d4" if dark else "#333333",
        "editor_margin": bg if dark else "#ffffff",
        "editor_caret_fg": "#ffffff" if dark else "#000000",
        "markdown_table_header_bg": "#252526" if dark else "#ffffff",

        # === Tabs ===
        "tab_active_bg": bg if dark else "#ffffff",
        "tab_active_fg": "#ffffff" if dark else "#1a1a1a",
        "tab_inactive_fg": "#969696" if dark else "#888888",

        # === Context Menu ===
        "context_bg": bg if dark else "#f3f3f3",
        "context_border": "#2b2b2b" if dark else "#e0e0e0",
        "popup_fg": "#cccccc" if dark else "#333333",
        "popup_hover": "#2a2d2e" if dark else "#f5f5f5",

        # === Tool Calls ===
        "tool_fg": fg,
        "tool_detail": muted,
        "detail_card_bg": detail_card_bg,
        "detail_card_border": detail_card_border,
        "detail_muted": detail_muted,
        "detail_fg": detail_fg,
        "detail_hover_fg": "#e2e8f0" if dark else fg,

        # === Message Controls ===
        "message_expand_bg": "rgba(32, 33, 36, 0.92)" if dark else "rgba(245, 245, 245, 0.96)",
        "message_expand_fg": "#f3f4f6" if dark else "#333333",
        "message_expand_border": (
            "rgba(255, 255, 255, 0.08)" if dark else "rgba(0, 0, 0, 0.10)"
        ),
        "message_expand_hover_bg": (
            "rgba(48, 50, 56, 0.96)" if dark else "rgba(232, 232, 232, 0.98)"
        ),

        # === Icon Semantic Colors ===
        "icon_default": "#d4d4d4" if dark else "#616161",
        "icon_run": success,
        "icon_preview": success,
        "icon_context_eye": "#a6a6a6" if dark else muted,
        "agent_main": button_blue,
        "agent_data_analysis": "#107c10" if dark else "#008000",
        "agent_plotting": "#8e44ad" if dark else "#7b1fa2",
        "agent_theory": "#e67e22" if dark else "#bf8900",
        "agent_report": "#5dade2" if dark else "#267f99",

        # === Syntax Highlighting ===
        "syntax_keyword": "#C586C0" if dark else "#AF00DB",
        "syntax_string": "#CE9178" if dark else "#A31515",
        "syntax_comment": "#6A9955" if dark else "#008000",
        "syntax_number": "#B5CEA8" if dark else "#098658",
        "syntax_operator": "#D4D4D4" if dark else "#000000",
        "syntax_identifier": "#9CDCFE" if dark else "#001080",
        "syntax_class_name": "#4EC9B0" if dark else "#267F99",
        "syntax_function": "#DCDCAA" if dark else "#795E26",

        # === Dialog/Config Specific ===
        "activeFg": "#ffffff" if dark else "#202020",
        "checkFg": success,

        # === Input Variations ===
        "inputBg": input_bg,
        "inputBorder": input_border,
        "inputFg": input_fg,
        "inputDisabledBg": "#1f1f1f" if dark else "#f3f3f3",
        "inputDisabledFg": disabled_fg,

        # === Primary Button Variations ===
        "primaryBtnFg": "#ffffff",

        # === Secondary Button ===
        "secondaryBtnBg": secondary_bg,
        "secondaryBtnBorder": secondary_border,
        "secondaryBtnFg": fg,
        "secondaryBtnHoverBg": hover,
        "secondaryBtnHoverBorder": "#4c4c4c" if dark else "#b5b5b5",

        # === Action Buttons ===
        "addBtnBorder": secondary_border,
        "addBtnFg": fg,
        "deleteFg": danger,
        "deleteHoverBg": danger,
        "deleteHoverFg": "#ffffff",
        "resetFg": fg,
        "resetHoverFg": "#ffffff" if dark else "#202020",

        # === Test/Connection Buttons ===
        "cancelHoverFg": "#ffffff" if dark else "#202020",

        # === Path/Link ===
        "pathFg": fg,

        # === Warning/Error ===
        "warningBg": "#4a1d1d" if dark else "#ffe5e5",
        "warningBorder": "#d94545" if dark else "#e55555",
        "warningFg": "#ff6b6b" if dark else "#c53030",
        "successFg": success,
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
