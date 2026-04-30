"""Logging configuration for AutoReport."""

import sys
import traceback
from pathlib import Path

from loguru import logger


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

    # Console handler with colors
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True,
    )

    # File handler for all logs
    if log_to_file:
        if log_dir is None:
            log_dir = Path("./logs")

        log_dir.mkdir(parents=True, exist_ok=True)

        # Main log file (rotation at 100 MB, keep 10 backups)
        logger.add(
            log_dir / "autoreport_{time:YYYY-MM-DD}.log",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="100 MB",
            retention="10 days",
            compression="zip",
            encoding="utf-8",
        )

        # Error log file (only errors and above)
        logger.add(
            log_dir / "errors_{time:YYYY-MM-DD}.log",
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}\n{exception}",
            rotation="50 MB",
            retention="30 days",
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
        )

    logger.info("Logging configured: level={}, log_to_file={}", log_level, log_to_file)


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

        logger.error(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = handle_exception
