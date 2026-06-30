import re
from pathlib import Path

from autoreport.gui import theme

ROOT = Path(__file__).resolve().parents[2]


def test_gui_components_do_not_define_local_color_palettes():
    files = [
        ROOT / "autoreport/gui/main_window.py",
        ROOT / "autoreport/gui/widgets/tool_call_group.py",
        ROOT / "autoreport/gui/icons.py",
        ROOT / "autoreport/gui/scintilla_utils.py",
        ROOT / "autoreport/gui/widgets/markdown_renderer.py",
    ]
    color_pattern = re.compile(r"#[0-9A-Fa-f]{6,8}|rgba?\([^)]*\)")

    offenders: list[str] = []
    for path in files:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if color_pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()}")

    assert offenders == []


def test_dark_theme_editor_palette_matches_vscode_modern(monkeypatch):
    monkeypatch.setattr(theme, "is_dark_mode", lambda: True)

    colors = theme.get_theme_colors()

    assert colors["editor_bg"] == "#1f1f1f"
    assert colors["editor_fg"] == "#cccccc"
    assert colors["editor_margin"] == "#1f1f1f"
    assert colors["input_bg"] == "#313131"
    assert colors["input_border"] == "#3c3c3c"
    assert colors["tab_active_bg"] == "#1f1f1f"
    assert colors["status_success"] == "#73c991"


def test_light_theme_editor_palette_matches_vscode_modern(monkeypatch):
    monkeypatch.setattr(theme, "is_dark_mode", lambda: False)

    colors = theme.get_theme_colors()

    assert colors["editor_bg"] == "#ffffff"
    assert colors["editor_fg"] == "#3b3b3b"
    assert colors["editor_margin"] == "#ffffff"
    assert colors["input_bg"] == "#ffffff"
    assert colors["input_border"] == "#cecece"
    assert colors["tab_active_bg"] == "#ffffff"
    assert colors["status_success"] == "#388a34"
