"""
Logging Protocol Interface for Core Domain.

Defines the LoggerProtocol interface to abstract logging operations,
allowing the Core domain to remain independent of specific logging
implementations (e.g., structlog).
"""

from typing import Any, Protocol


class LoggerProtocol(Protocol):
    """Protocol for logging operations in Core domain."""

    def info(self, event: str, **kwargs: Any) -> None:
        """Log an informational message."""
        ...

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log a warning message."""
        ...

    def error(self, event: str, **kwargs: Any) -> None:
        """Log an error message."""
        ...

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log a debug message."""
        ...
