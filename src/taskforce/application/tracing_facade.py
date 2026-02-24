"""
Application Layer - Tracing Facade

Provides application-level access to infrastructure tracing,
maintaining clean architecture boundaries.

API layer should import from here instead of directly from infrastructure.
"""

from typing import Any

from taskforce.infrastructure.tracing import (
    TracingConfig,
)
from taskforce.infrastructure.tracing import (
    get_tracer as _get_tracer,
)
from taskforce.infrastructure.tracing import (
    init_tracing as _init_tracing,
)
from taskforce.infrastructure.tracing import (
    shutdown_tracing as _shutdown_tracing,
)


def init_tracing() -> None:
    """Initialize application tracing."""
    _init_tracing()


def shutdown_tracing() -> None:
    """Shutdown application tracing and flush pending spans."""
    _shutdown_tracing()


def get_tracer() -> Any:
    """Get the global tracer instance for creating custom spans."""
    return _get_tracer()


__all__ = ["init_tracing", "shutdown_tracing", "get_tracer", "TracingConfig"]
