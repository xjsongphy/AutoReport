"""Logging configuration for AutoReport."""

import sys
import traceback
from pathlib import Path

from loguru import logger

# Dedicated UI action logger — records user interactions for debugging
ui_logger = logger.bind(ui_action=True)


def setup_logging(
    log_level: str = "INFO",
    log_to_file: bool = True,
    log_dir: Path | None = None,
) -> None:
    """Setup logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_to_file: Whether to log to file.
        log_dir: Directory for log files (defaults to ./logs).
    """
    # Remove default handler
    logger.remove()

    # Console handler — RichHandler for beautiful terminal output
    _add_console_handler(log_level)

    # File handler for all logs
    if log_to_file:
        if log_dir is None:
            log_dir = Path("./logs")

        log_dir.mkdir(parents=True, exist_ok=True)

        # Main log file — callable format appends traceback only when present
        logger.add(
            log_dir / "autoreport_{time:YYYY-MM-DD}.log",
            level="DEBUG",
            format=_file_format,
            rotation="100 MB",
            retention="10 days",
            compression="zip",
            encoding="utf-8",
        )

        # Error log file — same callable format with backtrace/diagnose
        logger.add(
            log_dir / "errors_{time:YYYY-MM-DD}.log",
            level="ERROR",
            format=_file_format,
            rotation="50 MB",
            retention="30 days",
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
        )

        # UI actions log file — records user interactions for debugging
        logger.add(
            log_dir / "ui_actions_{time:YYYY-MM-DD}.log",
            level="DEBUG",
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>UI_ACTION</level> | {message}",
            rotation="50 MB",
            retention="7 days",
            compression="zip",
            encoding="utf-8",
            filter=lambda record: "ui_action" in record["extra"],
        )

    logger.info("Logging configured: level={}, log_to_file={}", log_level, log_to_file)


def _add_console_handler(log_level: str) -> None:
    """Add a rich-powered console handler for beautiful terminal output.

    Uses rich.logging.RichHandler when available, falling back to a
    colorized loguru format for environments without rich.
    """
    try:
        from rich.logging import RichHandler

        # RichHandler + loguru: use a format with just the message,
        # since RichHandler renders time/level/path in its own markup.
        logger.add(
            RichHandler(
                console=None,  # auto-detect
                show_time=True,
                show_level=True,
                show_path=True,
                markup=True,
                rich_tracebacks=True,
                log_time_format="%Y-%m-%d %H:%M:%S",
            ),
            level=log_level,
            format="{message}",
        )
    except ImportError:
        # Fallback: colorized loguru format
        logger.add(
            sys.stderr,
            level=log_level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
        )


def _file_format(record):
    """Format for file output — appends traceback only when exception is present."""
    base = (
        f"{record['time']:YYYY-MM-DD HH:mm:ss} | "
        f"{record['level'].name: <8} | "
        f"{record['name']}:{record['function']}:{record['line']} | "
        f"{record['message']}"
    )
    exc = record.get("exception")
    if exc and exc.value is not None:
        tb = "".join(traceback.format_exception(exc.type, exc.value, exc.traceback))
        if tb:
            return base + "\n" + tb + "\n"
    return base + "\n"


def log_exception(
    message: str,
    exc: Exception,
    level: str = "ERROR",
) -> None:
    """Log an exception with full traceback.

    Args:
        message: Error message.
        exc: Exception to log.
        level: Log level (ERROR, CRITICAL).
    """
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    log_method = getattr(logger, level.lower(), logger.error)
    log_method("{}\nException: {}\n\n{}", message, type(exc).__name__, tb_str)


def get_logger(name: str):
    """Get a logger instance.

    Args:
        name: Logger name (usually __name__).

    Returns:
        Logger instance.
    """
    return logger.bind(name=name)


# Global exception handler
def setup_exception_handler() -> None:
    """Setup global exception handler."""

    def handle_exception(exc_type, exc_value, exc_traceback):
        """Handle uncaught exceptions."""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Also print to stderr directly so it's always visible
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

        # Use exception-aware logging to avoid markup parsing issues
        # when traceback text contains angle brackets like "<module>".
        logger.opt(exception=(exc_type, exc_value, exc_traceback)).error("Uncaught exception")

    sys.excepthook = handle_exception
