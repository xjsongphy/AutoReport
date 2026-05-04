"""DPI-aware scaling factor for UI element sizes.

Returns a scale factor based on the primary screen's logical DPI relative
to the standard 96 DPI baseline.  On macOS Retina displays Qt reports a
logical DPI of 72, so the factor is near 1.0.  On a 4K display at 150 %
scaling (144 logical DPI) the factor is ~1.5.
"""

from PyQt6.QtGui import QGuiApplication


def dpi_scale() -> float:
    """Return the DPI scale factor for the primary screen.

    Uses logicalDotsPerInch() relative to 96 DPI baseline, clamped
    to a minimum of 1.0 so macOS (72 logical DPI) is not shrunk.

    Returns 1.0 if no screen is available (headless / early init).
    """
    app = QGuiApplication.instance()
    if app is None:
        return 1.0
    screen = app.primaryScreen()
    if screen is None:
        return 1.0
    return max(screen.logicalDotsPerInch() / 96.0, 1.0)


def scaled(value: int) -> int:
    """Return *value* multiplied by the DPI scale factor, rounded to int."""
    return round(value * dpi_scale())


def scaled_size(w: int, h: int) -> tuple[int, int]:
    """Return (width, height) both scaled by DPI factor."""
    s = dpi_scale()
    return round(w * s), round(h * s)
