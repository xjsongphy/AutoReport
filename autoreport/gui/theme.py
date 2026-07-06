"""Unified theme management for AutoReport GUI.

Provides centralized color definitions for dark/light modes,
following the Claude Code design language.
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
    bg = "#1f1f1f" if dark else "#ffffff"
    surface = "#181818" if dark else "#f8f8f8"
    panel_bg = "#181818" if dark else "#f8f8f8"
    titlebar_bg = "#181818" if dark else surface
    messages_bg = panel_bg
    border = "#2b2b2b" if dark else "#e5e5e5"
    fg = "#cccccc" if dark else "#3b3b3b"
    muted = "#9d9d9d" if dark else "#616161"

    # Blue system: only two keys should be consumed by UI code.
    button_blue = "#0078d4" if dark else "#005fb8"
    selection_blue = "#264f78" if dark else "#add6ff"
    hover = "#2a2d2e" if dark else "#e8e8e8"
    danger = "#f44747" if dark else "#d32f2f"
    success = "#73c991" if dark else "#388a34"
    input_bg = "#313131" if dark else "#ffffff"
    input_border = "#3c3c3c" if dark else "#cecece"
    input_fg = "#cccccc" if dark else "#3b3b3b"
    disabled_fg = muted
    secondary_bg = "#313131" if dark else "#e5e5e5"
    secondary_border = "#3c3c3c" if dark else "#cecece"
    detail_card_bg = "#1f1f1f" if dark else "#ffffff"
    detail_card_border = border
    detail_muted = muted
    detail_fg = fg

    return {
        # === Layout ===
        "bg": bg,  # Main content area
        "surface": surface,  # Sidebar/chrome (file tree, header)
        "panel_bg": panel_bg,  # Agent panel background (darker than editor)
        "titlebar_bg": titlebar_bg,  # Custom window title bar background
        "messages_bg": messages_bg,  # Agent conversation area background
        "card": "#252526" if dark else "#f8f8f8",  # Elevated cards
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
        # Neutral gray (R=G=B, no green/blue cast) for user-bubble and
        # context-chip borders — light enough to read as ash-gray, not white.
        "gray_white": "#a6a6a6" if dark else "#a6a6a6",
        "edit_bubble_bg": "#3c3c3c" if dark else "#ffffff",
        "edit_bubble_border": "transparent" if dark else "#cecece",
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
        "tree_sel_bg": "#094771" if dark else "#e8e8e8",
        "tree_sel_fg": "#ffffff" if dark else "#202020",

        # === Editor/Preview ===
        "editor_bg": bg,
        "editor_fg": fg,
        "editor_margin": bg if dark else "#ffffff",
        "editor_caret_fg": "#ffffff" if dark else "#005fb8",
        "markdown_table_header_bg": "#252526" if dark else "#f8f8f8",

        # === Tabs ===
        "tab_active_bg": bg if dark else "#ffffff",
        "tab_active_fg": "#ffffff" if dark else "#3b3b3b",
        "tab_inactive_fg": "#9d9d9d" if dark else "#868686",

        # === Context Menu ===
        "context_bg": bg if dark else "#ffffff",
        "context_border": "#454545" if dark else "#cecece",
        "popup_fg": "#cccccc" if dark else "#3b3b3b",
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
        "icon_default": "#cccccc" if dark else "#3b3b3b",
        "icon_run": success,
        "icon_preview": success,
        "icon_context_eye": "#a6a6a6" if dark else muted,
        "agent_main": button_blue,
        "agent_data_analysis": "#73c991" if dark else "#388a34",
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

        # === Markdown tokens (VSCode dark-modern / light-modern) ===
        # markup.heading / markup.bold — bold blue (dark) vs navy/maroon (light).
        "md_heading": "#569CD6" if dark else "#800000",
        "md_bold": "#569CD6" if dark else "#000080",
        # markup.italic — *italic* / _italic_ (same hue as bold, italic via font).
        "md_italic": "#569CD6" if dark else "#000080",
        # markup.underline.link — [text](url) link target text.
        "md_link": "#4CB9FF" if dark else "#0451A5",
        # markup.strikethrough — ~~strikethrough~~ (muted grey).
        "md_strikethrough": "#808080" if dark else "#555555",
        # markup.inline.raw — inline `code` (own key so light mode uses blue,
        # not the red from syntax_string).
        "md_code": "#CE9178" if dark else "#0451A5",
        # punctuation.definition.list.begin — list markers (-, *, 1.).
        "md_list": "#6796E6" if dark else "#0451A5",
        # punctuation.definition.quote.begin — block-quote marker (>).
        "md_quote": "#6A9955" if dark else "#008000",
        # markup.horizontal-rule — --- / *** (subtle, same as comment or muted).
        "md_hr": "#6A9955" if dark else "#008000",

        # === TeX tokens (VSCode dark-modern / light-modern) ===
        # support.function.general.tex — \section, \textbf etc.
        "tex_command": "#DCDCAA" if dark else "#795E26",
        # keyword.control.tex — \begin, \end, \usepackage, \documentclass etc.
        "tex_keyword": "#C586C0" if dark else "#AF00DB",
        # constant.character.escape — $ # % & ~ _ ^ \ (foreground = punctuation).
        "tex_special": "#D4D4D4" if dark else "#000000",
        # punctuation.definition.group.brace — {…} (foreground = punctuation).
        "tex_group": "#D4D4D4" if dark else "#000000",
        # string.other.math — $E=mc^2$ math content (string, not number).
        "tex_math": "#CE9178" if dark else "#A31515",

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


def scrollbar_stylesheet(
    *,
    selector: str = "QScrollBar",
    orientation: str = "vertical",
    background_color: str = "transparent",
    thickness: str = "8px",
    min_handle_extent: str = "30px",
    radius: str = "4px",
    margin: str | None = None,
    handle_margin: str | None = None,
    colors: dict[str, str] | None = None,
) -> str:
    """Build themed scrollbar QSS while leaving layout choices to callers."""
    if colors is None:
        colors = get_theme_colors()
    if orientation not in {"vertical", "horizontal"}:
        raise ValueError("orientation must be 'vertical' or 'horizontal'")

    thickness_prop = "width" if orientation == "vertical" else "height"
    min_extent_prop = "min-height" if orientation == "vertical" else "min-width"
    line_extent_prop = "height" if orientation == "vertical" else "width"
    margin_rule = f"\n                margin: {margin};" if margin else ""
    handle_margin_rule = f"\n                margin: {handle_margin};" if handle_margin else ""

    return f"""
            {selector}:{orientation} {{
                background-color: {background_color};
                {thickness_prop}: {thickness};
                border: none;
                {margin_rule}
            }}
            {selector}::handle:{orientation} {{
                background-color: {colors["scrollbar"]};
                {min_extent_prop}: {min_handle_extent};
                border-radius: {radius};
                {handle_margin_rule}
            }}
            {selector}::handle:{orientation}:hover,
            {selector}::handle:{orientation}:pressed {{
                background-color: {colors["scrollbar_hover"]};
            }}
            {selector}::groove:{orientation} {{
                background-color: {background_color};
                border: none;
            }}
            {selector}::add-line:{orientation},
            {selector}::sub-line:{orientation} {{
                {line_extent_prop}: 0;
                margin: 0;
                border: none;
                background-color: transparent;
            }}
            {selector}::add-page:{orientation},
            {selector}::sub-page:{orientation} {{
                background-color: transparent;
            }}
        """
