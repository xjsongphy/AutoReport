import re
from pathlib import Path

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
