"""
Application Layer - Tracing Facade

Provides application-level access to infrastructure tracing,
maintaining clean architecture boundaries.

API layer should import from here instead of directly from infrastructure.

Supports two tracing modes:
- Phoenix OTEL tracing (network-based, sends to collector)
- File-based tracing (local JSONL files for offline analysis)
"""

from pathlib import Path

from taskforce.infrastructure.tracing import (
    TracingConfig,
    get_tracer as _get_tracer,
    init_tracing as _init_tracing,
    shutdown_tracing as _shutdown_tracing,
    # File-based tracing
    FileTracer,
    init_file_tracing as _init_file_tracing,
    get_file_tracer as _get_file_tracer,
    shutdown_file_tracing as _shutdown_file_tracing,
)


def init_tracing() -> None:
    """Initialize application tracing (Phoenix OTEL)."""
    _init_tracing()


def shutdown_tracing() -> None:
    """Shutdown application tracing and flush pending spans."""
    _shutdown_tracing()


def get_tracer():
    """Get the global tracer instance for creating custom spans."""
    return _get_tracer()


def init_file_tracing(path: Path, session_id: str | None = None) -> FileTracer:
    """
    Initialize file-based tracing.

    Args:
        path: Path to the JSONL trace file
        session_id: Optional session ID to include in events

    Returns:
        FileTracer instance
    """
    return _init_file_tracing(path=path, session_id=session_id)


def get_file_tracer() -> FileTracer | None:
    """Get the global file tracer instance."""
    return _get_file_tracer()


def shutdown_file_tracing() -> None:
    """Shutdown file-based tracing."""
    _shutdown_file_tracing()


__all__ = [
    # Phoenix OTEL
    "init_tracing",
    "shutdown_tracing",
    "get_tracer",
    "TracingConfig",
    # File-based
    "FileTracer",
    "init_file_tracing",
    "get_file_tracer",
    "shutdown_file_tracing",
]
