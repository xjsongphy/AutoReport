"""Custom exceptions for AutoReport.

Provides project-specific exception classes for better error handling
and debugging.
"""


class AutoReportError(Exception):
    """Base exception for all AutoReport errors."""

    def __init__(self, message: str, details: str | None = None) -> None:
        """Initialize AutoReportError.

        Args:
            message: Human-readable error message.
            details: Optional additional details for debugging.
        """
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class ConfigurationError(AutoReportError):
    """Raised when configuration is invalid or missing."""

    pass


class ProviderError(AutoReportError):
    """Raised when LLM provider operations fail."""

    pass


class ProviderNotFoundError(ConfigurationError):
    """Raised when requested LLM provider is not configured."""

    pass


class APIKeyError(ConfigurationError):
    """Raised when API key is missing or invalid."""

    pass


class TaskError(AutoReportError):
    """Raised when task operations fail."""

    pass


class TaskNotFoundError(TaskError):
    """Raised when a requested task does not exist."""

    pass


class TaskStateError(TaskError):
    """Raised when task is in wrong state for requested operation."""

    pass


class FileOperationError(AutoReportError):
    """Raised when file operations fail."""

    pass


class FileNotFoundError(FileOperationError):
    """Raised when a required file is not found."""

    pass


class WorkspaceError(AutoReportError):
    """Raised when workspace operations fail."""

    pass


class CheckpointError(AutoReportError):
    """Raised when checkpoint operations fail."""

    pass


class AgentLoopError(AutoReportError):
    """Raised when agent loop operations fail."""

    pass


class MessageBusError(AutoReportError):
    """Raised when message bus operations fail."""

    pass


class CompilationError(AutoReportError):
    """Raised when LaTeX compilation fails."""

    pass


class PDFError(AutoReportError):
    """Raised when PDF operations fail."""

    pass


class SyncError(AutoReportError):
    """Raised when preset synchronization fails."""

    pass
