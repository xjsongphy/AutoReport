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

    from autoreport.app import app

    app()


if __name__ == "__main__":
    main()
