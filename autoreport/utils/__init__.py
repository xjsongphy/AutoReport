"""Utility functions for AutoReport."""

from .logging_config import (
    add_project_logging,
    get_logger,
    log_exception,
    setup_exception_handler,
    setup_logging,
)

__all__ = [
    "setup_logging",
    "add_project_logging",
    "log_exception",
    "get_logger",
    "setup_exception_handler",
]
