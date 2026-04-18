"""
Application Layer - Tracing Facade

Provides application-level access to infrastructure tracing,
maintaining clean architecture boundaries.

API layer should import from here instead of directly from infrastructure.
"""

from taskforce.infrastructure.tracing import (
    TracingConfig,
    get_tracer,
    init_tracing,
    shutdown_tracing,
)

__all__ = ["init_tracing", "shutdown_tracing", "get_tracer", "TracingConfig"]
