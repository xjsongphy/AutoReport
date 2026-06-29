"""AutoReport entry point wrapper.

Cleans conflicting environment variables (from conda/msys2) before
importing PyQt6, which prevents "Must construct a QApplication" errors
caused by loading Qt libraries from the wrong site-packages.
"""

import os


def main():
    # Remove conflicting virtual environment variables that may cause
    # uv/pip to load PyQt6 from conda/msys2 instead of the project venv.
    for var in ("VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
        os.environ.pop(var, None)

    # Silence Qt's font-alias "cost" warnings (missing "Sans Serif" etc.).
    # Must be set before any Qt library is imported — Qt reads this env var at
    # shared-library load time, not at QApplication construction.
    _merge_logging_rule("qt.qpa.fonts=false")

    from autoreport.app import app

    app()


def _merge_logging_rule(rule: str) -> None:
    existing = os.environ.get("QT_LOGGING_RULES", "")
    key = rule.split("=", 1)[0]
    if key in existing:
        return
    os.environ["QT_LOGGING_RULES"] = f"{existing};{rule}" if existing else rule


if __name__ == "__main__":
    main()
