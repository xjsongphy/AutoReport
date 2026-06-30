"""Regression guard: GUI stylesheets must not use web-only font aliases.

Qt's font resolver cannot map CSS web aliases like ``-apple-system`` or
``BlinkMacSystemFont`` to real fonts; using them triggers the noisy
``qt.qpa.fonts: Populating font family aliases …`` warning at startup.
Keep the font stacks limited to real, installed font families.
"""

from pathlib import Path

WEB_FONT_ALIASES = ("-apple-system", "BlinkMacSystemFont")


def _gui_source_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2] / "autoreport" / "gui"
    return sorted(root.rglob("*.py"))


def test_no_web_font_aliases_in_gui_stylesheets() -> None:
    offenders: list[str] = []
    for path in _gui_source_files():
        text = path.read_text(encoding="utf-8")
        for alias in WEB_FONT_ALIASES:
            if alias in text:
                offenders.append(f"{path}: {alias}")
    assert not offenders, (
        "Web-only font aliases found (they trigger qt.qpa.fonts warnings): "
        + "; ".join(offenders)
    )
