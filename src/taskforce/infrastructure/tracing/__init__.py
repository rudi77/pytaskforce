"""
Infrastructure Layer - Tracing

This module provides OpenTelemetry-based tracing with Arize Phoenix integration.
Follows hexagonal architecture by keeping observability concerns in infrastructure.
"""

from taskforce.infrastructure.tracing.phoenix_tracer import (
    init_tracing,
    shutdown_tracing,
    get_tracer,
    TracingConfig,
)

__all__ = [
    "init_tracing",
    "shutdown_tracing",
    "get_tracer",
    "TracingConfig",
]

